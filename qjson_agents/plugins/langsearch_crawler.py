from __future__ import annotations

import os
import json
import requests
from typing import Any, Dict, Callable, List
from qjson_agents.plugin_manager import Plugin
from qjson_agents.web_crawler import Crawler
from qjson_agents.web_indexer import upsert_outline

def _fallback_googlesearch(query: str, k: int = 5) -> List[Dict[str, str]]:
    try:
        from googlesearch import search as _gsearch  # type: ignore
    except Exception:
        return []
    try:
        urls = list(_gsearch(query, num_results=k))
    except Exception:
        urls = []
    return [{"name": u, "url": u, "snippet": ""} for u in urls[:k]]

class LangSearchCrawlerPlugin(Plugin):
    """A plugin for performing web searches and crawling using the LangSearch API."""

    def get_commands(self) -> Dict[str, Callable[..., Any]]:
        return {
            "/crawl": self.crawl,
        }

    def crawl(self, *query_parts: str) -> str:
        """
        Performs a web search using LangSearch API and returns summarized results.
        Usage: /crawl <query>
        """
        query = " ".join(query_parts)
        if not query:
            return "Please provide a query to crawl for."

        # Top-K shared across branches
        try:
            topk = max(1, int(os.environ.get("QJSON_WEB_TOPK", "5")))
        except Exception:
            topk = 5

        api_key = os.environ.get("LANGSEARCH_API_KEY")
        # Detect crawl mode (seed URLs) via explicit url=... or if the query contains http(s) URLs
        parts = query.split()
        seeds = [p for p in parts if p.startswith("http://") or p.startswith("https://")]
        # Parse simple flags like depth=, pages=
        depth = None
        pages = None
        for p in parts:
            if p.startswith("depth="):
                try:
                    depth = max(0, int(p.split("=",1)[1]))
                except Exception:
                    pass
            elif p.startswith("pages="):
                try:
                    pages = max(1, int(p.split("=",1)[1]))
                except Exception:
                    pass
        # Optional per-page export via export=<out_dir>
        export_dir = None
        for p in parts:
            if p.startswith("export="):
                export_dir = p.split("=",1)[1]
        if seeds or depth is not None or pages is not None:
            # Multi-page crawl with BFS
            if not seeds:
                return "Usage: /crawl <URL...> [depth=N] [pages=M]"
            try:
                d = depth if depth is not None else 1
                m = pages if pages is not None else max(5, topk)
                cr = Crawler(rate_per_host=float(os.environ.get("QJSON_CRAWL_RATE", "1.0")))
                outlines = cr.crawl(seeds, max_depth=d, max_pages=m)
                # Index into current agent's memory/index
                agent_id = os.environ.get("QJSON_AGENT_ID") or "WebCrawler"
                for o in outlines:
                    try:
                        upsert_outline(agent_id, o)
                    except Exception:
                        pass
                # Optional per-page JSON export
                if export_dir:
                    try:
                        from pathlib import Path
                        Path(export_dir).mkdir(parents=True, exist_ok=True)
                        import re, json as _json
                        def _slug(s: str) -> str:
                            s = (s or "untitled").strip().lower()
                            s = re.sub(r"[^a-z0-9]+","-", s)
                            return s.strip("-") or "doc"
                        for o in outlines:
                            title = o.get("title") or o.get("url") or "page"
                            fname = _slug(title)[:64] + ".json"
                            (Path(export_dir) / fname).write_text(_json.dumps(o, ensure_ascii=False, indent=2), encoding="utf-8")
                    except Exception:
                        pass
                # Prepare results cache for /open consumption
                pages_list = [{
                    "title": (o.get("title") or o.get("url") or ""),
                    "url": (o.get("url") or ""),
                    "snippet": ((o.get("sections") or [{}])[0].get("text") or "")[:240],
                } for o in outlines]
                payload = json.dumps(pages_list[:topk])
                os.environ["QJSON_WEBSEARCH_RESULTS_ONCE"] = payload
                os.environ["QJSON_WEBRESULTS_CACHE"] = payload
                os.environ.setdefault("QJSON_WEBSEARCH_HEADER", "### Web Crawl Results (BFS)")
                # Render pretty output
                out_lines = []
                if not outlines:
                    return "No pages crawled. Check URL, depth, and pages limits."
                for i, o in enumerate(outlines[:topk], 1):
                    out_lines.append(f"--- Result {i} ---\nTitle: {o.get('title') or 'N/A'}\nURL: {o.get('url') or 'N/A'}\nSnippet: {((o.get('sections') or [{}])[0].get('text') or '')[:240]}")
                return "\n\n".join(out_lines)
            except Exception as e:
                return f"[crawl error] {e}"
        
        # If not a BFS crawl, fall back to web search results (LangSearch or googlesearch)
        if not api_key:
            # Web-only fallback via googlesearch
            local = _fallback_googlesearch(query, k=topk)
            if not local:
                return "LangSearch API key not found and no web fallback results. Set LANGSEARCH_API_KEY or enable googlesearch-python."
            try:
                norm = [{
                    "title": str(p.get("name") or p.get("url") or ""),
                    "url": str(p.get("url") or ""),
                    "snippet": str(p.get("snippet") or ""),
                } for p in local]
                payload = json.dumps(norm[:topk])
                os.environ["QJSON_WEBSEARCH_RESULTS_ONCE"] = payload
                os.environ["QJSON_WEBRESULTS_CACHE"] = payload
                os.environ.setdefault("QJSON_WEBSEARCH_HEADER", "### Web Crawl Results (WebFallback)")
            except Exception:
                pass
            return self._format_results({"data": {"webPages": {"value": local}}})

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "query": query,
            "summary": True,
            "count": topk
        }

        try:
            response = requests.post("https://api.langsearch.com/v1/web-search", headers=headers, json=payload)
            response.raise_for_status()  # Raise an exception for HTTP errors
            search_results = response.json()
            # Normalize and arm one-shot injection for next prompt
            try:
                pages = (((search_results or {}).get("data") or {}).get("webPages") or {}).get("value") or []
                norm: List[Dict[str, str]] = []
                for p in pages:
                    if isinstance(p, dict):
                        norm.append({
                            "title": str(p.get("name") or p.get("title") or p.get("url") or ""),
                            "url": str(p.get("url") or ""),
                            "snippet": str(p.get("summary") or p.get("snippet") or ""),
                        })
                if norm:
                    payload = json.dumps(norm[:topk])
                    os.environ["QJSON_WEBSEARCH_RESULTS_ONCE"] = payload
                    os.environ["QJSON_WEBRESULTS_CACHE"] = payload
                    os.environ.setdefault("QJSON_WEBSEARCH_HEADER", "### Web Crawl Results (LangSearch)")
            except Exception:
                pass
            return self._format_results(search_results)
        except requests.exceptions.RequestException:
            # Network or HTTP error – web-only fallback via googlesearch
            local = _fallback_googlesearch(query, k=topk)
            if local:
                try:
                    norm = [{
                        "title": str(p.get("name") or p.get("url") or ""),
                        "url": str(p.get("url") or ""),
                        "snippet": str(p.get("snippet") or ""),
                    } for p in local]
                    payload = json.dumps(norm[:topk])
                    os.environ["QJSON_WEBSEARCH_RESULTS_ONCE"] = payload
                    os.environ["QJSON_WEBRESULTS_CACHE"] = payload
                    os.environ.setdefault("QJSON_WEBSEARCH_HEADER", "### Web Crawl Results (WebFallback)")
                except Exception:
                    pass
                return self._format_results({"data": {"webPages": {"value": local}}})
            return "An error occurred during the API request and no web fallback results were found."
        except json.JSONDecodeError as e:
            return f"Failed to parse API response: {e}"
        except Exception as e:
            return f"An unexpected error occurred: {e}"

    def _format_results(self, results: dict) -> str:
        if not results or not results.get("data") or not results["data"].get("webPages") or not results["data"]["webPages"].get("value"):
            return "No search results found."

        formatted_string = ""
        for i, page in enumerate(results["data"]["webPages"]["value"]):
            formatted_string += f"--- Result {i+1} ---\n"
            formatted_string += f"Title: {page.get('name', 'N/A')}\n"
            formatted_string += f"URL: {page.get('url', 'N/A')}\n"
            formatted_string += f"Snippet: {page.get('snippet', 'N/A')}\n"
            if page.get("summary"):
                formatted_string += f"Summary: {page.get('summary', 'N/A')}\n"
            formatted_string += "\n"

        return formatted_string
