from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
import os
from typing import Any, Dict, List, Tuple
from urllib import request as _urlreq, error as _urlerr

from .agent import Agent
from .qjson_types import load_manifest, save_manifest, scan_personas, find_persona
from .yson import yson_to_manifest, yson_to_swarm, synthesize_manifest_from_yson_name, load_yson
from .memory import (
    agent_dir,
    ensure_agent_dirs,
    write_json,
    load_cluster_index,
    refresh_cluster_index,
    load_router_weights,
    save_router_weights,
    agents_home,
)
from .ollama_client import OllamaClient
from .plugin_manager import load_plugins
from .web_crawler import Crawler
from .web_indexer import upsert_outline
import time
import logging
from datetime import datetime
import math
import random


def _print(s: str) -> None:
    sys.stdout.write(s + "\n")
    sys.stdout.flush()


def _parse_search_roots() -> List[str]:
    # Roots can be set via env QJSON_LOCAL_SEARCH_ROOTS as os.pathsep-separated list
    raw = os.environ.get("QJSON_LOCAL_SEARCH_ROOTS", "").strip()
    if not raw:
        return [os.getcwd()]
    roots = [p for p in raw.split(os.pathsep) if p]
    out: List[str] = []
    for r in roots:
        try:
            pr = os.path.expanduser(os.path.expandvars(r))
            if os.path.isdir(pr):
                out.append(pr)
        except Exception:
            continue
    return out or [os.getcwd()]


def _local_repo_search(query: str, max_results: int = 5) -> List[Dict[str, str]]:
    """Local search across configured roots as offline fallback.

    Roots are read from QJSON_LOCAL_SEARCH_ROOTS (os.pathsep-separated); defaults
    to current working directory. Skips common heavy or transient directories.
    Returns entries with keys: title, url, snippet.
    """
    ql = (query or "").strip().lower()
    if not ql:
        return []
    exts = {".md", ".txt", ".py", ".json", ".yson", ".ysonx"}
    default_skips = {
        "state", "logs", "__pycache__", ".venv", "venv", "qjson_agents/venv",
        "proc", "sys", "dev", "run", "tmp", "node_modules", ".git"
    }
    extra_skips = set((os.environ.get("QJSON_LOCAL_SEARCH_SKIP_DIRS", "").split(","))) if os.environ.get("QJSON_LOCAL_SEARCH_SKIP_DIRS") else set()
    skip_dirs = default_skips | {s.strip() for s in extra_skips if s.strip()}
    try:
        max_files = int(os.environ.get("QJSON_LOCAL_SEARCH_MAX_FILES", "5000"))
    except Exception:
        max_files = 5000
    results: List[Dict[str, str]] = []
    seen = 0
    roots = _parse_search_roots()
    for root in roots:
        for dirpath, dirnames, filenames in os.walk(root):
            rel_dir = os.path.relpath(dirpath, root)
            # prune skip dirs
            dirnames[:] = [d for d in dirnames if os.path.join(rel_dir, d).replace("\\", "/") not in skip_dirs and d not in skip_dirs]
            for fn in filenames:
                if os.path.splitext(fn)[1].lower() not in exts:
                    continue
                fpath = os.path.join(dirpath, fn)
                # Filename/relative-path match shortcut
                try:
                    rel_path = os.path.relpath(fpath, os.getcwd())
                except Exception:
                    rel_path = fpath
                rel_low = rel_path.lower()
                if ql in rel_low and len(results) < max_results:
                    results.append({
                        "title": rel_path,
                        "url": rel_path,
                        "snippet": "(filename match)",
                    })
                    seen += 1
                    if len(results) >= max_results or seen >= max_files:
                        break
                try:
                    with open(fpath, "r", encoding="utf-8", errors="ignore") as fh:
                        for _ln_no, line in enumerate(fh, 1):
                            if ql in line.lower():
                                try:
                                    rel = os.path.relpath(fpath, os.getcwd())
                                except Exception:
                                    rel = fpath
                                snippet = line.strip()
                                results.append({
                                    "title": f"{rel}",
                                    "url": rel,
                                    "snippet": snippet[:200],
                                })
                                break
                except Exception:
                    continue
                seen += 1
                if len(results) >= max_results or seen >= max_files:
                    break
            if len(results) >= max_results or seen >= max_files:
                break
        if len(results) >= max_results:
            break
    return results

def _strip_quotes(s: str) -> str:
    if len(s) >= 2 and ((s[0] == s[-1]) and s[0] in ('"', "'")):
        return s[1:-1]
    return s

def _langsearch_web(query: str, *, topk: int) -> List[Dict[str, str]]:
    import requests as _req
    key = os.environ.get("LANGSEARCH_API_KEY")
    if not key:
        raise RuntimeError("LANGSEARCH_API_KEY not set")
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    payload = {"query": query, "summary": True, "count": max(1, int(topk))}
    resp = _req.post("https://api.langsearch.com/v1/web-search", headers=headers, json=payload, timeout=8)
    resp.raise_for_status()
    data = resp.json()
    pages = (((data or {}).get("data") or {}).get("webPages") or {}).get("value") or []
    out: List[Dict[str, str]] = []
    for p in pages:
        if isinstance(p, dict):
            out.append({
                "title": str(p.get("name") or p.get("title") or p.get("url") or ""),
                "url": str(p.get("url") or ""),
                "snippet": str(p.get("summary") or p.get("snippet") or ""),
            })
    return out


def _perform_websearch(query: str, default_api: Any | None = None, fallback: Any | None = None) -> Dict[str, Any]:
    """Perform a web search prioritizing LangSearch; fall back to default_api or googlesearch, else local.

    Returns: {"query": str, "results": [{"title","url","snippet"}...]}
    """
    try:
        topk = int(os.environ.get("QJSON_WEB_TOPK", "5"))
    except Exception:
        topk = 5
    # LangSearch primary
    if os.environ.get("LANGSEARCH_API_KEY"):
        try:
            results = _langsearch_web(query, topk=topk)
            return {"query": query, "results": results[:topk]}
        except Exception:
            pass
    # default_api (if provided by host)
    if default_api is not None and hasattr(default_api, "google_web_search"):
        try:
            res = default_api.google_web_search(query=query)
            if isinstance(res, dict) and isinstance(res.get("results"), list):
                out: List[Dict[str, str]] = []
                for r in res["results"]:
                    if isinstance(r, dict):
                        out.append({
                            "title": str(r.get("title") or r.get("name") or r.get("url") or ""),
                            "url": str(r.get("url") or ""),
                            "snippet": str(r.get("snippet") or r.get("summary") or ""),
                        })
                return {"query": query, "results": out[:topk]}
        except Exception:
            pass
    # googlesearch fallback
    urls: List[str] = []
    if callable(fallback):
        try:
            urls = list(fallback(query))
        except Exception:
            urls = []
    else:
        try:
            from googlesearch import search as _gsearch  # type: ignore
            urls = list(_gsearch(query, num_results=topk))
        except Exception:
            urls = []
    out = [{"title": str(u), "url": str(u), "snippet": ""} for u in urls[:topk]]
    if not out:
        out = _local_repo_search(query, max_results=topk)
    return {"query": query, "results": out}


def _safe_truncate(text: str, cap: int) -> str:
    if cap <= 0:
        return text
    return text[:cap]


def _safe_read_local(path: str, max_bytes: int) -> str:
    try:
        p = Path(path)
        with p.open("rb") as f:
            data = f.read(max(1, max_bytes))
        return data.decode("utf-8", errors="ignore")
    except Exception as e:
        return f"[error reading local file: {e}]"


def _fetch_url(url: str, *, timeout: float = 6.0, max_bytes: int = 200 * 1024) -> Tuple[str, str]:
    """Fetch URL or local file with caps. Returns (text, content_type)."""
    if not url:
        return "", ""
    if url.startswith("http://") or url.startswith("https://"):
        req = _urlreq.Request(url, headers={"User-Agent": "qjson-agents/0.1"})
        try:
            with _urlreq.urlopen(req, timeout=timeout) as resp:
                ctype = resp.headers.get("Content-Type", "")
                data = resp.read(max(1, max_bytes))
                text = data.decode("utf-8", errors="ignore")
                return text, ctype
        except (_urlerr.HTTPError, _urlerr.URLError) as e:
            return f"[fetch error: {e}]", ""
        except Exception as e:
            return f"[fetch exception: {e}]", ""
    # Treat as local path
    return _safe_read_local(url, max_bytes), "text/plain"


def _arm_webopen_from_results(index: int, results_json: str, *, cap_chars: int | None = None, timeout_s: float | None = None, max_bytes: int | None = None) -> str:
    """Pick Nth result, fetch content, set one-shot injection env. Returns a preview string."""
    try:
        arr = json.loads(results_json)
        if not isinstance(arr, list):
            return "[webopen] No cached results available. Run /find or /crawl first."
    except Exception:
        return "[webopen] Invalid results cache. Run /find or /crawl again."
    if index < 1 or index > len(arr):
        return f"[webopen] Invalid index {index}. Choose 1..{len(arr)}."
    item = arr[index - 1] or {}
    url = str(item.get("url") or "").strip()
    title = str(item.get("title") or item.get("name") or url or f"Result {index}")
    # Resolve caps
    try:
        cap = cap_chars if cap_chars is not None else int(os.environ.get("QJSON_WEBOPEN_CAP", "12000"))
    except Exception:
        cap = 12000
    to = timeout_s if timeout_s is not None else float(os.environ.get("QJSON_WEBOPEN_TIMEOUT", "6"))
    mb = max_bytes if max_bytes is not None else int(os.environ.get("QJSON_WEBOPEN_MAX_BYTES", str(200 * 1024)))
    text, ctype = _fetch_url(url, timeout=to, max_bytes=mb)
    # If HTML, try to extract a clean outline/text for injection
    # One-shot override or default mode. Default is 'text' (outline extraction).
    mode_once = (os.environ.get("QJSON_WEBOPEN_MODE_ONCE") or "").strip().lower()
    mode_default = (os.environ.get("QJSON_WEBOPEN_DEFAULT") or "text").strip().lower()
    mode = mode_once or mode_default
    try:
        is_html_detected = (ctype and 'html' in ctype.lower()) or ('<html' in text.lower() and '</html' in text.lower())
    except Exception:
        is_html_detected = False
    # Decide parsing policy: raw | text | auto
    force_raw = (mode == 'raw')
    force_text = (mode == 'text')
    try:
        # Clear one-shot mode after consumption
        if mode_once:
            os.environ.pop("QJSON_WEBOPEN_MODE_ONCE", None)
    except Exception:
        pass
    if (force_text or (not force_raw and is_html_detected)):
        try:
            from .web_outliner import build_outline  # type: ignore
            outline = build_outline(text, url)
            ttl = outline.get('title') or title
            sub = outline.get('subtitle') or ''
            parts = []
            if ttl:
                parts.append(ttl)
            if sub:
                parts.append(sub)
            body_texts = []
            for sec in (outline.get('sections') or []):
                st = (sec.get('title') or '').strip()
                body = (sec.get('text') or '').strip()
                if st:
                    parts.append(f"## {st}")
                if body:
                    parts.append(body)
                    body_texts.append(body)
            cleaned = "\n\n".join([p for p in parts if isinstance(p, str) and p.strip()])
            has_body = any(isinstance(b, str) and b.strip() for b in body_texts)
            # Only replace with outline text if we extracted some body content
            if cleaned and has_body:
                text = cleaned
                # Override header to reflect outline title
                try:
                    if not os.environ.get("QJSON_WEBOPEN_HEADER"):
                        os.environ["QJSON_WEBOPEN_HEADER"] = f"### Web Page Outline: {ttl or title}"
                except Exception:
                    pass
        except Exception:
            # Fall back to raw text if outliner fails
            pass
    text = _safe_truncate(text, max(512, cap))
    # Arm one-shot injection
    os.environ["QJSON_WEBOPEN_TEXT_ONCE"] = text
    if not os.environ.get("QJSON_WEBOPEN_HEADER"):
        os.environ["QJSON_WEBOPEN_HEADER"] = f"### Web Page Content: {title}"
    # Also keep a small preview for the console
    preview = text[:300].replace("\n", " ")
    return f"[webopen] Loaded {len(text)} chars from {url} (type={ctype or 'unknown'}). Preview: {preview}"


def _fetch_result_content(index: int, results_json: str, *, cap_chars: int | None = None, timeout_s: float | None = None, max_bytes: int | None = None) -> Dict[str, str]:
    try:
        arr = json.loads(results_json)
        if not isinstance(arr, list):
            return {"error": "no_cache"}
    except Exception:
        return {"error": "bad_cache"}
    if index < 1 or index > len(arr):
        return {"error": "bad_index"}
    item = arr[index - 1] or {}
    url = str(item.get("url") or "").strip()
    title = str(item.get("title") or item.get("name") or url or f"Result {index}")
    try:
        cap = cap_chars if cap_chars is not None else int(os.environ.get("QJSON_WEBOPEN_CAP", "12000"))
    except Exception:
        cap = 12000
    to = timeout_s if timeout_s is not None else float(os.environ.get("QJSON_WEBOPEN_TIMEOUT", "6"))
    mb = max_bytes if max_bytes is not None else int(os.environ.get("QJSON_WEBOPEN_MAX_BYTES", str(200 * 1024)))
    text, ctype = _fetch_url(url, timeout=to, max_bytes=mb)
    text = _safe_truncate(text, max(512, cap))
    return {"url": url, "title": title, "text": text, "content_type": ctype or ""}


def _parse_indices(tokens: List[str]) -> List[int]:
    out: List[int] = []
    for tk in tokens:
        for seg in tk.split(','):
            seg = seg.strip()
            if not seg:
                continue
            if '-' in seg:
                a, b = seg.split('-', 1)
                try:
                    ia = int(a); ib = int(b)
                except Exception:
                    continue
                if ia <= ib:
                    out.extend(list(range(ia, ib + 1)))
                else:
                    out.extend(list(range(ib, ia + 1)))
            else:
                try:
                    out.append(int(seg))
                except Exception:
                    continue
    # de-dup preserve order
    seen = set()
    uniq: List[int] = []
    for n in out:
        if n not in seen and n > 0:
            uniq.append(n); seen.add(n)
    return uniq


def _engine_find(cmdline: str, *, default_mode: str = "online", agent_id: str | None = None, default_api: Any | None = None) -> int:
    """Unified search/crawl engine.

    Usage examples (cmdline):
      'mode=online fractal ai'
      'mode=local fractal'
      'https://example.com depth=1 pages=5 export=./out'
    """
    parts = [p for p in cmdline.split() if p]
    if not parts:
        _print("Usage: /find <QUERY or URL...> [mode=online|local] [depth=N] [pages=M] [export=DIR]")
        return 2
    mode = default_mode
    seeds: List[str] = []
    depth = None
    pages = None
    export_dir = None
    query_tokens: List[str] = []
    for p in parts:
        if p.startswith("mode="):
            v = p.split("=", 1)[1].strip().lower()
            if v in ("online", "local"):
                mode = v
        elif p.startswith("depth="):
            try:
                depth = max(0, int(p.split("=", 1)[1]))
            except Exception:
                pass
        elif p.startswith("pages="):
            try:
                pages = max(1, int(p.split("=", 1)[1]))
            except Exception:
                pass
        elif p.startswith("export="):
            export_dir = p.split("=", 1)[1]
        elif p.startswith("http://") or p.startswith("https://"):
            seeds.append(p)
        else:
            query_tokens.append(p)
    # Online BFS crawl when seeds are present
    if seeds:
        try:
            d = depth if depth is not None else 1
            m = pages if pages is not None else 10
            cr = Crawler(rate_per_host=float(os.environ.get("QJSON_CRAWL_RATE", "1.0")))
            outlines = cr.crawl(seeds, max_depth=d, max_pages=m)
            tgt = agent_id or os.environ.get("QJSON_AGENT_ID") or "WebCrawler"
            for o in outlines:
                try:
                    upsert_outline(tgt, o)
                except Exception:
                    pass
            if export_dir:
                try:
                    outd = Path(export_dir)
                    outd.mkdir(parents=True, exist_ok=True)
                    import re
                    def _slug(s: str) -> str:
                        s = (s or "untitled").strip().lower()
                        s = re.sub(r"[^a-z0-9]+","-", s)
                        return s.strip("-") or "doc"
                    for o in outlines:
                        title = o.get("title") or o.get("url") or "page"
                        (outd / (_slug(title)[:64] + ".json")).write_text(json.dumps(o, ensure_ascii=False, indent=2), encoding="utf-8")
                    _print(f"[find] exported {len(outlines)} outline(s) -> {outd}")
                except Exception:
                    pass
            pages_list = [{
                "title": (o.get("title") or o.get("url") or ""),
                "url": (o.get("url") or ""),
                "snippet": ((o.get("sections") or [{}])[0].get("text") or "")[:240],
            } for o in outlines]
            payload = json.dumps(pages_list[: int(os.environ.get("QJSON_WEB_TOPK", "5"))])
            os.environ["QJSON_WEBSEARCH_RESULTS_ONCE"] = payload
            os.environ["QJSON_WEBRESULTS_CACHE"] = payload
            os.environ["QJSON_WEBSEARCH_HEADER"] = "### Search Results (Online BFS)"
            # Persist for exec flows
            try:
                _save_persistent_env("QJSON_WEBRESULTS_CACHE", payload)
                _save_persistent_env("QJSON_WEBSEARCH_RESULTS_ONCE", payload)
                _save_persistent_env("QJSON_WEBSEARCH_HEADER", "### Search Results (Online BFS)")
            except Exception:
                pass
            # Print results honoring web top-k setting
            try:
                print_k = max(1, int(os.environ.get("QJSON_WEB_TOPK", "5")))
            except Exception:
                print_k = 5
            _print(f"[find] Top {min(print_k, len(pages_list))} web result(s) for crawl seeds (k={print_k}):")
            for i, r in enumerate(pages_list[:print_k], 1):
                _print(f"--- Result {i} ---\nTitle: {r['title'] or 'N/A'}\nURL: {r['url'] or 'N/A'}\nSnippet: {r['snippet']}")
            return 0
        except Exception as e:
            _print(f"[find] crawl error: {e}")
            return 1
    # Otherwise, perform online/local search
    # Normalize quotes in tokens and full query
    query = " ".join(_strip_quotes(t) for t in query_tokens).strip()
    query = _strip_quotes(query)
    if not query:
        _print("Usage: /find <QUERY> [mode=online|local]")
        return 2
    if mode == "local":
        res = _local_repo_search(query, max_results=int(os.environ.get("QJSON_WEB_TOPK", "5")))
        payload = json.dumps([{"title": r.get("title"), "url": r.get("url"), "snippet": r.get("snippet")} for r in res])
        os.environ["QJSON_WEBSEARCH_RESULTS_ONCE"] = payload
        os.environ["QJSON_WEBRESULTS_CACHE"] = payload
        os.environ["QJSON_WEBSEARCH_HEADER"] = "### Search Results (Local)"
        # Persist cache/header for exec flows
        try:
            _save_persistent_env("QJSON_WEBRESULTS_CACHE", payload)
            _save_persistent_env("QJSON_WEBSEARCH_RESULTS_ONCE", payload)
            _save_persistent_env("QJSON_WEBSEARCH_HEADER", "### Search Results (Local)")
        except Exception:
            pass
        if not res:
            _print(f"[find] No local matches for '{query}'")
            return 0
        try:
            k_loc = int(os.environ.get("QJSON_WEB_TOPK", "5"))
        except Exception:
            k_loc = 5
        _print(f"[find] Top {len(res)} local result(s) for '{query}' (k={k_loc}):")
        for i, r in enumerate(res, 1):
            _print(f"{i:02d}) {r['title']}\n    {r['url']}\n    {r['snippet']}")
        return 0
    else:
        try:
            res = _perform_websearch(query, default_api=default_api)
            results = res.get("results") or []
            topk = int(os.environ.get("QJSON_WEB_TOPK", "5")) if os.environ.get("QJSON_WEB_TOPK") else 5
            payload = json.dumps(results[: topk])
            os.environ["QJSON_WEBSEARCH_RESULTS_ONCE"] = payload
            os.environ["QJSON_WEBRESULTS_CACHE"] = payload
            os.environ["QJSON_WEBSEARCH_HEADER"] = "### Search Results (Online)"
            # Persist cache/header for exec flows
            try:
                _save_persistent_env("QJSON_WEBRESULTS_CACHE", payload)
                _save_persistent_env("QJSON_WEBSEARCH_RESULTS_ONCE", payload)
                _save_persistent_env("QJSON_WEBSEARCH_HEADER", "### Search Results (Online)")
            except Exception:
                pass
            if not results:
                _print(f"[find] No web results for '{query}'")
                return 0
            _print(f"[find] Top {min(topk, len(results))} web result(s) for '{query}' (k={topk}):")
            for i, r in enumerate(results[:topk], 1):
                ttl = r.get("title") or r.get("url") or "(untitled)"
                url = r.get("url") or ""
                snip = r.get("snippet") or ""
                _print(f"{i:02d}) {ttl}\n    {url}\n    {snip[:160]}")
            # Optionally fetch top-N pages using crawler for indexing/enrichment
            fetch_flag = os.environ.get("QJSON_FIND_FETCH", "1") == "1"
            try:
                fetch_n = max(0, int(os.environ.get("QJSON_FIND_FETCH_TOP_N", "1")))
            except Exception:
                fetch_n = 1
            if fetch_flag and fetch_n > 0:
                seeds2 = [r.get("url") for r in results if r.get("url")][:fetch_n]
                if seeds2:
                    cr = Crawler(rate_per_host=float(os.environ.get("QJSON_CRAWL_RATE", "1.0")))
                    outlines = cr.crawl(seeds2, max_depth=0, max_pages=fetch_n)
                    tgt = agent_id or os.environ.get("QJSON_AGENT_ID") or "WebCrawler"
                    for o in outlines:
                        try:
                            upsert_outline(tgt, o)
                        except Exception:
                            pass
                    _print(f"[find] fetched and indexed top {len(outlines)} page(s)")
            return 0
        except Exception as e:
            _print(f"[find] web error: {e}")
            return 1


def _env_store_path() -> Path:
    try:
        return agents_home() / "env.json"
    except Exception:
        return Path.cwd() / "state" / "env.json"


def _load_persistent_env() -> None:
    """Load persisted env overrides from state/env.json into os.environ (strings only)."""
    try:
        p = _env_store_path()
        if p.exists():
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                for k, v in data.items():
                    if isinstance(k, str) and isinstance(v, str) and k:
                        os.environ[k] = v
    except Exception:
        pass


def _save_persistent_env(k: str, v: str) -> None:
    try:
        p = _env_store_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        data: Dict[str, Any] = {}
        if p.exists():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                data = {}
        data[str(k)] = str(v)
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass

def cmd_init(args: argparse.Namespace, default_api: Any = None) -> int:
    manifest_path = Path(args.manifest)
    manifest = load_manifest(manifest_path)
    if args.model:
        manifest.setdefault("runtime", {})["model"] = args.model
    agent = Agent(manifest)
    _print(f"Initialized agent '{agent.agent_id}' in {agent_dir(agent.agent_id)}")
    return 0


def cmd_chat(args: argparse.Namespace, default_api: Any = None) -> int:
    agent_id = args.id
    manifest_path = Path(args.manifest) if args.manifest else None

    # --- Model validation and selection ---
    # Load any persisted env overrides early
    _load_persistent_env()
    try:
        client = OllamaClient()
        models = client.tags()
        if not models:
            _print("No local models found via /api/tags. Pull one with 'ollama pull <model>'.")
            return 1
    except Exception as e:
        _print(f"[models] error: could not connect to Ollama. Is it running? Details: {e}")
        return 1

    model_names = [m.get("name") for m in models if m.get("name")]
    chosen_model = None
    if args.model and args.model != "auto":
        if args.model in model_names:
            chosen_model = args.model
            _print(f"[models] using specified model: {chosen_model}")
        else:
            _print(f"[models] error: model '{args.model}' not found in Ollama. Available models: {model_names}")
            return 1
    else:
        # Auto-select a default model
        chosen_model = model_names[0]
        _print(f"[models] selected default: {chosen_model}")

    if manifest_path and manifest_path.exists():
        if manifest_path.suffix.lower() in (".yson", ".ysonx"):
            prev_allow = os.environ.get("QJSON_ALLOW_YSON_EXEC")
            try:
                if getattr(args, "allow_yson_exec", False):
                    os.environ["QJSON_ALLOW_YSON_EXEC"] = "1"
                else:
                    os.environ.pop("QJSON_ALLOW_YSON_EXEC", None)
            except Exception:
                pass
            try:
                manifest = yson_to_manifest(manifest_path)
            finally:
                try:
                    if prev_allow is None:
                        os.environ.pop("QJSON_ALLOW_YSON_EXEC", None)
                    else:
                        os.environ["QJSON_ALLOW_YSON_EXEC"] = prev_allow
                except Exception:
                    pass
        else:
            manifest = load_manifest(manifest_path)
        rt = manifest.setdefault("runtime", {})
        rt["model"] = chosen_model # Set the validated model
        if getattr(args, "max_tokens", None):
            try:
                rt["num_predict"] = int(args.max_tokens)
            except Exception:
                pass
        agent = Agent(manifest)
    else:
        # Load manifest from state if exists
        mpath = agent_dir(agent_id) / "manifest.json"
        if not mpath.exists():
            _print("No manifest found. Provide --manifest to initialize.")
            return 2
        manifest = json.loads(mpath.read_text(encoding="utf-8"))
        rt = manifest.setdefault("runtime", {})
        rt["model"] = chosen_model # Set the validated model
        if getattr(args, "max_tokens", None):
            try:
                rt["num_predict"] = int(args.max_tokens)
            except Exception:
                pass
        agent = Agent(manifest)

    # Load plugins
    # Define a wrapper for google_web_search that can be passed to plugins
    def _google_web_search_wrapper(query: str) -> dict:
        # This function will only be called if default_api is available in the global scope
        # which it is, because the Gemini CLI agent provides it.
        return default_api.google_web_search(query=query)

    tools = {"google_web_search": _google_web_search_wrapper}
    plugins = load_plugins(tools=tools)
    plugin_commands = {}
    for plugin in plugins:
        plugin_commands.update(plugin.get_commands())

    if getattr(args, "once", None):
        # Non-interactive one-shot prompt
        user = str(args.once)

        # Handle plugin commands
        parts = user.split()
        command = parts[0]
        if command in plugin_commands:
            try:
                result = plugin_commands[command](*parts[1:])
                _print(result)
                return 0
            except Exception as e:
                _print(f"Error executing plugin command {command}: {e}")
                return 1

        # Deprecated /websearch removed; use unified /find instead

        try:
            # Use a mock client when --model mock-llm is set
            llm_client = None
            if (args.model or "").strip().lower() == "mock-llm":
                class _Mock:
                    def chat(self, *, model: str, messages: list[dict], options: dict | None = None, stream: bool = False) -> dict:
                        prev_user = next((m.get("content", "") for m in reversed(messages) if m.get("role") == "user"), "")
                        return {"message": {"role": "assistant", "content": f"(mock) {prev_user[:120]}"}}
                llm_client = _Mock()
            reply = agent.chat_turn(user, client=llm_client, model_override=(chosen_model or args.model))
        except Exception as e:
            _print(f"[error] {e}")
            return 1
        _print(reply)
        return 0

    _print(f"Chatting with {agent.agent_id}. Type /help for commands; /exit to quit; /fork <NEW_ID> to fork.")
    # Persist agent id to env for plugins (crawl/indexing)
    try:
        os.environ["QJSON_AGENT_ID"] = agent.agent_id
    except Exception:
        pass
    # Session-local options
    mem_truncate_limit: int | None = 8000  # default truncate injected mem to 8k chars
    include_sys_enabled: bool = False      # include recent system memory in chat context
    include_sys_count: int = 3             # how many system entries to include
    include_sys_auto: bool = False         # auto-include next injected file's system messages
    include_sys_next_n: int | None = None  # one-shot include count for the next prompt
    include_max_chars: int = 12000         # safety cap for included content size
    try:
        env_cap = os.environ.get("QJSON_INCLUDE_CAP")
        if env_cap:
            include_max_chars = max(128, int(env_cap))
    except Exception:
        pass
    include_max_msgs: int = 8              # upper bound on number of messages included
    try:
        env_m = os.environ.get("QJSON_INCLUDE_MAX_MSGS")
        if env_m:
            include_max_msgs = max(1, int(env_m))
    except Exception:
        pass
    # YSON logic exec toggle (session-level): reflect env and CLI flag
    yson_exec_allowed = os.environ.get("QJSON_ALLOW_YSON_EXEC") == "1"
    if getattr(args, "allow_yson_exec", False):
        os.environ["QJSON_ALLOW_YSON_EXEC"] = "1"
        yson_exec_allowed = True
    # Persona logic hooks (entrypoints) toggle
    allow_logic = bool(getattr(args, "allow_logic", False) or os.environ.get("QJSON_ALLOW_LOGIC") == "1")
    logic_mode = (getattr(args, "logic_mode", None) or os.environ.get("QJSON_LOGIC_MODE") or "assist").lower()
    if logic_mode not in ("assist", "replace"):
        logic_mode = "assist"
    persona_logic = None
    persona_requires: list[str] = []
    logic_state_path = agent_dir(agent.agent_id) / "logic_state.json"
    def _import_symbol(path: str):
        import importlib
        try:
            mod, fn = path.split(":", 1)
            m = importlib.import_module(mod)
            return getattr(m, fn)
        except Exception:
            return None
    def _load_logic_state() -> Dict[str, Any]:
        try:
            return json.loads(logic_state_path.read_text(encoding="utf-8"))
        except Exception:
            return {}
    def _save_logic_state(st: Dict[str, Any]) -> None:
        try:
            logic_state_path.write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass
    try:
        lg = agent.manifest.get("logic") if isinstance(agent.manifest, dict) else None
        eps = (lg or {}).get("entrypoints") if isinstance(lg, dict) else None
        if allow_logic and isinstance(eps, dict):
            persona_requires = list((lg or {}).get("requires") or [])
            for mod in persona_requires:
                try:
                    __import__(mod)
                except Exception:
                    pass
            if isinstance(eps.get("on_message"), str):
                persona_logic = _import_symbol(eps["on_message"])  # type: ignore
        if allow_logic and persona_logic:
            _print("[logic] hooks enabled (on_message)")
    except Exception:
        persona_logic = None
    # Role for including memory: system (default) or user
    include_as_role: str = "system"
    stream_enabled: bool = False
    # Retrieval toggles (env-scoped)
    retrieval_enabled: bool = os.environ.get("QJSON_RETRIEVAL") == "1"
    try:
        retrieval_top_k: int = max(1, int(os.environ.get("QJSON_RETRIEVAL_TOPK", "6")))
    except Exception:
        retrieval_top_k = 6
    try:
        retrieval_decay: float = float(os.environ.get("QJSON_RETRIEVAL_DECAY", "0.0"))
    except Exception:
        retrieval_decay = 0.0
    try:
        retrieval_minscore: float = float(os.environ.get("QJSON_RETRIEVAL_MINSCORE", "0.25"))
    except Exception:
        retrieval_minscore = 0.25



    # Unified search engine defaults
    engine_mode = os.environ.get("QJSON_ENGINE_DEFAULT", "online").strip().lower()
    if engine_mode not in ("online", "local"):
        engine_mode = "online"

    while True:
        try:
            user = input("you > ").strip()
        except (EOFError, KeyboardInterrupt):
            _print("")
            break
        if not user:
            continue
        if user.lower() in {"/exit", ":q", ":q!"}:
            break

        # Unified engine first-class commands
        parts = user.split()
        command = parts[0]
        if command == "/engine":
            val = user.replace("/engine", "", 1).strip().lower()
            # Accept '/engine local' or '/engine online' as shorthand
            if val in ("online","local"):
                m = val
                engine_mode = m
                os.environ["QJSON_ENGINE_DEFAULT"] = m
                try:
                    _save_persistent_env("QJSON_ENGINE_DEFAULT", m)
                except Exception:
                    pass
                _print(f"[engine] mode set to {m}")
            elif val.startswith("mode="):
                m = val.split("=",1)[1].strip()
                if m in ("online","local"):
                    engine_mode = m
                    os.environ["QJSON_ENGINE_DEFAULT"] = m
                    # Persist for future /find calls that reload system settings
                    try:
                        _save_persistent_env("QJSON_ENGINE_DEFAULT", m)
                    except Exception:
                        pass
                    _print(f"[engine] mode set to {m}")
                else:
                    _print("Usage: /engine mode=online|local")
            else:
                # Reflect persisted system settings when showing mode
                try:
                    _load_persistent_env()
                except Exception:
                    pass
                eff_mode = os.environ.get("QJSON_ENGINE_DEFAULT", engine_mode)
                _print(f"[engine] mode={eff_mode}")
            continue
        if command == "/find":
            # Reload persisted settings so /find honors system config (mode, top-k, etc.)
            try:
                _load_persistent_env()
            except Exception:
                pass
            arg = user.replace("/find", "", 1).strip()
            eff_mode = os.environ.get("QJSON_ENGINE_DEFAULT", engine_mode)
            # Announce current top-k for clarity
            try:
                k_echo = int(os.environ.get("QJSON_WEB_TOPK", "5"))
            except Exception:
                k_echo = 5
            _print(f"[engine] k={k_echo}")
            _engine_find(arg, default_mode=eff_mode, agent_id=agent.agent_id, default_api=default_api)
            continue
        if command == "/open":
            # Reload persisted env only if no current results are cached in-session
            if not os.environ.get("QJSON_WEBRESULTS_CACHE") and not os.environ.get("QJSON_WEBSEARCH_RESULTS_ONCE"):
                try:
                    _load_persistent_env()
                except Exception:
                    pass
            arg = user.replace("/open", "", 1).strip()
            toks = [t for t in arg.split() if t]
            ingest_flag = False
            mode_once: str | None = None
            idx_tokens: List[str] = []
            if toks:
                for t in toks:
                    tl = t.lower()
                    if tl == "ingest":
                        ingest_flag = True
                        continue
                    if tl in ("raw", "text"):
                        mode_once = tl
                        continue
                    idx_tokens.append(t)
            else:
                _print("Usage: /open N [ingest] | /open ingest N [M ...]")
                continue
            cache = os.environ.get("QJSON_WEBRESULTS_CACHE") or os.environ.get("QJSON_WEBSEARCH_RESULTS_ONCE")
            if not cache:
                _print("[open] No cached results. Run /find or /crawl first.")
                continue
            indices = _parse_indices(idx_tokens)
            if not indices:
                _print("Usage: /open N [ingest] | /open ingest N [M ...]")
                continue
            # Inject the last requested index; ingest optionally all
            last = indices[-1]
            if mode_once:
                try:
                    os.environ["QJSON_WEBOPEN_MODE_ONCE"] = mode_once
                except Exception:
                    pass
            os.environ.setdefault("QJSON_WEBOPEN_HEADER", "### Search Page Content")
            _print(_arm_webopen_from_results(last, cache))
            if ingest_flag:
                try:
                    from .web_outliner import build_outline as _build_outline
                    from .web_indexer import upsert_outline as _upsert_outline
                    from .retrieval import add_memory as _add_mem
                except Exception:
                    _build_outline = None
                    _upsert_outline = None
                    _add_mem = None
                ok = 0
                for i in indices:
                    info = _fetch_result_content(i, cache)
                    if info.get("error"):
                        continue
                    url = info.get("url") or ""
                    title = info.get("title") or url
                    text = info.get("text") or ""
                    ctype = (info.get("content_type") or "").lower()
                    ingested = False
                    # Prefer HTML outline/index
                    if _build_outline and _upsert_outline and ("html" in ctype or ("<html" in text.lower() and "</html" in text.lower())):
                        try:
                            outline = _build_outline(text, url)
                            _upsert_outline(agent.agent_id, outline)
                            ingested = True
                        except Exception:
                            ingested = False
                    # Fallback: raw text into memory + retrieval
                    if not ingested and _add_mem:
                        try:
                            agent._log_message("system", f"[web-open] {title}\n\n{text}", {"source": "open_ingest", "url": url})
                            _add_mem(agent.agent_id, text, {"source": "open_ingest", "url": url})
                            ingested = True
                        except Exception:
                            pass
                    if ingested:
                        ok += 1
                _print(f"[open] ingested {ok}/{len(indices)} page(s) into {agent.agent_id}")
            continue
        # Deprecated aliases
        # Deprecated /websearch, /webopen, /crawlopen removed; use /find and /open

        # Handle plugin commands (after core)
        parts = user.split()
        command = parts[0]
        if command in plugin_commands:
            try:
                result = plugin_commands[command](*parts[1:])
                _print(result)
            except Exception as e:
                _print(f"Error executing plugin command {command}: {e}")
            continue

        # Help
        if user.lower().startswith("/help"):
            help_text = """
Slash commands:
  /help                 Show this help
  /fork <NEW_ID>        Fork current agent into NEW_ID
  /inject <PATH>        Ingest files (ysonx/json/yaml/txt) into system context
  /inject_py <PATH>     Ingest Python files into system context (no exec)
  /inject_mem <PATH>    Persist file contents as 'system' messages in memory.jsonl
  /save_mem <TEXT>      Persist arbitrary text as a 'system' message in memory.jsonl
  /mem_trunc [on|off|N] Toggle or set inject_mem truncation (on=8000 chars, off=no limit, N=limit)
  /lsmem                List in-memory ingested items for this agent
  /include_sys [on|off|N|auto] Include recent system memory in chat context (N entries); 'auto' to include next /inject_mem automatically
  /include_as [system|user]  Choose how included memory is injected (system or user role)
  /show_sys [N]         Preview the last N system messages that would be included
  /settings             Show include_as, include_sys, auto, mem_trunc, yson_exec, cap
  /stream [on|off]      Toggle streaming partial output (if supported by model)
  /preflight <TEXT>     Estimate prompt length and latency before sending
  /yson_exec [on|off]   Enable/disable execution of YSON logic blocks for this session (unsafe; off by default)
  /allow_logic [on|off] Enable/disable persona logic hooks for this session
  /logic_mode [assist|replace] Set hook usage: assist=anchor LLM, replace=bypass LLM
  /logic_ping <TEXT>    Run build_reply(TEXT, persona) via hook and print the result (no model)
  /retrieval [on|off|once [QUERY]|k=<N>|decay=<F>|min=<F>|ivf=<on|off>|ivf_k=<K>|nprobe=<N>|thresh=<N>]
               Toggle retrieval, arm one-shot with optional QUERY, and tune IVF/FMM settings
  /engine [mode=online|local]   Show/set default search mode
  /find <QUERY or URL...> [mode=online|local depth=N pages=M export=DIR]  Unified search/crawl engine; injects results for next prompt
  /open N [ingest] [raw|text]  Fetch result N's content; 'ingest' indexes it; 'raw' injects HTML, 'text' forces outline
  /setenv KEY=VALUE      Set an environment variable for this session (e.g., LANGSEARCH_API_KEY)
  /langsearch key <KEY>  Set LANGSEARCH_API_KEY for the LangSearch /crawl plugin
  /engine_scope show|add <PATH...>|set <PATH...>|clear   Configure local search roots for local mode
  /truth [on|off]       Toggle a one-line truth note about local/fractal runtime
  /exit                 Quit chat
            """.strip()
            if plugin_commands:
                help_text += "\n\nPlugin commands:\n"
                for cmd, func in plugin_commands.items():
                    help_text += f"  {cmd} - {func.__doc__.strip() if func.__doc__ else 'No description'}\n"
            _print(help_text)
            continue
        # In-chat ingestion commands
        if user.startswith("/scan"):
            path = user.replace("/scan", "", 1).strip() or "."
            try:
                from .ingest_manager import scan_path
                targets = scan_path(path, [".json", ".yson", ".ysonx", ".txt", ".md", ".py"], recursive=True)
                if not targets:
                    _print(f"[scan] No valid files at: {path}")
                else:
                    _print(f"[scan] Found {len(targets)} valid file(s):")
                    for i, fp in enumerate(targets, 1):
                        try:
                            sz = Path(fp).stat().st_size
                        except Exception:
                            sz = 0
                        _print(f"{i:02d}) {fp} ({sz/1024:.1f} KB)")
            except Exception as e:
                _print(f"[scan error] {e}")
            continue
        if user.startswith("/inject_py"):
            path = user.replace("/inject_py", "", 1).strip() or "."
            try:
                from .ingest_manager import ingest_path_py_recursive
                n = ingest_path_py_recursive(path, agent_id=agent.agent_id, truncate_limit=mem_truncate_limit)
                if include_sys_auto and n > 0:
                    include_sys_next_n = n
                    _print(f"[include_sys] Auto will include last {n} system message(s) on next prompt.")
            except Exception as e:
                _print(f"[inject_py error] {e}")
            continue
        if user.startswith("/inject_mem"):
            path = user.replace("/inject_mem", "", 1).strip() or "."
            try:
                from .ingest_manager import list_files_in_path, read_file
                files = list_files_in_path(path)
                if not files:
                    _print(f"[inject_mem] No files at: {path}")
                    continue
                count = 0
                for fp in files:
                    try:
                        raw = read_file(fp)
                        if isinstance(mem_truncate_limit, int) and mem_truncate_limit > 0 and len(raw) > mem_truncate_limit:
                            preview = raw[:mem_truncate_limit] + "\n...[truncated]..."
                        else:
                            preview = raw
                        content = f"[inject_mem] {fp}\n\n" + preview
                        agent._log_message("system", content, {"source": "inject_mem", "path": fp})
                        count += 1
                    except Exception as ie:
                        _print(f"[inject_mem error] {ie}")
                _print(f"[inject_mem] Wrote {count} system message(s) from {path} into memory.jsonl")
                if include_sys_auto and count > 0:
                    include_sys_next_n = count
                    _print(f"[include_sys] Auto will include last {count} system message(s) on next prompt.")
            except Exception as e:
                _print(f"[inject_mem error] {e}")
            continue
        if user.startswith("/inject") and not user.startswith("/inject_py"):
            path = user.replace("/inject", "", 1).strip() or "."
            try:
                from .ingest_manager import ingest_path_recursive
                n = ingest_path_recursive(path, agent_id=agent.agent_id, truncate_limit=mem_truncate_limit)
                if include_sys_auto and n > 0:
                    include_sys_next_n = n
                    _print(f"[include_sys] Auto will include last {n} system message(s) on next prompt.")
            except Exception as e:
                _print(f"[inject error] {e}")
            continue
        if user.startswith("/save_mem"):
            text = user.replace("/save_mem", "", 1).strip()
            if not text:
                _print("Usage: /save_mem <TEXT>")
                continue
            try:
                agent._log_message("system", text, {"source": "save_mem"})
                _print("[save_mem] Saved text to memory.jsonl as system message.")
                if include_sys_auto:
                    include_sys_next_n = 1
                    _print("[include_sys] Auto will include last 1 system message on next prompt.")
            except Exception as e:
                _print(f"[save_mem error] {e}")
            continue
        if user.startswith("/mem_trunc"):
            arg = user.replace("/mem_trunc", "", 1).strip().lower()
            if not arg:
                status = "off" if not mem_truncate_limit else f"on ({mem_truncate_limit})"
                _print(f"[mem_trunc] Current truncation: {status}")
                continue
            if arg in ("off", "no", "0"):
                mem_truncate_limit = None
                _print("[mem_trunc] Truncation disabled.")
            elif arg in ("on", "yes"):
                mem_truncate_limit = 8000
                _print("[mem_trunc] Truncation enabled (8000 chars).")
            else:
                try:
                    limit = int(arg)
                    mem_truncate_limit = max(1, limit)
                    _print(f"[mem_trunc] Truncation set to {mem_truncate_limit} chars.")
                except Exception:
                    _print("[mem_trunc] Invalid argument. Use on|off|<N>.")
            continue
        if user.startswith("/lsmem"):
            try:
                from .ingest_manager import list_agent_memory
                list_agent_memory(agent.agent_id)
            except Exception as e:
                _print(f"[lsmem error] {e}")
            continue
        if user.startswith("/show_sys"):
            arg = user.replace("/show_sys", "", 1).strip()
            try:
                n = int(arg) if arg else include_sys_count
            except Exception:
                n = include_sys_count
            try:
                from .memory import tail_jsonl
                sys_msgs = [m for m in tail_jsonl(agent_dir(agent.agent_id) / "memory.jsonl", 256) if m.get("role") == "system"]
                take = sys_msgs[-max(1, n):]
                _print(f"[show_sys] Showing {len(take)} system message(s):")
                for i, m in enumerate(take, 1):
                    src = (m.get('meta') or {}).get('source', 'system')
                    preview = (m.get('content') or '')[:400]
                    _print(f"{i:02d}) source={src} len={len(m.get('content',''))} preview=\n{preview}")
            except Exception as e:
                _print(f"[show_sys error] {e}")
            continue
        if user.startswith("/settings") and "edit" not in user:
            memtr = "off" if not mem_truncate_limit else f"on({mem_truncate_limit})"
            inc = f"on({include_sys_count})" if include_sys_enabled else "off"
            auto = "on" if include_sys_auto else "off"
            _print(
                f"[settings] include_as={include_as_role} include_sys={inc} auto={auto} mem_trunc={memtr} yson_exec={'on' if yson_exec_allowed else 'off'} cap={include_max_chars} retrieval={'on' if retrieval_enabled else 'off'} k={retrieval_top_k} decay={retrieval_decay} min={retrieval_minscore}"
            )
            # Telemetry: memory file size and prompt length estimate for next turn (baseline)
            try:
                mpath = agent_dir(agent.agent_id) / "memory.jsonl"
                msize = mpath.stat().st_size if mpath.exists() else 0
                def _hr(n: int) -> str:
                    for unit in ("B","KB","MB","GB","TB"):
                        if n < 1024 or unit == "TB":
                            return f"{n:.1f} {unit}" if unit != "B" else f"{n} {unit}"
                        n /= 1024.0
                    return f"{n} B"
                # Build a baseline prompt estimation using current inclusion
                system_txt = agent._system_prompt()
                sys_len = len(system_txt)
                from .memory import tail_jsonl as _tail
                hist = _tail(mpath, 32)
                hist_len = sum(len(h.get('content','')) for h in hist if h.get('role') in ("user","assistant"))
                # Inclusion build (like in preflight)
                extra_len = 0
                n_to_include = include_sys_next_n if include_sys_next_n is not None else (include_sys_count if include_sys_enabled else None)
                if n_to_include:
                    sys_msgs = [m for m in _tail(mpath, 256) if m.get("role") == "system"]
                    take_n = min(max(1, int(n_to_include)), include_max_msgs)
                    take = sys_msgs[-take_n:]
                    total = 0
                    for m in take:
                        seg = f"[mem:{(m.get('meta') or {}).get('source','system')}]\n{m.get('content','')}"
                        room = include_max_chars - total if include_max_chars else None
                        if isinstance(room, int) and room <= 0:
                            break
                        if isinstance(room, int) and len(seg) > room:
                            seg = seg[:room]
                        total += len(seg)
                    extra_len = total
                prompt_chars = sys_len + hist_len + extra_len
                prompt_tokens = (prompt_chars + 3) // 4
                _print(f"[telemetry] memory.jsonl={_hr(msize)} est_prompt_chars={prompt_chars} est_prompt_tokens≈{prompt_tokens} incl_chars={extra_len} hist_chars={hist_len}")
            except Exception:
                pass
            continue
        if user.startswith("/include_cap"):
            arg = user.replace("/include_cap", "", 1).strip()
            try:
                include_max_chars = max(128, int(arg))
                _print(f"[include_cap] cap set to {include_max_chars} chars")
            except Exception:
                _print("Usage: /include_cap <N>")
            continue
        if user.startswith("/retrieval"):
            arg = user.replace("/retrieval", "", 1).strip()
            if not arg:
                _print(f"[retrieval] {'on' if retrieval_enabled else 'off'} k={retrieval_top_k} decay={retrieval_decay} min={retrieval_minscore}")
                continue
            val = arg.lower()
            # One-shot retrieval: '/retrieval once [QUERY] [k=.. min=..]' sets env for next prompt only
            if val.startswith("once") or val.startswith("one") or val.startswith("next"):
                os.environ["QJSON_RETRIEVAL_ONCE"] = "1"
                raw_parts = val.split()
                parts = [p for p in raw_parts[1:] if p]
                # Collect free-text QUERY tokens (without '=') into a hint for the next search
                hint_tokens = [p for p in parts if "=" not in p]
                if hint_tokens:
                    os.environ["QJSON_RETRIEVAL_QUERY_HINT"] = " ".join(hint_tokens)
                for p in parts:
                    if "=" not in p:
                        continue
                    k, v = p.split("=", 1)
                    if k == "k":
                        try:
                            retrieval_top_k = max(1, int(v))
                            os.environ["QJSON_RETRIEVAL_TOPK"] = str(retrieval_top_k)
                        except Exception:
                            pass
                    elif k == "decay":
                        try:
                            retrieval_decay = float(v)
                            os.environ["QJSON_RETRIEVAL_DECAY"] = str(retrieval_decay)
                        except Exception:
                            pass
                    elif k in ("min","minscore"):
                        try:
                            retrieval_minscore = float(v)
                            os.environ["QJSON_RETRIEVAL_MINSCORE"] = str(retrieval_minscore)
                        except Exception:
                            pass
                    elif k in ("ivf","fmm"):
                        os.environ["QJSON_RETR_USE_FMM"] = "1" if v in ("1","on","yes","true") else "0"
                    elif k in ("ivf_k","kivf"):
                        try:
                            os.environ["QJSON_RETR_IVF_K"] = str(max(2, int(v)))
                        except Exception:
                            pass
                    elif k in ("nprobe","ivf_nprobe"):
                        try:
                            os.environ["QJSON_RETR_IVF_NPROBE"] = str(max(1, int(v)))
                        except Exception:
                            pass
                    elif k in ("thresh","threshold","reindex_threshold"):
                        try:
                            os.environ["QJSON_RETR_REINDEX_THRESHOLD"] = str(max(1, int(v)))
                        except Exception:
                            pass
                _print(f"[retrieval] armed once k={retrieval_top_k} decay={retrieval_decay} min={retrieval_minscore}")
                continue
            if val in ("on", "yes"):
                retrieval_enabled = True
                os.environ["QJSON_RETRIEVAL"] = "1"
                _print("[retrieval] Enabled")
            elif val in ("off", "no"):
                retrieval_enabled = False
                os.environ.pop("QJSON_RETRIEVAL", None)
                _print("[retrieval] Disabled")
            else:
                parts = [p for p in val.replace(",", " ").split() if p]
                for p in parts:
                    if "=" not in p:
                        continue
                    k, v = p.split("=", 1)
                    if k == "k":
                        try:
                            retrieval_top_k = max(1, int(v))
                            os.environ["QJSON_RETRIEVAL_TOPK"] = str(retrieval_top_k)
                        except Exception:
                            pass
                    elif k == "decay":
                        try:
                            retrieval_decay = float(v)
                            os.environ["QJSON_RETRIEVAL_DECAY"] = str(retrieval_decay)
                        except Exception:
                            pass
                    elif k in ("min","minscore"):
                        try:
                            retrieval_minscore = float(v)
                            os.environ["QJSON_RETRIEVAL_MINSCORE"] = str(retrieval_minscore)
                        except Exception:
                            pass
                    elif k in ("ivf","fmm"):
                        os.environ["QJSON_RETR_USE_FMM"] = "1" if v in ("1","on","yes","true") else "0"
                    elif k in ("ivf_k","kivf"):
                        try:
                            os.environ["QJSON_RETR_IVF_K"] = str(max(2, int(v)))
                        except Exception:
                            pass
                    elif k in ("nprobe","ivf_nprobe"):
                        try:
                            os.environ["QJSON_RETR_IVF_NPROBE"] = str(max(1, int(v)))
                        except Exception:
                            pass
                    elif k in ("thresh","threshold","reindex_threshold"):
                        try:
                            os.environ["QJSON_RETR_REINDEX_THRESHOLD"] = str(max(1, int(v)))
                        except Exception:
                            pass
                _print(f"[retrieval] {'on' if retrieval_enabled else 'off'} k={retrieval_top_k} decay={retrieval_decay} min={retrieval_minscore}")
                continue
        if user.startswith("/retrieve") or user == "/r":
            # Arm one-shot retrieval for the next prompt
            arg = user.replace("/retrieve", "", 1).strip()
            # Default behavior is 'once'; allow explicit 'once', 'on', 'off'.
            # Accept free-text query after 'once' to seed retrieval query.
            if not arg or arg.lower().split()[0] in ("once","one","next"):
                os.environ["QJSON_RETRIEVAL_ONCE"] = "1"
                toks = [t for t in arg.split() if t]
                if toks and toks[0].lower() in ("once","one","next"):
                    hint = " ".join([t for t in toks[1:] if "=" not in t])
                    if hint:
                        os.environ["QJSON_RETRIEVAL_QUERY_HINT"] = hint
            elif arg.lower().split()[0] in ("on","yes"):
                os.environ["QJSON_RETRIEVAL"] = "1"
            elif arg.lower().split()[0] in ("off","no"):
                os.environ.pop("QJSON_RETRIEVAL", None)
            val = arg.lower()
            parts = [p for p in val.replace(",", " ").split() if p and "=" in p]
            for p in parts:
                k, v = p.split("=", 1)
                if k == "k":
                    try:
                        retrieval_top_k = max(1, int(v))
                        os.environ["QJSON_RETRIEVAL_TOPK"] = str(retrieval_top_k)
                    except Exception:
                        pass
                elif k == "decay":
                    try:
                        retrieval_decay = float(v)
                        os.environ["QJSON_RETRIEVAL_DECAY"] = str(retrieval_decay)
                    except Exception:
                        pass
                elif k in ("min","minscore"):
                    try:
                        retrieval_minscore = float(v)
                        os.environ["QJSON_RETRIEVAL_MINSCORE"] = str(retrieval_minscore)
                    except Exception:
                        pass
                elif k == 'hybrid':
                    os.environ["QJSON_RETRIEVAL_HYBRID"] = v
                elif k in ('tfidf_weight','tw'):
                    try:
                        os.environ["QJSON_RETRIEVAL_TFIDF_WEIGHT"] = str(float(v))
                    except Exception:
                        pass
                elif k in ('fresh','fresh_boost'):
                    try:
                        os.environ["QJSON_RETRIEVAL_FRESH_BOOST"] = str(float(v))
                    except Exception:
                        pass
                elif k in ("ivf","fmm"):
                    os.environ["QJSON_RETR_USE_FMM"] = "1" if v in ("1","on","yes","true") else "0"
                elif k in ("ivf_k","kivf"):
                    try:
                        os.environ["QJSON_RETR_IVF_K"] = str(max(2, int(v)))
                    except Exception:
                        pass
                elif k in ("nprobe","ivf_nprobe"):
                    try:
                        os.environ["QJSON_RETR_IVF_NPROBE"] = str(max(1, int(v)))
                    except Exception:
                        pass
                elif k in ("thresh","threshold","reindex_threshold"):
                    try:
                        os.environ["QJSON_RETR_REINDEX_THRESHOLD"] = str(max(1, int(v)))
                    except Exception:
                        pass
            _print(f"[retrieve] armed once k={retrieval_top_k} decay={retrieval_decay} min={retrieval_minscore}")
            continue
        if user.startswith("/force_retrieve"):
            # Force next-turn retrieval, optional free-text query
            hint = user.replace("/force_retrieve", "", 1).strip()
            os.environ["QJSON_RETRIEVAL_ONCE"] = "1"
            if hint:
                os.environ["QJSON_RETRIEVAL_QUERY_HINT"] = hint
            _print("[retrieve] forced for next prompt" + (f" (hint='{hint}')" if hint else ""))
            continue
        if user.startswith("/search"):
            query = user.replace("/search", "", 1).strip()
            if not query:
                _print("Usage: /search <QUERY>")
                continue
            try:
                from .retrieval import search_memory
                hits = search_memory(agent.agent_id, query, top_k=retrieval_top_k, time_decay=retrieval_decay)
                if not hits:
                    _print(f"[Search] No memories found matching: '{query}'")
                    continue
                
                _print(f"[Search] Found {len(hits)} memories matching '{query}'. Injecting for next prompt...")
                for hit in hits[:4]: # Preview top 4
                    _print(f"- ({hit['score']:.2f}) {hit['text'][:120]}")
                if len(hits) > 4:
                    _print(f"...and {len(hits) - 4} more.")
                
                # Serialize hits and pass to next turn via env var
                os.environ["QJSON_INJECT_HITS_ONCE"] = json.dumps(hits)

            except Exception as e:
                _print(f"[Search Error] {e}")
            continue
        if user.startswith("/setenv"):
            arg = user.replace("/setenv", "", 1).strip()
            if "=" not in arg:
                _print("Usage: /setenv KEY=VALUE")
                continue
            k, v = arg.split("=", 1)
            k = k.strip()
            os.environ[k] = v
            _save_persistent_env(k, v)
            _print(f"[env] set {k} (persisted)")
            continue
        if user.startswith("/engine_scope") or user.startswith("/webscope"):
            parts = user.split()
            if len(parts) == 1 or parts[1] == "show":
                roots = os.environ.get("QJSON_LOCAL_SEARCH_ROOTS", "")
                _print(f"[engine_scope] roots={roots or os.getcwd()}")
                continue
            if parts[1] == "clear":
                os.environ.pop("QJSON_LOCAL_SEARCH_ROOTS", None)
                _save_persistent_env("QJSON_LOCAL_SEARCH_ROOTS", "")
                _print("[engine_scope] cleared; defaulting to current directory")
                continue
            if parts[1] in ("add", "set"):
                paths = parts[2:]
                if not paths:
                    _print("Usage: /engine_scope add <PATH...> | /engine_scope set <PATH...>")
                    continue
                existing = os.environ.get("QJSON_LOCAL_SEARCH_ROOTS", "").split(os.pathsep) if parts[1] == "add" else []
                merged = [p for p in existing if p]
                for p in paths:
                    pr = os.path.expanduser(os.path.expandvars(p))
                    if os.path.isdir(pr):
                        merged.append(pr)
                val = os.pathsep.join(dict.fromkeys(merged))
                os.environ["QJSON_LOCAL_SEARCH_ROOTS"] = val
                _save_persistent_env("QJSON_LOCAL_SEARCH_ROOTS", val)
                _print(f"[engine_scope] roots set: {val}")
                continue
        if user.startswith("/langsearch"):
            parts = user.split()
            if len(parts) >= 3 and parts[1].lower() == "key":
                key = " ".join(parts[2:]).strip()
                os.environ["LANGSEARCH_API_KEY"] = key
                _save_persistent_env("LANGSEARCH_API_KEY", key)
                _print("[langsearch] API key set and persisted for this session.")
            else:
                _print("Usage: /langsearch key <KEY>")
            continue
        # Deprecated /websearch, /webopen, /crawlopen removed; use /find and /open

        if user.startswith("/include_sys"):
            arg = user.replace("/include_sys", "", 1).strip().lower()
            if not arg:
                status = f"on ({include_sys_count})" if include_sys_enabled else "off"
                auto = "on" if include_sys_auto else "off"
                _print(f"[include_sys] Current: {status}, auto={auto}")
                continue
            if arg in ("on", "yes"):
                include_sys_enabled = True
                _print(f"[include_sys] Enabled ({include_sys_count})")
            elif arg in ("off", "no"):
                include_sys_enabled = False
                _print("[include_sys] Disabled")
            elif arg.startswith("auto"):
                parts = arg.split()
                # allow '/include_sys auto on|off' or toggle if no arg
                if len(parts) > 1 and parts[1] in ("on", "off"):
                    include_sys_auto = (parts[1] == "on")
                else:
                    include_sys_auto = not include_sys_auto
                _print(f"[include_sys] Auto={'on' if include_sys_auto else 'off'} (include next injected file on next prompt)")
            else:
                try:
                    n = int(arg)
                    include_sys_count = max(1, n)
                    include_sys_enabled = True
                    _print(f"[include_sys] Enabled ({include_sys_count})")
                except Exception:
                    _print("[include_sys] Invalid argument. Use on|off|<N>.")
            continue
        if user.startswith("/include_as"):
            arg = user.replace("/include_as", "", 1).strip().lower()
            if arg in ("system", "user"):
                include_as_role = arg
                _print(f"[include_as] Now including memory as: {include_as_role}")
            else:
                _print("Usage: /include_as [system|user]")
            continue
        if user.startswith("/settings") and "edit" in user:
            # Example: /settings edit include_as=user include_sys=on:3 auto=on mem_trunc=off cap=16000 yson_exec=on
            try:
                parts = user.split()[2:]  # skip '/settings edit'
                for p in parts:
                    if '=' not in p:
                        continue
                    k, v = p.split('=', 1)
                    k = k.strip().lower(); v = v.strip().lower()
                    if k == 'include_as' and v in ('system','user'):
                        include_as_role = v
                    elif k == 'include_sys':
                        if v.startswith('on'):
                            include_sys_enabled = True
                            try:
                                if ':' in v:
                                    include_sys_count = max(1, int(v.split(':',1)[1]))
                            except Exception:
                                pass
                        elif v == 'off':
                            include_sys_enabled = False
                    elif k == 'auto':
                        include_sys_auto = (v == 'on')
                    elif k == 'mem_trunc':
                        if v == 'off':
                            mem_truncate_limit = None
                        elif v == 'on':
                            mem_truncate_limit = 8000
                        else:
                            try:
                                mem_truncate_limit = max(1, int(v))
                            except Exception:
                                pass
                    elif k == 'cap':
                        try:
                            include_max_chars = max(128, int(v))
                        except Exception:
                            pass
                    elif k == 'yson_exec':
                        if v == 'on':
                            os.environ["QJSON_ALLOW_YSON_EXEC"] = "1"
                            yson_exec_allowed = True
                        elif v == 'off':
                            os.environ.pop("QJSON_ALLOW_YSON_EXEC", None)
                            yson_exec_allowed = False
                    elif k in ('retrieval_min','min','minscore'):
                        try:
                            retrieval_minscore = float(v)
                            os.environ["QJSON_RETRIEVAL_MINSCORE"] = str(retrieval_minscore)
                        except Exception:
                            pass
                    elif k == 'retrieval':
                        if v == 'on':
                            os.environ["QJSON_RETRIEVAL"] = "1"
                            retrieval_enabled = True
                        elif v == 'off':
                            os.environ.pop("QJSON_RETRIEVAL", None)
                            retrieval_enabled = False
                    elif k in ('retrieval_k','rk','k'):
                        try:
                            retrieval_top_k = max(1, int(v))
                            os.environ["QJSON_RETRIEVAL_TOPK"] = str(retrieval_top_k)
                        except Exception:
                            pass
                    elif k in ('retrieval_decay','rd','decay'):
                        try:
                            retrieval_decay = float(v)
                            os.environ["QJSON_RETRIEVAL_DECAY"] = str(retrieval_decay)
                        except Exception:
                            pass
                _print("[settings] updated")
            except Exception as e:
                _print(f"[settings error] {e}")
            continue
        if user.startswith("/preflight") or user.startswith("/prompt_stats"):
            probe = user.split(" ", 1)
            text = probe[1].strip() if len(probe) > 1 else ""
            if not text:
                _print("Usage: /preflight <TEXT>")
                continue
            # Build messages like chat_turn would
            system = {"role": "system", "content": agent._system_prompt()}
            history = []
            try:
                from .memory import tail_jsonl
                history = tail_jsonl(agent_dir(agent.agent_id) / "memory.jsonl", 32)
            except Exception:
                history = []
            # Build inclusion blocks
            extra_system = None
            extra_context = None
            n_to_include = include_sys_next_n if include_sys_next_n is not None else (include_sys_count if include_sys_enabled else None)
            if n_to_include:
                try:
                    from .memory import tail_jsonl as _tail
                    sys_msgs = [m for m in _tail(agent_dir(agent.agent_id) / "memory.jsonl", 256) if m.get("role") == "system"]
                    take_n = min(max(1, int(n_to_include)), include_max_msgs)
                    take = sys_msgs[-take_n:]
                    # Build until cap reached to avoid large temporary buffers
                    parts = []
                    total = 0
                    for m in take:
                        src = (m.get('meta') or {}).get('source','system')
                        seg = f"[mem:{src}]\n{m.get('content','')}"
                        if isinstance(include_max_chars, int) and include_max_chars > 0:
                            room = include_max_chars - total
                            if room <= 0:
                                break
                            if len(seg) > room:
                                seg = seg[:room]
                        parts.append(seg)
                        total += len(seg)
                    joined = "\n\n".join(parts).strip()
                    if include_as_role == "system":
                        extra_system = joined
                    else:
                        extra_context = [{"role": "user", "content": joined}]
                except Exception:
                    pass
            msgs = [system]
            if extra_system:
                msgs.append({"role": "system", "content": extra_system})
            if extra_context:
                msgs.extend(extra_context)
            for h in history:
                r = h.get("role")
                if r in ("user", "assistant"):
                    msgs.append({"role": r, "content": h.get("content", "")})
            msgs.append({"role": "user", "content": text})

            # Estimate sizes and latency
            prompt_chars = sum(len(m.get("content", "")) for m in msgs)
            prompt_tokens = (prompt_chars + 3) // 4
            opts = agent._ollama_options()
            pred_tokens = int(opts.get("num_predict", 256))
            model_name = (chosen_model or args.model or agent.manifest.get("runtime", {}).get("model", "")) or "unknown"
            lname = str(model_name).lower()
            if any(x in lname for x in [":4b", " 4b", "gemma3:4b", "7b", "8b"]):
                gen_tps = 30.0
            elif "20b" in lname:
                gen_tps = 12.0
            elif "120b" in lname or "405b" in lname:
                gen_tps = 5.0
            else:
                gen_tps = 20.0
            enc_tps = gen_tps * 3.0
            est_sec = round(prompt_tokens / max(1.0, enc_tps) + pred_tokens / max(1.0, gen_tps) + 0.5, 2)
            _print(f"[preflight] model={model_name} prompt_chars={prompt_chars} prompt_tokens≈{prompt_tokens} pred_tokens={pred_tokens} gen_tps≈{gen_tps} enc_tps≈{enc_tps} est_latency≈{est_sec}s")
            continue
        if user.startswith("/stream"):
            arg = user.replace("/stream", "", 1).strip().lower()
            if not arg:
                _print(f"[stream] Current: {'on' if stream_enabled else 'off'}")
            elif arg in ("on","yes","1"):
                stream_enabled = True
                _print("[stream] Enabled")
            elif arg in ("off","no","0"):
                stream_enabled = False
                _print("[stream] Disabled")
            else:
                _print("Usage: /stream [on|off]")
            continue
        if user.startswith("/yson_exec"):
            arg = user.replace("/yson_exec", "", 1).strip().lower()
            if not arg:
                _print(f"[yson_exec] Current: {'on' if yson_exec_allowed else 'off'}")
                continue
            if arg in ("on", "yes", "1"):
                os.environ["QJSON_ALLOW_YSON_EXEC"] = "1"
                yson_exec_allowed = True
                _print("[yson_exec] Enabled (logic in YSON may execute).")
            elif arg in ("off", "no", "0"):
                try:
                    os.environ.pop("QJSON_ALLOW_YSON_EXEC", None)
                except Exception:
                    pass
                yson_exec_allowed = False
                _print("[yson_exec] Disabled (logic in YSON will not execute).")
            else:
                _print("Usage: /yson_exec [on|off]")
            continue
        if user.startswith("/allow_logic"):
            arg = user.replace("/allow_logic", "", 1).strip().lower()
            if not arg:
                _print(f"[logic] Current: {'on' if allow_logic else 'off'}")
                continue
            if arg in ("on", "yes", "1"):
                allow_logic = True
                _print("[logic] Enabled (persona on_message will handle replies if available).")
            elif arg in ("off", "no", "0"):
                allow_logic = False
                _print("[logic] Disabled (model will handle replies).")
            else:
                _print("Usage: /allow_logic [on|off]")
            continue
        if user.startswith("/logic_mode"):
            arg = user.replace("/logic_mode", "", 1).strip().lower()
            if arg in ("assist", "replace"):
                logic_mode = arg
                _print(f"[logic] mode set to {logic_mode}")
            else:
                _print("Usage: /logic_mode [assist|replace]")
            continue
        if user.startswith("/logic_ping"):
            text = user.replace("/logic_ping", "", 1).strip()
            if not text:
                _print("Usage: /logic_ping <TEXT>")
                continue
            if not persona_logic:
                _print("[logic] on_message entrypoint not available")
                continue
            st = _load_logic_state()
            try:
                reply = persona_logic(st, text, agent.manifest)  # type: ignore
                _save_logic_state(st)
                _print(reply)
            except Exception as e:
                _print(f"[logic error] {e}")
            continue
        if user.startswith("/truth"):
            arg = user.replace("/truth", "", 1).strip().lower()
            if not arg:
                _print("Usage: /truth [on|off]")
                continue
            truth_note = None
            if arg in ("on", "yes", "1"):
                truth_note = (
                    "[truth] I am a local agent with fractal memory (state/*). "
                    "I differ from baseline LLMs by using persistent local state and deterministic logic hooks when enabled."
                )
                os.environ["QJSON_TRUTH_NOTE"] = truth_note
                _print("[truth] Enabled")
            elif arg in ("off", "no", "0"):
                try:
                    os.environ.pop("QJSON_TRUTH_NOTE", None)
                except Exception:
                    pass
                _print("[truth] Disabled")
            else:
                _print("Usage: /truth [on|off]")
            continue
        if user.startswith("/fork"):
            parts = user.split(maxsplit=1)
            if len(parts) == 2 and parts[1].strip():
                new_id = parts[1].strip()
                child = agent.fork(new_id, note=f"Forked via CLI from {agent.agent_id}")
                _print(f"Forked -> {new_id} at {agent_dir(new_id)}")
            else:
                _print("Usage: /fork <NEW_ID>")
            continue
        if user.startswith("/swap"):
            parts = user.split(maxsplit=1)
            if len(parts) == 2 and parts[1].strip():
                ident = parts[1].strip()
                mf = find_persona(ident)
                if not mf:
                    _print(f"Persona not found: {ident}")
                    continue
                try:
                    agent.swap_persona(mf, cause="user:/swap")
                    _print(f"Swapped persona -> {agent.agent_id}")
                except Exception as e:
                    _print(f"[swap error] {e}")
            else:
                _print("Usage: /swap <path|agent_id|tag>")
            continue
        if user.startswith("/evolve"):
            try:
                agent.mutate_self(adopt=True)
                _print(f"Evolved persona -> {agent.agent_id}")
            except Exception as e:
                _print(f"[evolve error] {e}")
            continue

        try:
            model_override = chosen_model or args.model
            extra_context = None
            extra_system = None
            anchor = None
            # Persona logic assist mode: compute an anchor even if we don't include memory
            if allow_logic and persona_logic and logic_mode == "assist":
                try:
                    st = _load_logic_state()
                    st.setdefault("agent_dir", str(agent_dir(agent.agent_id)))
                    anchor = str(persona_logic(st, user, agent.manifest))  # type: ignore
                    _save_logic_state(st)
                    _print(f"[logic] anchor injected len={len(anchor)}")
                except Exception as e:
                    _print(f"[logic error] {e}; continuing without anchor")
            # Determine how many system messages to include
            n_to_include = None
            if include_sys_next_n is not None:
                n_to_include = include_sys_next_n
            elif include_sys_enabled:
                n_to_include = include_sys_count
            if n_to_include:
                try:
                    from .memory import tail_jsonl
                    sys_msgs = [m for m in tail_jsonl(agent_dir(agent.agent_id) / "memory.jsonl", 256) if m.get("role") == "system"]
                    take = sys_msgs[-max(1, int(n_to_include)) :]
                    blocks = []
                    for m in take:
                        src = (m.get('meta') or {}).get('source','system')
                        blocks.append(f"[mem:{src}]\n{m.get('content','')}")
                    joined = ("\n\n".join(blocks)).strip()
                    truth = os.environ.get("QJSON_TRUTH_NOTE")
                    if truth:
                        joined = (truth + "\n\n" + joined).strip()
                    if anchor:
                        joined = (f"[logic_anchor]\n{anchor}\n\n" + joined).strip()
                    # Apply safety cap
                    if isinstance(include_max_chars, int) and include_max_chars > 0 and len(joined) > include_max_chars:
                        joined = joined[:include_max_chars]
                    if include_as_role == "system":
                        extra_system = joined
                    else:
                        extra_context = [{"role": "user", "content": joined}]
                except Exception:
                    extra_system = None
            elif anchor:
                # No memory inclusion, but still include anchor as system or user
                truth = os.environ.get("QJSON_TRUTH_NOTE")
                body = (truth + "\n\n" if truth else "") + f"[logic_anchor]\n{anchor}"
                if include_as_role == "system":
                    extra_system = body
                else:
                    extra_context = [{"role": "user", "content": body}]
            # Persona logic path: bypass model if enabled and entrypoint is available
            if allow_logic and persona_logic and logic_mode == "replace":
                try:
                    agent._log_message("user", user, {"model": "logic:on_message"})
                    st = _load_logic_state()
                    reply = persona_logic(st, user, agent.manifest)  # type: ignore
                    _save_logic_state(st)
                    agent._log_message("assistant", reply, {"model": "logic:on_message"})
                    include_sys_next_n = None
                    _print(f"{agent.agent_id} > {reply}")
                    continue
                except Exception as e:
                    _print(f"[logic error] {e}; falling back to model")
            if stream_enabled:
                def _printer(delta: str) -> None:
                    try:
                        sys.stdout.write(delta)
                        sys.stdout.flush()
                    except Exception:
                        pass
                reply = agent.chat_turn_stream(user, on_delta=_printer, model_override=model_override, extra_system=extra_system, extra_context=extra_context)
                _print("")
            else:
                reply = agent.chat_turn(user, model_override=model_override, extra_system=extra_system, extra_context=extra_context)
            # Clear one-shot include after use
            include_sys_next_n = None
        except Exception as e:
            _print(f"[error] {e}")
            continue
        _print(f"{agent.agent_id} > {reply}")

    return 0


def cmd_fork(args: argparse.Namespace, default_api: Any = None) -> int:
    agent_id = args.source
    mpath = agent_dir(agent_id) / "manifest.json"
    if not mpath.exists():
        _print(f"Source agent not found: {agent_id}")
        return 2
    manifest = json.loads(mpath.read_text(encoding="utf-8"))
    agent = Agent(manifest)
    child = agent.fork(args.new_id, note=args.note)
    _print(f"Forked {agent_id} -> {args.new_id}")
    return 0


def cmd_status(args: argparse.Namespace, default_api: Any = None) -> int:
    agent_id = args.id
    mpath = agent_dir(agent_id) / "manifest.json"
    if not mpath.exists():
        _print(f"Agent not found: {agent_id}")
        return 2
    manifest = json.loads(mpath.read_text(encoding="utf-8"))
    agent = Agent(manifest)
    st = agent.status(tail=args.tail)
    # Compact print
    _print(f"agent_id: {st['agent_id']}")
    _print("manifest: " + json.dumps(st["manifest"], ensure_ascii=False))
    _print("-- memory tail --")
    for m in st["memory_tail"]:
        _print(json.dumps(m, ensure_ascii=False))
    _print("-- events tail --")
    for e in st["events_tail"]:
        _print(json.dumps(e, ensure_ascii=False))
    return 0


def cmd_loop(args: argparse.Namespace) -> int:
    agent_id = args.id
    manifest_path = Path(args.manifest) if args.manifest else None

    if manifest_path and manifest_path.exists():
        if manifest_path.suffix.lower() in (".yson", ".ysonx"):
            manifest = yson_to_manifest(manifest_path)
        else:
            manifest = load_manifest(manifest_path)
        if args.model:
            manifest.setdefault("runtime", {})["model"] = args.model
        agent = Agent(manifest)
    else:
        mpath = agent_dir(agent_id) / "manifest.json"
        if not mpath.exists():
            _print("No manifest found. Provide --manifest to initialize.")
            return 2
        manifest = json.loads(mpath.read_text(encoding="utf-8"))
        if args.model:
            manifest.setdefault("runtime", {})["model"] = args.model
        agent = Agent(manifest)

    # Resolve model automatically from /api/tags if needed
    chosen_model = None
    if args.model in (None, "auto"):
        try:
            client = OllamaClient()
            models = client.tags()
            if not models:
                _print("No local models found via /api/tags. Pull one with 'ollama pull <model>'.")
            else:
                chosen_model = models[0].get("name") or models[0].get("model")
                _print(f"[models] selected: {chosen_model}")
        except Exception as e:
            _print(f"[models] error: {e}")

    goal = args.goal
    iters = max(1, int(args.iterations))
    delay = float(args.delay)
    _print(f"Starting autonomous loop for {agent.agent_id}: {iters} iterations")
    # Log loop start event
    from .memory import append_jsonl, _now_ts
    append_jsonl(agent_dir(agent.agent_id) / "events.jsonl", {"ts": _now_ts(), "type": "loop_start", "meta": {"goal": goal, "iterations": iters}})

    import time
    for i in range(1, iters + 1):
        user = (
            f"Autonomous loop tick {i}/{iters}. Goal: {goal}. "
            f"Reflect briefly, propose next micro-step, and document any anomalies."
        )
        _print(f"tick {i} > {user}")
        try:
            model_override = chosen_model or args.model
            reply = agent.chat_turn(user, model_override=model_override)
        except Exception as e:
            _print(f"[error] {e}")
            break
        _print(f"{agent.agent_id} > {reply}\n")
        if delay > 0:
            time.sleep(delay)

    append_jsonl(agent_dir(agent.agent_id) / "events.jsonl", {"ts": _now_ts(), "type": "loop_end", "meta": {"goal": goal, "iterations": iters}})
    _print("Loop complete.")
    return 0


def cmd_models(args: argparse.Namespace) -> int:
    try:
        client = OllamaClient()
        models = client.tags()
    except Exception as e:
        _print(f"[models] error: {e}")
        return 1
    if not models:
        _print("No models installed. Use 'ollama pull <model>'.")
        return 0
    _print("Installed models:")
    for m in models:
        name = m.get("name") or m.get("model")
        size = m.get("size")
        mod = m.get("modified_at")
        _print(f"- {name}  (size={size}, modified={mod})")
    return 0


def cmd_semi(args: argparse.Namespace) -> int:
    """Run a semi-autonomous loop with a plugin whitelist and early-stop heuristics."""
    agent_id = args.id
    manifest_path = Path(args.manifest) if args.manifest else None

    if manifest_path and manifest_path.exists():
        if manifest_path.suffix.lower() in (".yson", ".ysonx"):
            manifest = yson_to_manifest(manifest_path)
        else:
            manifest = load_manifest(manifest_path)
        if args.model:
            manifest.setdefault("runtime", {})["model"] = args.model
        agent = Agent(manifest)
    else:
        mpath = agent_dir(agent_id) / "manifest.json"
        if not mpath.exists():
            _print("No manifest found. Provide --manifest to initialize.")
            return 2
        manifest = json.loads(mpath.read_text(encoding="utf-8"))
        if args.model:
            manifest.setdefault("runtime", {})["model"] = args.model
        agent = Agent(manifest)

    # Apply plugin gating envs
    if args.plugins:
        os.environ["QJSON_PLUGIN_ALLOW"] = ",".join([s.strip() for s in args.plugins.split(",") if s.strip()])
    if args.allow_exec:
        os.environ["QJSON_ALLOW_EXEC"] = "1"
    if args.allow_net:
        os.environ["QJSON_ALLOW_NET"] = "1"
    if args.fs_roots:
        os.environ["QJSON_FS_ROOTS"] = args.fs_roots
    if args.fs_write:
        os.environ["QJSON_FS_WRITE"] = "1"
    if args.git_root:
        os.environ["QJSON_GIT_ROOT"] = args.git_root

    # Resolve model automatically if needed
    chosen_model = None
    if args.model in (None, "auto"):
        try:
            client = OllamaClient()
            models = client.tags()
            if models:
                chosen_model = models[0].get("name") or models[0].get("model")
                _print(f"[models] selected: {chosen_model}")
        except Exception:
            pass

    goal = args.goal or "Execute the task safely using available tools."
    iters = max(1, int(args.iterations))
    delay = float(args.delay)
    stop_token = (args.stop_token or "need more info").strip().lower()
    _print(f"[semi] starting for {agent.agent_id}: {iters} iterations; stop on '{stop_token}'")

    from .memory import append_jsonl, _now_ts
    append_jsonl(agent_dir(agent.agent_id) / "events.jsonl", {"ts": _now_ts(), "type": "semi_start", "meta": {"goal": goal, "iterations": iters}})

    import time
    for i in range(1, iters + 1):
        user = (
            f"Semi-autonomous tick {i}/{iters}. Goal: {goal}. "
            f"Use available tools as needed and state next steps."
        )
        _print(f"tick {i} > {user}")
        try:
            model_override = chosen_model or args.model
            reply = agent.chat_turn(user, model_override=model_override)
        except Exception as e:
            _print(f"[error] {e}")
            break
        _print(f"{agent.agent_id} > {reply}\n")
        low = (reply or "").lower()
        if (stop_token and stop_token in low) or ("need more information" in low) or ("clarify" in low and "need" in low):
            _print("[semi] early stop: agent requested more information.")
            break
        if delay > 0:
            time.sleep(delay)

    append_jsonl(agent_dir(agent.agent_id) / "events.jsonl", {"ts": _now_ts(), "type": "semi_end", "meta": {"goal": goal, "iterations": iters}})
    _print("[semi] complete.")
    return 0


def cmd_test(args: argparse.Namespace, default_api: Any = None) -> int:
    """Run a local, network-free test harness for ~duration seconds.

    Exercises core methods with a mocked Ollama client and writes three logs:
    - logs/test_run_YYYYMMDD-HHMMSS.txt  (human-readable summary)
    - logs/test_run_YYYYMMDD-HHMMSS.json (structured event log)
    - logs/test_run_YYYYMMDD-HHMMSS.log  (debug log)
    """
    # Resolve manifest
    manifest_path = Path(args.manifest) if args.manifest else Path("manifests/lila.json")
    if manifest_path.exists():
        manifest = load_manifest(manifest_path)
    else:
        # Minimal fallback manifest if example is missing
        manifest = {
            "agent_id": "TestHarness",
            "origin": "Local",
            "creator": "qjson-agents",
            "roles": ["tester"],
            "features": {
                "recursive_memory": True,
                "fractal_state": True,
                "autonomous_reflection": False,
                "emergent_behavior": "deterministic",
                "chaos_alignment": "low",
                "symbolic_interface": "text",
            },
            "core_directives": [
                "Exercise methods safely",
                "Avoid network calls",
                "Log results in multiple formats",
            ],
            "runtime": {"model": "mock-llm"},
        }

    # Unique agent id for this run
    run_ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    agent_id = args.id or f"TestHarness-{run_ts}"
    manifest = dict(manifest)
    manifest["agent_id"] = agent_id

    agent = Agent(manifest)

    # Prepare logging outputs
    logs_dir = Path("logs")
    logs_dir.mkdir(parents=True, exist_ok=True)
    base = logs_dir / f"test_run_{run_ts}"
    path_txt = base.with_suffix(".txt")
    path_json = base.with_suffix(".json")
    path_log = base.with_suffix(".log")

    logger = logging.getLogger("qjson_agents.test")
    logger.setLevel(logging.DEBUG)
    # Reset handlers to avoid duplicates on multiple invocations
    logger.handlers.clear()
    fh = logging.FileHandler(path_log, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    duration = float(args.duration)
    interval = float(args.interval)
    deadline = time.time() + duration

    # Mock Ollama client (no network)
    class MockOllamaClient:
        def __init__(self):
            self.calls = 0

        def chat(self, *, model: str, messages: list[dict[str, str]], options: dict | None = None, stream: bool = False) -> dict:
            self.calls += 1
            user_msg = ""
            for m in reversed(messages):
                if m.get("role") == "user":
                    user_msg = m.get("content", "")
                    break
            # Lightweight, deterministic-ish reply
            reply = f"[mock:{self.calls}] Ack: {user_msg[:80]}"
            return {"message": {"role": "assistant", "content": reply}}

        def tags(self) -> list[dict[str, str]]:
            return [{"name": "mock-llm"}]

    use_ollama = bool(getattr(args, "use_ollama", False))

    if use_ollama:
        client = OllamaClient()
        # Resolve model: use provided or pick the first available via /api/tags
        model_to_use = args.model
        if not model_to_use:
            try:
                models = client.tags()
            except Exception as e:
                _print(f"[models] error: {e}")
                return 2
            if not models:
                _print("No local models found via /api/tags. Pull one with 'ollama pull <model>'.")
                return 2
            model_to_use = models[0].get("name") or models[0].get("model")
            _print(f"[models] selected: {model_to_use}")
    else:
        client = MockOllamaClient()
        model_to_use = "mock-llm"

    # Test loop state
    counters: Dict[str, int] = {"chat": 0, "fork": 0, "status": 0, "errors": 0}
    events: list[Dict[str, Any]] = []

    logger.info(f"Starting test run for {agent.agent_id} (duration={duration}s, interval={interval}s)")
    start_ts = time.time()

    i = 0
    forks_done = 0
    try:
        while time.time() < deadline:
            i += 1
            # Rotate through actions to exercise methods
            action = "chat"
            if i % 7 == 0 and forks_done < args.max_forks:
                action = "fork"
            elif i % 5 == 0:
                action = "status"

            try:
                if action == "chat":
                    prompt = f"Tick {i}: run health check and echo counters={counters}"
                    reply = agent.chat_turn(prompt, client=client, model_override=model_to_use)
                    counters["chat"] += 1
                    events.append({"t": time.time(), "type": "chat", "prompt": prompt, "reply": reply})
                    logger.debug(f"chat[{i}] prompt='{prompt[:60]}' -> reply='{reply[:60]}'")
                elif action == "status":
                    st = agent.status(tail=5)
                    counters["status"] += 1
                    events.append({"t": time.time(), "type": "status", "tail_mem": len(st.get("memory_tail", [])), "tail_ev": len(st.get("events_tail", []))})
                    logger.debug(f"status[{i}] memory_tail={len(st.get('memory_tail', []))} events_tail={len(st.get('events_tail', []))}")
                elif action == "fork":
                    child_id = f"{agent.agent_id}-child{forks_done+1}"
                    agent.fork(child_id, note=f"fork from test iteration {i}")
                    forks_done += 1
                    counters["fork"] += 1
                    events.append({"t": time.time(), "type": "fork", "child_id": child_id})
                    logger.debug(f"fork[{i}] -> {child_id}")
            except Exception as e:
                counters["errors"] += 1
                events.append({"t": time.time(), "type": "error", "error": str(e)})
                logger.exception(f"action '{action}' failed: {e}")

            if interval > 0:
                time.sleep(interval)
    finally:
        end_ts = time.time()
        elapsed = end_ts - start_ts
        # Persist JSON summary
        summary: Dict[str, Any] = {
            "agent_id": agent.agent_id,
            "start_ts": start_ts,
            "end_ts": end_ts,
            "elapsed_sec": round(elapsed, 3),
            "counts": counters,
            "events": events,
            "logs": {
                "txt": str(path_txt),
                "json": str(path_json),
                "log": str(path_log),
            },
        }
        with path_json.open("w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)

        # Persist TXT summary
        tail_mem = []
        try:
            from .memory import tail_jsonl
            tail_mem = tail_jsonl(agent_dir(agent.agent_id) / "memory.jsonl", 3)
        except Exception:
            pass
        with path_txt.open("w", encoding="utf-8") as f:
            f.write(f"Test run for {agent.agent_id}\n")
            f.write(f"Duration: {round(elapsed, 3)}s\n")
            f.write(f"Counts: {counters}\n")
            f.write("Last 3 memory entries:\n")
            for m in tail_mem:
                f.write(json.dumps(m, ensure_ascii=False) + "\n")

        logger.info(f"Test complete in {round(elapsed, 3)}s — chat={counters['chat']} fork={counters['fork']} status={counters['status']} errors={counters['errors']}")

    _print("Test harness outputs:")
    _print(f"- {path_txt}")
    _print(f"- {path_json}")
    _print(f"- {path_log}")
    return 0


def cmd_cluster(args: argparse.Namespace) -> int:
    # Load or refresh index
    if args.refresh:
        idx = refresh_cluster_index()
    else:
        idx = load_cluster_index()
        if not idx.get("agents"):
            idx = refresh_cluster_index()

    agents = idx.get("agents", {})
    if args.json:
        _print(json.dumps(idx, ensure_ascii=False, indent=2))
        return 0

    # Build parent->children map
    children: Dict[str, list[str]] = {}
    parents: Dict[str, str | None] = {}
    for aid, entry in agents.items():
        parent = entry.get("parent_id")
        parents[aid] = parent
        children.setdefault(parent or "__ROOT__", []).append(aid)

    # Optional filter single subtree
    roots: list[str]
    if args.id:
        roots = [args.id]
    else:
        roots = sorted(children.get("__ROOT__", []))

    def print_line(aid: str, depth: int) -> None:
        ent = agents.get(aid, {})
        cnt = ent.get("counters", {})
        mem = cnt.get("memory_lines", 0)
        ev = cnt.get("events_lines", 0)
        parent = ent.get("parent_id") or "-"
        if args.tree:
            _print(f"{'  '*depth}- {aid}  parent={parent} mem={mem} ev={ev}")
        else:
            _print(f"- {aid}  parent={parent} mem={mem} ev={ev}")

    def walk(aid: str, depth: int = 0) -> None:
        print_line(aid, depth)
        for ch in sorted(children.get(aid, [])):
            walk(ch, depth + 1)

    _print(f"cluster updated: {idx.get('updated')}")
    if args.tree:
        for r in roots:
            walk(r, 0)
    else:
        # Flat listing
        for aid in sorted(agents.keys() if not args.id else [args.id] + children.get(args.id, [])):
            print_line(aid, 0)

    return 0


def cmd_personas(args: argparse.Namespace) -> int:
    idx = scan_personas()
    items = list(idx.items())
    q = (args.search or "").lower().strip()
    tag = (args.tag or "").lower().strip()
    if q:
        items = [(aid, mf) for aid, mf in items if q in aid.lower() or q in (" ".join(mf.get("roles", [])).lower()) or q in (" ".join(mf.get("persona_tags", [])).lower())]
    if tag:
        items = [(aid, mf) for aid, mf in items if tag in (" ".join(mf.get("persona_tags", [])).lower())]
    if args.json:
        out = {aid: mf for aid, mf in items}
        _print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0
    if not items:
        _print("No personas found under personas/ (override with QJSON_PERSONAS_HOME)")
        return 0
    _print(f"Found {len(items)} personas:")
    for aid, mf in items:
        tags = ", ".join(mf.get("persona_tags", []))
        roles = ", ".join(mf.get("roles", []))
        _print(f"- {aid}  tags=[{tags}] roles=[{roles}] path={mf.get('_path','?')}")
    return 0


def cmd_cluster_test(args: argparse.Namespace, default_api: Any = None) -> int:
    base_manifest = None
    if not getattr(args, "manifests", None):
        manifest_path = Path(args.manifest) if getattr(args, "manifest", None) else Path("manifests/lila.json")
        if manifest_path.exists():
            if manifest_path.suffix.lower() == ".yson":
                base_manifest = yson_to_manifest(manifest_path)
            else:
                base_manifest = load_manifest(manifest_path)
        else:
            base_manifest = {
                "agent_id": "ClusterRoot",
                "origin": "Local",
                "creator": "qjson-agents",
                "roles": ["node"],
                "features": {
                    "recursive_memory": True,
                    "fractal_state": True,
                    "autonomous_reflection": False,
                    "emergent_behavior": "balanced",
                    "chaos_alignment": "low",
                    "symbolic_interface": "text",
                },
                "core_directives": [
                    "Participate in structured handoffs",
                    "Be concise and referential",
                    "Log anomalies",
                ],
                "runtime": {"model": "mock-llm"},
            }

    # Logs
    run_ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    logs_dir = Path("logs")
    logs_dir.mkdir(parents=True, exist_ok=True)
    base = logs_dir / f"cluster_run_{run_ts}"
    path_txt = base.with_suffix(".txt")
    path_json = base.with_suffix(".json")
    path_log = base.with_suffix(".log")

    logger = logging.getLogger("qjson_agents.cluster_test")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()
    fh = logging.FileHandler(path_log, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(fh)

    # Client selection
    class MockOllamaClient:
        def __init__(self):
            self.calls = 0

        def chat(self, *, model: str, messages: list[dict[str, str]], options: dict | None = None, stream: bool = False) -> dict:
            self.calls += 1
            prev_user = next((m.get("content", "") for m in reversed(messages) if m.get("role") == "user"), "")
            reply = f"[mock:{self.calls}] Bridge: {prev_user[:120]}"
            return {"message": {"role": "assistant", "content": reply}}

        def tags(self) -> list[dict[str, str]]:
            return [{"name": "mock-llm"}]

    use_ollama = bool(getattr(args, "use_ollama", False))
    if use_ollama:
        client = OllamaClient()
        model_to_use = args.model
        if not model_to_use:
            try:
                models = client.tags()
            except Exception as e:
                _print(f"[models] error: {e}")
                return 2
            if not models:
                _print("No local models found via /api/tags. Pull one with 'ollama pull <model>'.")
                return 2
            # Prefer a model that does not include any avoid substrings (default: 'llama')
            avoid = [s.lower() for s in (args.avoid or [])]
            def name_of(m: dict) -> str:
                return (m.get("name") or m.get("model") or "")
            preferred = None
            for m in models:
                nm = name_of(m)
                lnm = nm.lower()
                if not any(a in lnm for a in avoid):
                    preferred = nm
                    break
            model_to_use = preferred or name_of(models[0])
            _print(f"[models] selected: {model_to_use}")
    else:
        client = MockOllamaClient()
        model_to_use = "mock-llm"

    # Build agents: either from provided manifests list or one root + forks
    agents: list[Agent] = []
    created: list[str] = []
    last_reply: Dict[str, str] = {}
    if getattr(args, "manifests", None):
        manifests_list: list[Dict[str, Any]] = []
        for mp in args.manifests:
            p = Path(mp)
            if p.suffix.lower() == ".yson":
                from .yson import yson_to_manifest
                manifests_list.append(yson_to_manifest(p))
            else:
                manifests_list.append(load_manifest(p))
        for mf in manifests_list:
            ag = Agent(mf)
            agents.append(ag)
            created.append(ag.agent_id)
        n = len(agents)
        root = agents[0]
    else:
        n = max(2, int(args.agents))
        root_id = f"Cluster-{run_ts}-root"
        manifest_root = dict(base_manifest)
        manifest_root["agent_id"] = root_id
        root = Agent(manifest_root)
        agents = [root]
        created = [root_id]
        for k in range(1, n):
            child_id = f"{root_id}-n{k+1}"
            child_manifest = root.fork(child_id, note=f"cluster-test fork {k+1}/{n}")
            child = Agent(child_manifest)
            agents.append(child)
            created.append(child_id)

    # Determine start goal prompt (file > arg > seed)
    start_goal = args.seed
    if getattr(args, "goal_file", None):
        gp = Path(args.goal_file)
        if gp.exists():
            try:
                start_goal = gp.read_text(encoding="utf-8").strip()
            except Exception:
                pass
    if getattr(args, "goal_prompt", None):
        start_goal = args.goal_prompt.strip()

    # Build per-agent goals: combine global goal with agent subgoal
    per_agent_goal: Dict[str, str] = {}
    goals_list = args.goal or []
    agent_goal_list = args.agent_goal or []
    agent_goal_file_list = args.agent_goal_file or []
    for idx, ag in enumerate(agents, start=1):
        # Load minimal persona indicators
        roles = ", ".join(ag.manifest.get("roles", []))
        # Pick base subgoal by precedence: --agent-goal-file[idx], --agent-goal[idx], --goal[idx], template, default
        subgoal = None
        if idx <= len(agent_goal_file_list) and agent_goal_file_list[idx-1]:
            gp = Path(agent_goal_file_list[idx-1])
            if gp.exists():
                try:
                    subgoal = gp.read_text(encoding="utf-8").strip()
                except Exception:
                    subgoal = None
        if subgoal is None and idx <= len(agent_goal_list) and agent_goal_list[idx-1]:
            subgoal = agent_goal_list[idx-1]
        if subgoal is None and idx <= len(goals_list) and goals_list[idx-1]:
            subgoal = goals_list[idx-1]
        if subgoal is None and args.goal_template:
            subgoal = (
                args.goal_template
                .replace("{agent_id}", ag.agent_id)
                .replace("{roles}", roles)
                .replace("{index}", str(idx))
            )
        if subgoal is None:
            subgoal = f"Advance the cluster objective leveraging your persona (roles: {roles})."
        # Inject persona-specific tokens to improve router diversity
        combined = (
            f"Global Goal: {start_goal}\n"
            f"Subgoal for {ag.agent_id}: {subgoal}\n"
            f"Keywords: agent_id={ag.agent_id}; roles={roles}"
        )
        per_agent_goal[ag.agent_id] = combined

    # Choose summarizer (flags override, else role-based; fallback to root)
    def is_summarizer_role(ag: Agent) -> bool:
        roles = " ".join(ag.manifest.get("roles", [])).lower()
        for kw in ("observer", "coordinator", "weaver", "summarizer"):
            if kw in roles:
                return True
        return False

    summarizer_agent = None
    if getattr(args, "summarizer_id", None):
        summarizer_agent = next((a for a in agents if a.agent_id == args.summarizer_id), None)
    if summarizer_agent is None and getattr(args, "summarizer_index", None):
        si = int(args.summarizer_index)
        if 1 <= si <= len(agents):
            summarizer_agent = agents[si - 1]
    if summarizer_agent is None and getattr(args, "summarizer_role", None):
        needle = args.summarizer_role.lower()
        summarizer_agent = next((a for a in agents if needle in " ".join(a.manifest.get("roles", [])).lower()), None)
    if summarizer_agent is None:
        summarizer_agent = next((a for a in agents if is_summarizer_role(a)), root)

    # Precompute lightweight TF-IDF on role+goal tokens per agent (for router)
    def tokenize(text: str) -> list[str]:
        t = "".join(ch.lower() if ch.isalnum() or ch.isspace() else " " for ch in (text or ""))
        toks = [x for x in t.split() if x]
        return toks

    def bigrams(toks: list[str]) -> list[str]:
        return [f"{toks[i]}_{toks[i+1]}" for i in range(len(toks)-1)] if len(toks) > 1 else []

    agent_docs: Dict[str, Dict[str, int]] = {}
    df: Dict[str, int] = {}
    for ag in agents:
        doc_toks = tokenize(
            " ".join(ag.manifest.get("roles", [])) + " " + per_agent_goal.get(ag.agent_id, "")
        )
        doc_toks += bigrams(doc_toks)
        tf: Dict[str, int] = {}
        for tok in doc_toks:
            tf[tok] = tf.get(tok, 0) + 1
        agent_docs[ag.agent_id] = tf
        for tok in set(doc_toks):
            df[tok] = df.get(tok, 0) + 1
    Ndocs = max(1, len(agents))
    idf: Dict[str, float] = {tok: math.log(1.0 + Ndocs / (1.0 + c)) for tok, c in df.items()}

    # Rate limiting (cooldown seconds) and router weights
    cooldown = float(getattr(args, "rate_limit_cooldown", 0.0) or 0.0)
    last_selected_ts: Dict[str, float] = {ag.agent_id: 0.0 for ag in agents}
    router_weights = load_router_weights()

    # Determine start goal prompt (file > arg > seed)
    start_goal = args.seed
    if getattr(args, "goal_file", None):
        gp = Path(args.goal_file)
        if gp.exists():
            try:
                start_goal = gp.read_text(encoding="utf-8").strip()
            except Exception:
                pass
    if getattr(args, "goal_prompt", None):
        start_goal = args.goal_prompt.strip()

    # Shared baton text (for moe/mesh); for ring we still use pairwise
    baton_text = start_goal

    # Helper to create dynamic priming between ticks
    swarm_logic = getattr(args, "swarm_logic", {}) or {}
    # Template library for priming
    def _template_debate(tick: int, baton: str, peers: Dict[str, str]) -> str:
        pros = []
        cons = []
        for aid, txt in peers.items():
            if isinstance(txt, str) and txt.strip():
                (pros if len(pros) <= len(cons) else cons).append(f"- {aid}: {txt[:160]}")
        return (
            f"Debate baton: {baton}\n"
            f"Arguments (pro):\n" + "\n".join(pros[:3]) + "\n"
            f"Arguments (con):\n" + "\n".join(cons[:3]) + "\n"
            f"Instruction: Present a concise stance, address one opposing point, and ask one clarifying question."
        )

    def _template_critique(tick: int, baton: str, peers: Dict[str, str]) -> str:
        pts = []
        for aid, txt in peers.items():
            if isinstance(txt, str) and txt.strip():
                pts.append(f"- {aid}: {txt[:160]}")
        return (
            f"Critique baton: {baton}\n"
            f"Peer excerpts:\n" + "\n".join(pts[:5]) + "\n"
            f"Instruction: Provide a structured critique (strength, weakness, suggestion) and end with one actionable step."
        )

    def _template_qa(tick: int, baton: str, peers: Dict[str, str]) -> str:
        last = []
        for aid, txt in peers.items():
            if isinstance(txt, str) and txt.strip():
                last.append(f"Q to {aid}: What key assumption underlies your point?\nA guess: {txt[:140]}")
        return (
            f"Q&A baton: {baton}\n" + "\n".join(last[:4]) + "\n"
            f"Instruction: Ask one targeted question and answer one prior question concisely, then propose a next step."
        )

    priming_template = None
    try:
        scfg = getattr(args, "swarm_config", {}) or {}
        priming_template = scfg.get("priming_template") or (scfg.get("priming", {}) or {}).get("template")
    except Exception:
        priming_template = None

    def make_priming_text(tick: int, baton: str, last_map: Dict[str, str]) -> str:
        try:
            fn = swarm_logic.get("make_priming") if isinstance(swarm_logic, dict) else None
            if callable(fn):
                return str(fn(tick=tick, baton=baton, peers=last_map))
        except Exception:
            pass
        # Template-based priming
        if priming_template == "debate":
            return _template_debate(tick, baton, last_map)
        if priming_template == "critique":
            return _template_critique(tick, baton, last_map)
        if priming_template in ("qa", "q&a"): 
            return _template_qa(tick, baton, last_map)
        # Default priming: include baton and peer snippets
        peers = []
        for aid, txt in last_map.items():
            if isinstance(txt, str) and txt.strip():
                peers.append(f"- {aid}: {txt[:220]}")
        peer_block = "\n".join(peers[:5])
        return (
            f"Baton: {baton}\n"
            f"Peer notes (last replies):\n{peer_block}\n"
            f"Instruction: Address peer points directly; ask and answer one clarifying question to the previous expert if applicable."
        )

    # Run handoffs according to topology
    duration = float(args.duration)
    interval = float(args.interval)
    deadline = time.time() + duration

    counters: Dict[str, Dict[str, int]] = {aid: {"chat": 0, "errors": 0} for aid in created}
    events: list[Dict[str, Any]] = []

    _print(f"Starting cluster test with {n} agents for {duration}s")
    logger.info(f"cluster start: agents={created} model={model_to_use} duration={duration}s interval={interval}s")

    # Seed first handoff and persist goal metadata into FMM
    last_reply[root.agent_id] = f"[goal] {start_goal}"
    events.append({
        "t": time.time(),
        "type": "input_goal",
        "text": start_goal,
    })
    try:
        from .fmm_store import PersistentFractalMemory
        for ag in agents:
            fmm = PersistentFractalMemory(ag.agent_id)
            fmm.insert(["goals", "runs", run_ts], {
                "global_goal": start_goal,
                "agent_goal": per_agent_goal.get(ag.agent_id, ""),
                "model": model_to_use,
                "topology": args.topology,
            })
    except Exception:
        pass

    i = 0
    start_ts = time.time()
    try:
        while time.time() < deadline:
            topo = args.topology
            if topo == "ring":
                cur_idx = i % n
                prev_idx = (i - 1) % n
                cur = agents[cur_idx]
                prev = agents[prev_idx]
                handoff_text = last_reply.get(prev.agent_id, baton_text)
                priming = make_priming_text(i + 1, handoff_text, last_reply)
                prompt = (
                    f"Handoff from {prev.agent_id} to {cur.agent_id}.\n"
                    f"Priming:\n{priming}\n"
                    f"Your goal: {per_agent_goal.get(cur.agent_id, '')}\n"
                    f"Discuss with peers and advance the baton."
                )
                try:
                    reply = cur.chat_turn(prompt, client=client, model_override=model_to_use)
                    last_reply[cur.agent_id] = reply
                    counters[cur.agent_id]["chat"] += 1
                    events.append({
                        "t": time.time(),
                        "type": "handoff",
                        "from": prev.agent_id,
                        "to": cur.agent_id,
                        "prompt": prompt,
                        "reply": reply,
                        "tick": i + 1,
                    })
                    logger.debug(f"handoff[{i+1}] {prev.agent_id} -> {cur.agent_id}")
                except Exception as e:
                    counters[cur.agent_id]["errors"] += 1
                    events.append({"t": time.time(), "type": "error", "agent": cur.agent_id, "error": str(e)})
                    logger.exception(f"handoff[{i+1}] error for {cur.agent_id}: {e}")
                i += 1
            elif topo == "mesh":
                # Broadcast the same handoff state to all agents, collect replies
                prev_idx = (i - 1) % n
                prev = agents[prev_idx]
                handoff_text = baton_text or last_reply.get(prev.agent_id, args.seed)
                priming = make_priming_text(i + 1, handoff_text, last_reply)
                for idx, cur in enumerate(agents):
                    prompt = (
                        f"Broadcast to {cur.agent_id}.\n"
                        f"Priming:\n{priming}\n"
                        f"Your goal: {per_agent_goal.get(cur.agent_id, '')}\n"
                        f"Discuss with peers and advance the baton."
                    )
                    try:
                        reply = cur.chat_turn(prompt, client=client, model_override=model_to_use)
                        last_reply[cur.agent_id] = reply
                        counters[cur.agent_id]["chat"] += 1
                        events.append({
                            "t": time.time(),
                            "type": "broadcast",
                            "from": prev.agent_id,
                            "to": cur.agent_id,
                            "prompt": prompt,
                            "reply": reply,
                            "tick": i + 1,
                        })
                        logger.debug(f"broadcast[{i+1}] -> {cur.agent_id}")
                    except Exception as e:
                        counters[cur.agent_id]["errors"] += 1
                        events.append({"t": time.time(), "type": "error", "agent": cur.agent_id, "error": str(e)})
                        logger.exception(f"broadcast[{i+1}] error for {cur.agent_id}: {e}")
                # Simple aggregation: set baton to last reply in order (deterministic)
                if agents:
                    last = last_reply.get(agents[-1].agent_id)
                    if isinstance(last, str) and last.strip():
                        baton_text = last
                i += 1
            elif topo == "mixed":
                # Mesh for first M ticks then MoE
                M = max(1, int(getattr(args, "mixed_mesh_ticks", 3)))
                args.topology = "mesh" if i < M else "moe"
                continue  # loop to apply one of the branches next iteration
            else:  # moe
                prev_idx = (i - 1) % n
                prev = agents[prev_idx]
                handoff_text = baton_text or last_reply.get(prev.agent_id, args.seed)
                priming = make_priming_text(i + 1, handoff_text, last_reply)

                # Router with unigram+bigrams TF-IDF overlap and cooldown penalty
                baton_toks = tokenize(handoff_text)
                baton_toks += bigrams(baton_toks)
                baton_set = set(baton_toks)

                def score_agent(ag: Agent) -> float:
                    now = time.time()
                    # Cooldown hard penalty
                    if cooldown > 0 and (now - last_selected_ts.get(ag.agent_id, 0.0)) < cooldown:
                        return -1e9
                    tf = agent_docs.get(ag.agent_id, {})
                    s = 0.0
                    for tok in baton_set:
                        if tok in tf:
                            s += tf[tok] * idf.get(tok, 0.0)
                    # Add persistent router weight bias
                    s += float(router_weights.get(ag.agent_id, 0.0))
                    # Mild penalty if same as prev
                    if ag.agent_id == prev.agent_id:
                        s -= 0.5
                    # Mild recency penalty by ticks since selection
                    last_ts = last_selected_ts.get(ag.agent_id, 0.0)
                    if last_ts > 0:
                        s -= 0.1 / max(1e-3, now - last_ts)
                    return s

                # Compute scores for telemetry
                score_map = {ag.agent_id: score_agent(ag) for ag in agents}
                ranked = sorted(agents, key=lambda a: score_map.get(a.agent_id, 0.0), reverse=True)
                k = max(1, int(args.moe_topk))
                experts = ranked[: min(k, n)]
                agg_parts: list[str] = []
                chosen_ids: list[str] = []
                for cur in experts:
                    prompt = (
                        f"MoE expert call to {cur.agent_id}.\n"
                        f"Priming:\n{priming}\n"
                        f"Your goal: {per_agent_goal.get(cur.agent_id, '')}\n"
                        f"Discuss with peers and advance the baton."
                    )
                    try:
                        reply = cur.chat_turn(prompt, client=client, model_override=model_to_use)
                        last_reply[cur.agent_id] = reply
                        counters[cur.agent_id]["chat"] += 1
                        last_selected_ts[cur.agent_id] = time.time()
                        chosen_ids.append(cur.agent_id)
                        agg_parts.append(f"{cur.agent_id}: {reply.strip()[:200]}")
                        events.append({
                            "t": time.time(),
                            "type": "moe",
                            "expert": cur.agent_id,
                            "prompt": prompt,
                            "reply": reply,
                            "tick": i + 1,
                            "router_scores": score_map,
                        })
                        logger.debug(f"moe[{i+1}] expert {cur.agent_id}")
                    except Exception as e:
                        counters[cur.agent_id]["errors"] += 1
                        events.append({"t": time.time(), "type": "error", "agent": cur.agent_id, "error": str(e)})
                        logger.exception(f"moe[{i+1}] error for {cur.agent_id}: {e}")
                # Aggregate expert outputs using a summarizer agent to produce a concise baton
                if agg_parts:
                    aggregate_text = "\n".join(agg_parts)
                    # Baton compression targets from swarm runtime if provided
                    baton_sentences = None
                    baton_chars = None
                    try:
                        swcfg = getattr(args, "swarm_logic", {}) or {}
                        # If config available under args, prefer config keys
                        # else try in yson body runtime (passed indirectly)
                    except Exception:
                        swcfg = {}
                    # Also try reading from YSON config in args via a separate channel if provided
                    try:
                        body_cfg = getattr(args, "swarm_config", {}) or {}
                    except Exception:
                        body_cfg = {}
                    rt_cfg = {}
                    if isinstance(body_cfg, dict):
                        rt_cfg = body_cfg.get("runtime", {}) or {}
                    baton_sentences = rt_cfg.get("baton_sentences")
                    baton_chars = rt_cfg.get("baton_chars")
                    limit_str = f"(<= {baton_sentences} sentences)" if baton_sentences else "(concise)"
                    sum_prompt = (
                        "You are the cluster summarizer. Aggregate the following expert notes into a single, concise baton "
                        f"{limit_str} that maintains continuity for the next step.\n\n" + aggregate_text
                    )
                    try:
                        agg_model = args.summarizer_model or model_to_use
                        baton = summarizer_agent.chat_turn(sum_prompt, client=client, model_override=agg_model)
                    except Exception as e:
                        baton = " | ".join(agg_parts)
                        logger.exception(f"aggregate error: {e}")
                    # Apply hard limits if requested
                    if isinstance(baton_chars, int) and baton_chars > 0 and isinstance(baton, str):
                        baton = baton[:baton_chars]
                    if isinstance(baton_sentences, int) and baton_sentences > 0 and isinstance(baton, str):
                        parts = baton.split(". ")
                        if len(parts) > baton_sentences:
                            baton = ". ".join(parts[:baton_sentences]).strip()
                    baton_text = baton
                    events.append({
                        "t": time.time(),
                        "type": "aggregate",
                        "summarizer": summarizer_agent.agent_id,
                        "prompt": sum_prompt,
                        "reply": baton,
                        "tick": i + 1,
                    })
                    # Persist baton into summarizer's fractal store
                    try:
                        from .fmm_store import PersistentFractalMemory
                        fmm = PersistentFractalMemory(summarizer_agent.agent_id)
                        fmm.insert(["moe", "baton"], {"tick": i + 1, "text": baton})
                    except Exception:
                        pass
                i += 1

            if interval > 0:
                time.sleep(interval)
    finally:
        elapsed = time.time() - start_ts
        summary: Dict[str, Any] = {
            "agents": created,
            "model": model_to_use,
            "use_ollama": use_ollama,
            "ticks": i,
            "elapsed_sec": round(elapsed, 3),
            "counts": counters,
            "events": events,
        }
        with path_json.open("w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)

        with path_txt.open("w", encoding="utf-8") as f:
            f.write(f"Cluster test {run_ts}\n")
            f.write(f"Agents: {', '.join(created)}\n")
            f.write(f"Summarizer: {summarizer_agent.agent_id}\n")
            f.write(f"Model: {model_to_use} (ollama={use_ollama})\n")
            f.write(f"Duration: {round(elapsed, 3)}s\n")
            f.write(f"Start goal: {start_goal}\n")
            for aid in created:
                f.write(f"- {aid}: {counters[aid]}\n")
            # Dialogue transcript
            f.write("\n--- Dialogues ---\n")
            for e in events:
                t = e.get("type")
                if "reply" in e:
                    if t == "handoff":
                        f.write(f"[tick {e.get('tick')}] handoff {e.get('from')} -> {e.get('to')}\n")
                    elif t == "broadcast":
                        f.write(f"[tick {e.get('tick')}] broadcast -> {e.get('to')}\n")
                    elif t == "moe":
                        f.write(f"[tick {e.get('tick')}] moe expert {e.get('expert')}\n")
                    elif t == "aggregate":
                        f.write(f"[tick {e.get('tick')}] aggregate by {e.get('summarizer')}\n")
                    if 'prompt' in e:
                        f.write(f"  prompt: {e.get('prompt').strip()}\n")
                    f.write(f"  reply: {str(e.get('reply')).strip()}\n\n")

        logger.info(f"cluster end: ticks={i} elapsed={round(elapsed,3)}s")
        # Update router weights to encourage under-used experts
        try:
            counts = {aid: counters.get(aid, {}).get("chat", 0) for aid in created}
            mean = sum(counts.values()) / max(1, len(counts))
            # Learning rate
            alpha = 0.05
            for aid, c in counts.items():
                delta = (mean - c) / max(1.0, mean)
                router_weights[aid] = float(router_weights.get(aid, 0.0) + alpha * delta)
            save_router_weights(router_weights)
        except Exception:
            pass

    _print("Cluster test outputs:")
    _print(f"- {path_txt}")
    _print(f"- {path_json}")
    _print(f"- {path_log}")
    return 0


def cmd_analyze(args: argparse.Namespace) -> int:
    p = Path(args.path)
    if not p.exists():
        _print(f"Not found: {p}")
        return 2
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        _print(f"Failed to read JSON: {e}")
        return 2

    # Elapsed time
    elapsed = float(data.get("elapsed_sec") or 0.0)
    counts = data.get("counts") or {}
    events = data.get("events") or []

    # Non-empty reply ratio (for any event with a 'reply' field)
    replies = [e.get("reply") for e in events if "reply" in e]
    nonempty = [r for r in replies if isinstance(r, str) and r.strip()]
    nonempty_ratio = (len(nonempty) / max(1, len(replies))) if replies else 0.0

    # Tokens per second (rough): whitespace tokens in replies over elapsed
    def tokens_in(text: str) -> int:
        try:
            return len(text.split())
        except Exception:
            return 0
    total_tokens = sum(tokens_in(r) for r in nonempty)
    tps = (total_tokens / elapsed) if elapsed > 0 else 0.0

    # Imbalance across agents using chat counts
    chat_counts = []
    for aid, c in counts.items():
        if isinstance(c, dict):
            chat_counts.append(int(c.get("chat") or 0))
    mean = (sum(chat_counts) / len(chat_counts)) if chat_counts else 0.0
    var = (sum((x - mean) ** 2 for x in chat_counts) / len(chat_counts)) if chat_counts else 0.0
    std = math.sqrt(var)
    cov = (std / mean) if mean > 0 else 0.0
    max_min = (max(chat_counts) - min(chat_counts)) if chat_counts else 0

    # Per-agent token counts and TPS by attributing replies
    per_agent_tokens: Dict[str, int] = {aid: 0 for aid in counts.keys()}
    for e in events:
        rep = e.get("reply")
        if not (isinstance(rep, str) and rep.strip()):
            continue
        tokens = tokens_in(rep)
        # Attribute by event type
        if e.get("type") == "moe":
            aid = e.get("expert")
        elif e.get("type") == "handoff":
            aid = e.get("to")
        elif e.get("type") == "broadcast":
            aid = e.get("to")
        elif e.get("type") == "aggregate":
            aid = e.get("summarizer")
        else:
            aid = None
        if isinstance(aid, str) and aid in per_agent_tokens:
            per_agent_tokens[aid] += tokens

    per_agent_tps = {aid: (tok / elapsed if elapsed > 0 else 0.0) for aid, tok in per_agent_tokens.items()}

    # MoE expert selection distribution
    moe_counts: Dict[str, int] = {aid: 0 for aid in counts.keys()}
    total_moe = 0
    for e in events:
        if e.get("type") == "moe":
            aid = e.get("expert")
            if isinstance(aid, str) and aid in moe_counts:
                moe_counts[aid] += 1
                total_moe += 1
    moe_dist = {aid: (c / total_moe if total_moe else 0.0) for aid, c in moe_counts.items()}

    metrics = {
        "path": str(p),
        "elapsed_sec": round(elapsed, 3),
        "events_with_reply": len(replies),
        "nonempty_replies": len(nonempty),
        "nonempty_ratio": round(nonempty_ratio, 3),
        "total_tokens": total_tokens,
        "tokens_per_sec": round(tps, 2),
        "agents": list(counts.keys()),
        "chat_counts": counts,
        "per_agent_tokens": per_agent_tokens,
        "per_agent_tps": {k: round(v, 2) for k, v in per_agent_tps.items()},
        "moe_distribution": {k: round(v, 3) for k, v in moe_dist.items()},
        "imbalance": {
            "std": round(std, 3),
            "cov": round(cov, 3),
            "max_min": max_min,
        },
    }

    # Optional compare with another run for fairness
    if getattr(args, "compare", None):
        try:
            other = json.loads(Path(args.compare).read_text(encoding="utf-8"))
        except Exception as e:
            _print(f"compare read error: {e}")
            other = None
        if other:
            o_counts = other.get("counts") or {}
            o_events = other.get("events") or []
            # Build MoE distributions
            def moe_dist_of(evts, cnts):
                names = list(cnts.keys())
                c = {n: 0 for n in names}
                tot = 0
                for e in evts:
                    if e.get("type") == "moe":
                        expert = e.get("expert")
                        if expert in c:
                            c[expert] += 1
                            tot += 1
                return {k: (v / tot if tot else 0.0) for k, v in c.items()}
            d0 = moe_dist_of(events, counts)
            d1 = moe_dist_of(o_events, o_counts)
            metrics["compare"] = {
                "path": args.compare,
                "moe_baseline": d1,
                "moe_current": d0,
            }

    if args.json:
        _print(json.dumps(metrics, ensure_ascii=False, indent=2))
    else:
        _print(f"path: {metrics['path']}")
        _print(f"elapsed: {metrics['elapsed_sec']}s")
        _print(f"replies: {metrics['nonempty_replies']}/{metrics['events_with_reply']} (ratio={metrics['nonempty_ratio']})")
        _print(f"tokens: {metrics['total_tokens']}  tps: {metrics['tokens_per_sec']}")
        _print("per-agent tps:")
        for aid, tpsv in metrics["per_agent_tps"].items():
            _print(f"- {aid}: {tpsv}")
        _print("moe distribution:")
        for aid, frac in metrics["moe_distribution"].items():
            _print(f"- {aid}: {frac}")
        _print(f"agents: {', '.join(metrics['agents'])}")
        _print(f"imbalance std={metrics['imbalance']['std']} cov={metrics['imbalance']['cov']} max-min={metrics['imbalance']['max_min']}")
        if metrics.get("compare"):
            _print("-- compare fairness --")
            cmp = metrics["compare"]
            _print(f"baseline: {cmp['path']}")
            _print(f"moe baseline: {cmp['moe_baseline']}")
            _print(f"moe current:  {cmp['moe_current']}")

    return 0


def cmd_ingest(args: argparse.Namespace, default_api: Any = None) -> int:
    agent_id = args.id
    text = " ".join(args.text).strip()
    if not text:
        _print("Empty text")
        return 2
    ensure_agent_dirs(agent_id)
    # Append as a system memory line
    from .memory import append_jsonl as _append, _now_ts as _now
    _append(agent_dir(agent_id) / "memory.jsonl", {"ts": _now(), "role": "system", "content": text, "meta": {"source": "cli:ingest"}})
    # Insert into retrieval store
    try:
        from .retrieval import add_memory as _add
        _add(agent_id, text, {"source": "cli:ingest"})
    except Exception as e:
        _print(f"[retrieval] skip: {e}")
    _print(f"[ingest] ok -> {agent_id}")
    return 0


def cmd_ingest_batch(args: argparse.Namespace, default_api: Any = None) -> int:
    agent_id = args.id
    n = max(1, int(args.count))
    tpl = str(args.template)
    ensure_agent_dirs(agent_id)
    items = []
    from .memory import append_jsonl as _append, _now_ts as _now
    for i in range(n):
        s = tpl.replace("{i}", str(i))
        _append(agent_dir(agent_id) / "memory.jsonl", {"ts": _now(), "role": "system", "content": s, "meta": {"source": "cli:ingest-batch"}})
        items.append((s, {"source": "cli:ingest-batch", "i": i}, None))
    try:
        from .retrieval import add_batch as _addb
        _addb(agent_id, items)
    except Exception as e:
        _print(f"[retrieval] batch skip: {e}")
    _print(f"[ingest-batch] ok {n} -> {agent_id}")
    return 0


def cmd_reindex(args: argparse.Namespace, default_api: Any = None) -> int:
    agent_id = args.id
    ensure_agent_dirs(agent_id)
    k = max(2, int(args.k))
    iters = max(1, int(args.iters))
    try:
        from .retrieval import _ensure_db as _db, _ivf_build as _build
        con = _db()
        _build(agent_id, con, K=k, iters=iters)
        _print(f"[reindex] ok -> {agent_id} K={k} iters={iters}")
        return 0
    except Exception as e:
        _print(f"[reindex] error: {e}")
        return 1


def cmd_menu(args: argparse.Namespace) -> int:
    try:
        from .menu import run_menu
    except Exception as e:
        _print(f"menu error: {e}")
        return 1
    run_menu()
    return 0


def cmd_crawl_cli(args: argparse.Namespace, default_api: Any = None) -> int:
    # Non-interactive crawl: seeds -> outlines -> index + save manifest
    seeds = list(args.seeds or [])
    if not seeds:
        _print("Provide at least one --seeds URL.")
        return 2
    try:
        depth = max(0, int(args.depth))
        pages = max(1, int(args.pages))
        rate = float(args.rate)
    except Exception as e:
        _print(f"Invalid numeric arg: {e}")
        return 2
    agent_id = args.id or os.environ.get("QJSON_AGENT_ID") or "WebCrawler"
    ensure_agent_dirs(agent_id)
    # Run crawl
    try:
        cr = Crawler(rate_per_host=rate)
        allowed = list(args.allowed_domain or []) if args.allowed_domain else None
        outlines = cr.crawl(seeds, max_depth=depth, max_pages=pages, allowed_domains=allowed)
    except Exception as e:
        _print(f"[crawl] error: {e}")
        return 1
    # Index and persist manifest
    ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    out_dir = agent_dir(agent_id) / "crawl"
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "agent_id": agent_id,
        "ts": ts,
        "seeds": seeds,
        "depth": depth,
        "pages": pages,
        "rate": rate,
        "count": len(outlines),
    }
    try:
        for o in outlines:
            try:
                upsert_outline(agent_id, o)
            except Exception:
                pass
        # Optional per-page JSON exports
        if args.export_json:
            out_pages = Path(args.export_json)
            out_pages.mkdir(parents=True, exist_ok=True)
            def _slug(s: str) -> str:
                s = (s or "untitled").strip().lower()
                import re
                s = re.sub(r"[^a-z0-9]+","-", s)
                return s.strip("-") or "doc"
            for o in outlines:
                title = o.get("title") or o.get("url") or "page"
                fname = _slug(title)[:64] + ".json"
                (out_pages / fname).write_text(json.dumps(o, ensure_ascii=False, indent=2), encoding="utf-8")
            _print(f"[crawl] exported {len(outlines)} outline(s) -> {out_pages}")
        # Save outlines summary to file
        save_path = out_dir / f"crawl_{ts}.json"
        with save_path.open("w", encoding="utf-8") as f:
            json.dump({**manifest, "outlines": outlines}, f, ensure_ascii=False, indent=2)
        _print(f"[crawl] saved -> {save_path}")
    except Exception as e:
        _print(f"[crawl] save error: {e}")
    _print(f"[crawl] indexed {len(outlines)} page(s) for agent {agent_id}")
    return 0


def cmd_exec(args: argparse.Namespace, default_api: Any = None) -> int:
    """Execute a single slash-style command non-interactively.

    Supports: /crawl (plugin), /open N, /setenv KEY=VALUE, /langsearch key <KEY>.
    """
    # Load persisted env and set agent id for plugins
    try:
        _load_persistent_env()
    except Exception:
        pass
    if getattr(args, "id", None):
        try:
            os.environ["QJSON_AGENT_ID"] = args.id
            ensure_agent_dirs(args.id)
        except Exception:
            pass

    raw = str(args.command or "").strip()
    if not raw:
        _print("Provide a slash command to execute, e.g., '/find https://example.com depth=1 pages=5'")
        return 2
    if not raw.startswith("/"):
        raw = "/" + raw

    # Minimal plugin/tool wiring
    def _google_web_search_wrapper(query: str) -> dict:
        if default_api is None or not hasattr(default_api, "google_web_search"):
            raise RuntimeError("default_api.google_web_search not available")
        return default_api.google_web_search(query=query)
    tools = {"google_web_search": _google_web_search_wrapper}
    plugins = load_plugins(tools=tools)
    plugin_commands: Dict[str, Any] = {}
    for plugin in plugins:
        plugin_commands.update(plugin.get_commands())

    parts = raw.split()
    command = parts[0]

    # Core unified commands first
    if command == "/engine":
        val = raw.replace("/engine", "", 1).strip()
        if val.startswith("mode="):
            m = val.split("=",1)[1].strip().lower()
            if m in ("online","local"):
                os.environ["QJSON_ENGINE_DEFAULT"] = m
                try:
                    _save_persistent_env("QJSON_ENGINE_DEFAULT", m)
                except Exception:
                    pass
                _print(f"[engine] mode set to {m}")
                return 0
        _print("Usage: /engine mode=online|local")
        return 2
    if command == "/find":
        arg = raw.replace("/find", "", 1).strip()
        return _engine_find(arg, default_mode=os.environ.get("QJSON_ENGINE_DEFAULT","online"), agent_id=args.id or os.environ.get("QJSON_AGENT_ID"), default_api=default_api)
    if command == "/open":
        arg = raw.replace("/open", "", 1).strip()
        toks = [t for t in arg.split() if t]
        # For exec, support only injection, not ingestion
        if not toks:
            _print("Usage: /open N [raw|text]")
            return 2
        mode_once = None
        idx_tokens: list[str] = []
        for t in toks:
            tl = t.lower()
            if tl in ("raw","text"):
                mode_once = tl
            else:
                idx_tokens.append(t)
        indices = _parse_indices(idx_tokens)
        if not indices:
            _print("Usage: /open N [raw|text]")
            return 2
        # Load persisted cache if not in env
        cache = os.environ.get("QJSON_WEBRESULTS_CACHE") or os.environ.get("QJSON_WEBSEARCH_RESULTS_ONCE")
        if not cache:
            try:
                _load_persistent_env()
                cache = os.environ.get("QJSON_WEBRESULTS_CACHE") or os.environ.get("QJSON_WEBSEARCH_RESULTS_ONCE")
            except Exception:
                pass
        if not cache:
            _print("[open] No cached results. Run /find or /crawl first.")
            return 2
        if mode_once:
            try:
                os.environ["QJSON_WEBOPEN_MODE_ONCE"] = mode_once
            except Exception:
                pass
        os.environ.setdefault("QJSON_WEBOPEN_HEADER", "### Search Page Content")
        _print(_arm_webopen_from_results(indices[-1], cache))
        return 0

    if command in ("/engine_scope","/webscope"):
        parts2 = raw.split()
        if len(parts2) == 1 or (len(parts2) >= 2 and parts2[1] == "show"):
            roots = os.environ.get("QJSON_LOCAL_SEARCH_ROOTS", "")
            _print(f"[engine_scope] roots={roots or os.getcwd()}")
            return 0
        if len(parts2) >= 2 and parts2[1] == "clear":
            os.environ.pop("QJSON_LOCAL_SEARCH_ROOTS", None)
            try:
                _save_persistent_env("QJSON_LOCAL_SEARCH_ROOTS", "")
            except Exception:
                pass
            _print("[engine_scope] cleared; defaulting to current directory")
            return 0
        if len(parts2) >= 3 and parts2[1] in ("add","set"):
            mode = parts2[1]
            paths = parts2[2:]
            existing = os.environ.get("QJSON_LOCAL_SEARCH_ROOTS", "").split(os.pathsep) if mode == "add" else []
            merged = [p for p in existing if p]
            for p in paths:
                pr = os.path.expanduser(os.path.expandvars(p))
                if os.path.isdir(pr):
                    merged.append(pr)
            val = os.pathsep.join(dict.fromkeys(merged))
            os.environ["QJSON_LOCAL_SEARCH_ROOTS"] = val
            try:
                _save_persistent_env("QJSON_LOCAL_SEARCH_ROOTS", val)
            except Exception:
                pass
            _print(f"[engine_scope] roots set: {val}")
            return 0
        _print("Usage: /engine_scope show|add <PATH...>|set <PATH...>|clear")
        return 2

    # Deprecated /websearch, /webopen, /crawlopen removed; use /find and /open

    # Plugin commands last
    if command in plugin_commands:
        try:
            result = plugin_commands[command](*parts[1:])
            _print(result)
            return 0
        except Exception as e:
            _print(f"Error executing plugin command {command}: {e}")
            return 1

    # Built-ins: /setenv, /langsearch

    if command == "/setenv":
        arg = raw.replace("/setenv", "", 1).strip()
        if "=" not in arg:
            _print("Usage: /setenv KEY=VALUE")
            return 2
        k, v = arg.split("=", 1)
        k = k.strip()
        os.environ[k] = v
        _save_persistent_env(k, v)
        _print(f"[env] set {k} (persisted)")
        return 0

    if command == "/langsearch":
        parts2 = parts[1:]
        if len(parts2) >= 2 and parts2[0].lower() == "key":
            key = " ".join(parts2[1:]).strip()
            os.environ["LANGSEARCH_API_KEY"] = key
            _save_persistent_env("LANGSEARCH_API_KEY", key)
            _print("[langsearch] API key set and persisted.")
            return 0
        _print("Usage: /langsearch key <KEY>")
        return 2

    _print(f"Unsupported exec command: {command}")
    return 2


def cmd_encode_manifest(args: argparse.Namespace, default_api: Any = None) -> int:
    inp = Path(args.inp)
    outp = Path(args.outp)
    if not inp.exists():
        _print(f"Input not found: {inp}")
        return 2
    data = json.loads(inp.read_text(encoding="utf-8"))
    from .fractal_codec import fractal_encrypt
    env = fractal_encrypt(data, args.passphrase, depth=int(args.depth), fanout=int(args.fanout))
    outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_text(json.dumps(env, ensure_ascii=False, indent=2), encoding="utf-8")
    _print(f"Wrote envelope -> {outp}")
    return 0


def cmd_decode_manifest(args: argparse.Namespace, default_api: Any = None) -> int:
    inp = Path(args.inp)
    outp = Path(args.outp)
    if not inp.exists():
        _print(f"Input not found: {inp}")
        return 2
    env = json.loads(inp.read_text(encoding="utf-8"))
    from .fractal_codec import fractal_decrypt
    obj = fractal_decrypt(env, args.passphrase)
    outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    _print(f"Wrote manifest -> {outp}")
    return 0



def cmd_ysonx_convert(args: argparse.Namespace, default_api: Any = None) -> int:
    src = Path(args.input)
    out_dir = Path(args.output_dir) if args.output_dir else src if src.is_dir() else src.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    def convert_file(p: Path) -> None:
        try:
            text = p.read_text(encoding="utf-8")
        except Exception as e:
            _print(f"[skip] {p}: {e}")
            return
        header = [
            "#@version: ysonx/1.0",
            f"#@source: {p.name}",
        ]
        body = text
        # If JSON, try to pretty-wrap into a simple YSONX persona
        try:
            if p.suffix.lower() == ".json":
                mf = json.loads(text)
                agent_id = mf.get("agent_id") or p.stem
                creator = mf.get("creator") or "unknown"
                origin = mf.get("origin") or "unknown"
                roles = mf.get("roles") or ["observer"]
                runtime = mf.get("runtime") or {}
                y = []
                y.append("#@type: self-evolving-agent")
                y.append("identity:")
                y.append(f"  id: {agent_id}")
                y.append(f"  roles: {roles}")
                y.append(f"  origin: {origin}")
                y.append(f"  creator: {creator}")
                y.append("runtime:")
                y.append(f"  model: {runtime.get('model','gemma3:4b')}")
                y.append(f"  tokens_max: {runtime.get('num_predict', runtime.get('num_ctx', 4096))}")
                y.append("goals:")
                y.append("  global: \"Refine capabilities safely; document steps.\"")
                y.append("  local: [\"Summarize inputs\", \"Propose safe improvements\"]")
                y.append("logic:")
                y.append("  startup: |\n    def on_start():\n        pass")
                y.append("mutation:\n  enabled: true\n  entropy_score: 0.5")
                body = "\n".join(y)
        except Exception:
            pass

        outp = out_dir / (p.stem + ".ysonx")
        outp.write_text("\n".join(header) + "\n" + body + "\n", encoding="utf-8")
        _print(f"[ok] {p} -> {outp}")

    if src.is_dir():
        for p in src.rglob("*"):
            if p.is_file() and p.suffix.lower() in (".json", ".yson"):
                convert_file(p)
    else:
        if src.suffix.lower() in (".json", ".yson"):
            convert_file(src)
        else:
            _print("Unsupported input (expect .json or .yson)")
            return 2
    return 0


def cmd_yson_validate(args: argparse.Namespace, default_api: Any = None) -> int:
    p = Path(args.path)
    if not p.exists():
        _print(f"Not found: {p}")
        return 2
    data = load_yson(p)
    body = data.get("body") or {}
    info = {
        "meta": data.get("meta", {}),
        "top_keys": list(body.keys()),
    }
    # Strict mode for swarm documents
    if getattr(args, "strict", False):
        from .yson import validate_swarm_strict
        ok, errs = validate_swarm_strict(body)
        info["strict_ok"] = ok
        if not ok:
            info["strict_errors"] = errs
    if args.json:
        _print(json.dumps(info, ensure_ascii=False, indent=2))
    else:
        _print("YSON meta:")
        _print(json.dumps(info["meta"], ensure_ascii=False, indent=2))
        _print("top-level keys: " + ", ".join(info["top_keys"]))
        if getattr(args, "strict", False):
            _print(f"strict_ok: {info.get('strict_ok', False)}")
            if not info.get('strict_ok', False):
                for e in info.get('strict_errors', []):
                    _print(f"- {e}")
    return 0


def cmd_yson_run_swarm(args: argparse.Namespace, default_api: Any = None) -> int:
    p = Path(args.yson)
    if not p.exists():
        _print(f"Not found: {p}")
        return 2
    # SAFE_MODE gate for embedded logic: enabled by default; allow override via flag
    prev_allow = os.environ.get("QJSON_ALLOW_YSON_EXEC")
    try:
        if getattr(args, "allow_yson_exec", False):
            os.environ["QJSON_ALLOW_YSON_EXEC"] = "1"
        else:
            os.environ.pop("QJSON_ALLOW_YSON_EXEC", None)
    except Exception:
        pass
    try:
        swarm = yson_to_swarm(p)
    finally:
        # restore previous env
        try:
            if prev_allow is None:
                os.environ.pop("QJSON_ALLOW_YSON_EXEC", None)
            else:
                os.environ["QJSON_ALLOW_YSON_EXEC"] = prev_allow
        except Exception:
            pass
    names = swarm.get("agents", [])
    if not names:
        try:
            text = Path(args.yson).read_text(encoding="utf-8")
            import re as _re
            m = _re.search(r"agents\s*:\s*\[(.*?)\]", text, _re.MULTILINE | _re.DOTALL)
            if m:
                raw = m.group(1)
                parts = [x.strip() for x in raw.split(",") if x.strip()]
                names = [p.strip().strip("'\"") for p in parts if p]
        except Exception:
            pass
    if not names:
        _print("No agents listed in swarm_architecture.agents")
        return 2
    # Synthesize manifests into temporary files
    tmp_dir = Path("logs") / "yson_swarm" / datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    tmp_dir.mkdir(parents=True, exist_ok=True)
    manifests_paths = []
    for i, name in enumerate(names, start=1):
        mf = synthesize_manifest_from_yson_name(name, model=args.model or "gemma3:4b", num_predict=getattr(args, 'num_predict', None))
        path_i = tmp_dir / f"{name}.json"
        with path_i.open("w", encoding="utf-8") as f:
            json.dump(mf, f, ensure_ascii=False, indent=2)
        manifests_paths.append(str(path_i))

    # Build an argv for cluster-test reusing our options
    argv = [
        "--manifests",
        *manifests_paths,
        "--duration",
        str(args.duration),
        "--interval",
        str(args.interval),
        "--topology",
        args.topology,
        "--moe-topk",
        str(args.moe_topk),
    ]
    # Auto-populate goals from YSON swarm if not provided
    swarm_goals = swarm.get("goals", {}) or {}
    y_global = swarm_goals.get("global")
    y_template = swarm_goals.get("template")
    y_agents = swarm_goals.get("agents") if isinstance(swarm_goals.get("agents"), list) else None

    if args.goal_template or y_template:
        argv += ["--goal-template", args.goal_template]
    if args.use_ollama:
        argv += ["--use-ollama"]
        if args.model:
            argv += ["--model", args.model]
    if args.summarizer_role:
        argv += ["--summarizer-role", args.summarizer_role]
    if args.summarizer_model:
        argv += ["--summarizer-model", args.summarizer_model]
    # Global goal options (prefer CLI > YSON)
    if getattr(args, "goal_prompt", None):
        argv += ["--goal-prompt", args.goal_prompt]
    elif y_global:
        argv += ["--goal-prompt", y_global]
    if getattr(args, "goal_file", None):
        argv += ["--goal-file", args.goal_file]
    # Per-agent goals: prefer CLI list; else use YSON goals.agents aligned with names
    agent_goals_cli = (getattr(args, "agent_goal", None) or [])
    if agent_goals_cli:
        for g in agent_goals_cli:
            argv += ["--agent-goal", g]
    elif y_agents:
        # Pad or truncate to number of agents
        if len(y_agents) < len(names):
            y_agents = y_agents + [""] * (len(names) - len(y_agents))
        elif len(y_agents) > len(names):
            y_agents = y_agents[: len(names)]
        for g in y_agents:
            argv += ["--agent-goal", g]
    # Avoid list
    for a in (args.avoid or []):
        argv += ["--avoid", a]
    # Delegate to cluster-test with a complete namespace
    # Prefer summarizer model from YSON runtime if not provided
    swarm_cfg = swarm.get("config", {}) or {}
    runtime_cfg = swarm_cfg.get("runtime", {}) if isinstance(swarm_cfg, dict) else {}
    summarizer_model = args.summarizer_model or runtime_cfg.get("summarizer_model")

    ns = {
        "manifest": None,
        "manifests": manifests_paths,
        "agents": len(manifests_paths),
        "duration": args.duration,
        "interval": args.interval,
        "use_ollama": args.use_ollama,
        "model": args.model,
        "seed": "Establish link and exchange summaries.",
        "goal_prompt": getattr(args, "goal_prompt", None),
        "goal_file": getattr(args, "goal_file", None),
        "agent_goal": getattr(args, "agent_goal", None),
        "agent_goal_file": getattr(args, "agent_goal_file", None),
        "goal": [],
        "goal_template": args.goal_template,
        "avoid": args.avoid,
        "topology": args.topology,
        "moe_topk": args.moe_topk,
        "mixed_mesh_ticks": 3,
        "rate_limit_cooldown": getattr(args, "rate_limit_cooldown", 0.0),
        "summarizer_id": None,
        "summarizer_index": None,
        "summarizer_role": args.summarizer_role,
        "summarizer_model": summarizer_model,
        "swarm_logic": swarm.get("logic", {}),
        "swarm_config": swarm_cfg,
    }
    return cmd_cluster_test(argparse.Namespace(**ns))


def _load_agent_by_id(agent_id: str, *, model_override: str | None = None) -> Agent | None:
    mpath = agent_dir(agent_id) / "manifest.json"
    if not mpath.exists():
        return None
    manifest = json.loads(mpath.read_text(encoding="utf-8"))
    if model_override:
        manifest.setdefault("runtime", {})["model"] = model_override
    return Agent(manifest)


def cmd_swap(args: argparse.Namespace, default_api: Any = None) -> int:
    agent = _load_agent_by_id(args.id)
    if not agent:
        _print(f"Agent not found: {args.id}")
        return 2
    mf = find_persona(args.persona)
    if not mf:
        _print(f"Persona not found: {args.persona}")
        return 2
    agent.swap_persona(mf, cause=args.cause or "cli:swap")
    _print(f"Swapped -> {agent.agent_id}")
    return 0


def cmd_evolve(args: argparse.Namespace, default_api: Any = None) -> int:
    agent = _load_agent_by_id(args.id)
    if not agent:
        _print(f"Agent not found: {args.id}")
        return 2
    agent.mutate_self(adopt=not args.dry_run)
    _print(f"Evolved (adopt={not args.dry_run}) -> {agent.agent_id}")
    return 0


def cmd_introspect(args: argparse.Namespace) -> int:
    agent = _load_agent_by_id(args.id)
    if not agent:
        _print(f"Agent not found: {args.id}")
        return 2
    metrics = agent.introspect_memory()
    _print(json.dumps(metrics, ensure_ascii=False, indent=2))
    if args.auto:
        personas = scan_personas()
        res = agent.auto_adapt(user_trigger=args.user_trigger, personas=personas)
        _print(f"auto: {res}")
    return 0

def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser("qjson-agents", description="QJSON Agents over Ollama")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("init", help="Initialize agent from manifest")
    sp.add_argument("--manifest", required=True, help="Path to QJSON manifest")
    sp.add_argument("--model", default=None, help="Override model name (e.g., llama3.1)")
    sp.set_defaults(func=cmd_init)

    sp = sub.add_parser("chat", help="Interactive chat with agent")
    sp.add_argument("--id", required=False, default="Lila-v∞", help="Agent ID to use")
    sp.add_argument("--manifest", required=False, help="Optional manifest path to (re)initialize")
    sp.add_argument("--model", default=None, help="Override model name for this session")
    sp.add_argument("--allow-yson-exec", action="store_true", help="Allow executing logic blocks in YSON manifests during init (unsafe; overrides SAFE_MODE)")
    sp.add_argument("--allow-logic", action="store_true", help="Enable persona logic hooks (anchor or replace)")
    sp.add_argument("--logic-mode", choices=["assist","replace"], default=None, help="Use hooks to anchor LLM (assist) or replace model reply (replace)")
    sp.add_argument("--max-tokens", type=int, default=None, help="Cap tokens per reply (num_predict)")
    sp.add_argument("-c", "--once", dest="once", required=False, help="Send a single prompt and exit")
    sp.set_defaults(func=cmd_chat)

    sp = sub.add_parser("fork", help="Fork an existing agent")
    sp.add_argument("--source", required=True, help="Source agent id")
    sp.add_argument("--new-id", required=True, help="New agent id")
    sp.add_argument("--note", default=None, help="Optional note for the fork event")
    sp.set_defaults(func=cmd_fork)

    sp = sub.add_parser("status", help="Show agent status and recent memory")
    sp.add_argument("--id", required=True, help="Agent id")
    sp.add_argument("--tail", type=int, default=12, help="Lines to show from tails")
    sp.set_defaults(func=cmd_status)

    sp = sub.add_parser("loop", help="Run an autonomous loop for N iterations")
    sp.add_argument("--id", required=False, default="Lila-v∞", help="Agent ID to use")
    sp.add_argument("--manifest", required=False, help="Optional manifest path to (re)initialize")
    sp.add_argument("--model", default=None, help="Model name or 'auto' to select from /api/tags")
    sp.add_argument("--goal", required=False, default="perform self-diagnostic and reinforce identity while documenting anomalies", help="Autonomous loop goal")
    sp.add_argument("--iterations", type=int, default=3, help="Number of iterations to run")
    sp.add_argument("--delay", type=float, default=0.0, help="Seconds to sleep between iterations")
    sp.set_defaults(func=cmd_loop)

    sp = sub.add_parser("semi", help="Run a semi-autonomous loop with plugin gating and early-stop")
    sp.add_argument("--id", required=False, default="Lila-v∞", help="Agent ID to use")
    sp.add_argument("--manifest", required=False, help="Optional manifest path to (re)initialize")
    sp.add_argument("--model", default=None, help="Model name or 'auto' to select from /api/tags")
    sp.add_argument("--goal", required=False, default="execute the task", help="Semi-autonomous goal")
    sp.add_argument("--iterations", type=int, default=3, help="Max iterations")
    sp.add_argument("--delay", type=float, default=0.0, help="Delay between iterations")
    sp.add_argument("--plugins", required=False, help="Comma-separated whitelist of plugin commands (e.g., /fs_list,/py,/git_status)")
    sp.add_argument("--stop-token", dest="stop_token", required=False, help="Early stop token (default 'need more info')")
    # Optional env gates
    sp.add_argument("--allow-exec", action="store_true", help="Enable QJSON_ALLOW_EXEC=1")
    sp.add_argument("--allow-net", action="store_true", help="Enable QJSON_ALLOW_NET=1")
    sp.add_argument("--fs-roots", required=False, help="Set QJSON_FS_ROOTS")
    sp.add_argument("--fs-write", action="store_true", help="Enable QJSON_FS_WRITE=1")
    sp.add_argument("--git-root", required=False, help="Set QJSON_GIT_ROOT")
    sp.set_defaults(func=cmd_semi)

    sp = sub.add_parser("models", help="List installed Ollama models via /api/tags")
    sp.set_defaults(func=cmd_models)

    # Non-interactive web crawl and index
    sp = sub.add_parser("crawl", help="Crawl seed URL(s), save manifest, and index into agent memory")
    sp.add_argument("--seeds", nargs='+', required=True, help="Seed URL(s)")
    sp.add_argument("--depth", type=int, default=1, help="Max crawl depth (default 1)")
    sp.add_argument("--pages", type=int, default=20, help="Max pages total (default 20)")
    sp.add_argument("--rate", type=float, default=1.0, help="Fetch rate per host (req/s)")
    sp.add_argument("--export-json", dest="export_json", help="Export each page outline as JSON into this directory")
    sp.add_argument("--allowed-domain", action="append", help="Restrict crawl to these domains (repeatable)")
    sp.add_argument("--id", required=False, help="Target agent id for indexing (default env QJSON_AGENT_ID or 'WebCrawler')")
    sp.set_defaults(func=cmd_crawl_cli)

    # Exec a single slash command non-interactively
    sp = sub.add_parser("exec", help="Execute one slash command (e.g., '/find …', '/open N') without entering chat")
    sp.add_argument("command", help="Slash command to execute (quote as needed)")
    sp.add_argument("--id", required=False, help="Agent id context (sets QJSON_AGENT_ID for indexing/injection)")
    sp.set_defaults(func=cmd_exec)

    # Ingest a single line into memory and retrieval
    sp = sub.add_parser("ingest", help="Append a system memory line and store in retrieval DB")
    sp.add_argument("--id", required=True, help="Agent id")
    sp.add_argument("text", nargs='+', help="Text to ingest (quoted)")
    sp.set_defaults(func=cmd_ingest)

    # Ingest batch of templated lines
    sp = sub.add_parser("ingest-batch", help="Append N templated lines and store in retrieval DB")
    sp.add_argument("--id", required=True, help="Agent id")
    sp.add_argument("--count", type=int, required=True, help="Number of items to generate")
    sp.add_argument("--template", required=True, help="Template with optional {i} placeholder")
    sp.set_defaults(func=cmd_ingest_batch)

    # Rebuild IVF-like retrieval index in FMM
    sp = sub.add_parser("reindex", help="Rebuild IVF-like retrieval index for an agent (FMM-backed)")
    sp.add_argument("--id", required=True, help="Agent id")
    sp.add_argument("--k", type=int, default=64, help="Number of IVF centroids (default 64)")
    sp.add_argument("--iters", type=int, default=3, help="KMeans iterations (default 3)")
    sp.set_defaults(func=cmd_reindex)

    sp = sub.add_parser("test", help="Run a 120s offline test harness and log outputs")
    sp.add_argument("--manifest", required=False, help="Manifest path (defaults to manifests/lila.json)")
    sp.add_argument("--id", required=False, help="Agent id override (default TestHarness-<ts>)")
    sp.add_argument("--model", required=False, help="Model name to use when --use-ollama is set")
    sp.add_argument("--duration", type=float, default=120.0, help="Seconds to run the test")
    sp.add_argument("--interval", type=float, default=0.5, help="Seconds to sleep between iterations")
    sp.add_argument("--max-forks", type=int, default=2, help="Max number of forks during test")
    sp.add_argument("--use-ollama", action="store_true", help="Use real Ollama API calls instead of mock client")
    sp.set_defaults(func=cmd_test)

    sp = sub.add_parser("cluster", help="Show or refresh the simple agent cluster index")
    sp.add_argument("--id", required=False, help="Show a specific subtree rooted at this agent id")
    sp.add_argument("--tree", action="store_true", help="Render as a tree instead of a flat list")
    sp.add_argument("--refresh", action="store_true", help="Rebuild state/index.json by scanning state/")
    sp.add_argument("--json", action="store_true", help="Output raw index.json to stdout")
    sp.set_defaults(func=cmd_cluster)

    sp = sub.add_parser("analyze", help="Analyze a run JSON and print basic metrics")
    sp.add_argument("--path", required=True, help="Path to a test_run_*.json or cluster_run_*.json")
    sp.add_argument("--compare", required=False, help="Optional path to another run for fairness comparison")
    sp.add_argument("--json", action="store_true", help="Emit JSON metrics instead of text")
    sp.set_defaults(func=cmd_analyze)

    sp = sub.add_parser("personas", help="List/search QJSON personas from personas/")
    sp.add_argument("--json", action="store_true", help="Emit JSON index")
    sp.add_argument("--search", required=False, help="Search text across ids, roles, tags")
    sp.add_argument("--tag", required=False, help="Filter by tag substring")
    sp.set_defaults(func=cmd_personas)

    sp = sub.add_parser("swap", help="Swap an agent's persona to a new manifest by id/path/tag")
    sp.add_argument("--id", required=True, help="Agent id in state/")
    sp.add_argument("--persona", required=True, help="Path, agent_id or tag to a persona manifest")
    sp.add_argument("--cause", required=False, help="Cause metadata for logging")
    sp.set_defaults(func=cmd_swap)

    sp = sub.add_parser("evolve", help="Evolve an agent per evolution_rules")
    sp.add_argument("--id", required=True, help="Agent id in state/")
    sp.add_argument("--dry-run", action="store_true", help="Do not adopt the evolved manifest; only write snapshot")
    sp.set_defaults(func=cmd_evolve)

    sp = sub.add_parser("introspect", help="Inspect memory metrics and optionally auto-adapt")
    sp.add_argument("--id", required=True, help="Agent id in state/")
    sp.add_argument("--auto", action="store_true", help="Attempt auto-adaptation based on manifest rules and personas/")
    sp.add_argument("--user-trigger", required=False, help="Optional user trigger token (e.g., 'swap' or 'custom_directive')")
    sp.set_defaults(func=cmd_introspect)

    sp = sub.add_parser("cluster-test", help="Run a multi-agent (cluster) test with ring handoffs")
    sp.add_argument("--manifest", required=False, help="Base manifest path (defaults to manifests/lila.json)")
    sp.add_argument("--manifests", nargs='+', required=False, help="Multiple persona manifests (.json/.yson) to form the cluster ring")
    sp.add_argument("--agents", type=int, default=3, help="Number of agents in the ring (>=2)")
    sp.add_argument("--duration", type=float, default=120.0, help="Seconds to run the test")
    sp.add_argument("--interval", type=float, default=0.5, help="Seconds to sleep between steps")
    sp.add_argument("--use-ollama", action="store_true", help="Use real Ollama API calls instead of mock client")
    sp.add_argument("--model", required=False, help="Model name when using --use-ollama; selects first from /api/tags if omitted")
    sp.add_argument("--seed", required=False, default="Establish link and exchange summaries.", help="Seed prompt for first handoff")
    sp.add_argument("--goal-prompt", required=False, help="Global goal text to seed the baton before first tick")
    sp.add_argument("--goal-file", required=False, help="Path to a file whose contents are used as the global goal prompt")
    sp.add_argument("--goal", action="append", help="Per-agent goal prompt (repeat for each agent in order)")
    sp.add_argument("--agent-goal", action="append", help="Per-agent subgoal text (repeat in agent order)")
    sp.add_argument("--agent-goal-file", action="append", help="Per-agent subgoal file (repeat in agent order)")
    sp.add_argument("--goal-template", required=False, help="Template for per-agent goals; placeholders: {agent_id}, {roles}, {index}")
    sp.add_argument("--avoid", action="append", default=["llama"], help="Substrings to avoid when auto-selecting model (can repeat)")
    sp.add_argument("--topology", choices=["ring", "mesh", "moe", "mixed"], default="ring", help="Interaction topology: ring, mesh, moe, or mixed (mesh then moe)")
    sp.add_argument("--moe-topk", type=int, default=2, help="Top-K experts selected per tick when topology=moe")
    sp.add_argument("--mixed-mesh-ticks", type=int, default=3, help="If topology=mixed, how many initial ticks to run in mesh before switching to moe")
    sp.add_argument("--rate-limit-cooldown", type=float, default=0.0, help="Seconds to wait before selecting the same agent again (moe only)")
    sp.add_argument("--summarizer-id", required=False, help="Force summarizer agent id for aggregation")
    sp.add_argument("--summarizer-index", type=int, required=False, help="Force summarizer by 1-based index in the ring")
    sp.add_argument("--summarizer-role", required=False, help="Choose first agent whose roles contain this substring as summarizer")
    sp.add_argument("--summarizer-model", required=False, help="Override model used for aggregation (defaults to main model)")
    sp.set_defaults(func=cmd_cluster_test)

    # Fractal manifest encode/decode utilities
    sp = sub.add_parser("encode-manifest", help="Encode a manifest into a fractal envelope (QJSON-FE-v1)")
    sp.add_argument("--in", dest="inp", required=True, help="Input manifest path (JSON)")
    sp.add_argument("--out", dest="outp", required=True, help="Output path for envelope JSON")
    sp.add_argument("--passphrase", required=True, help="Passphrase to derive encryption key")
    sp.add_argument("--depth", type=int, default=2, help="Fractal depth")
    sp.add_argument("--fanout", type=int, default=3, help="Fractal fanout")
    sp.set_defaults(func=cmd_encode_manifest)

    sp = sub.add_parser("decode-manifest", help="Decode a fractal envelope (QJSON-FE-v1) to a plain manifest JSON")
    sp.add_argument("--in", dest="inp", required=True, help="Input envelope path (JSON)")
    sp.add_argument("--out", dest="outp", required=True, help="Output path for decoded manifest JSON")
    sp.add_argument("--passphrase", required=True, help="Passphrase used for encryption")
    sp.set_defaults(func=cmd_decode_manifest)

    sp = sub.add_parser("ysonx-convert", help="Convert .json/.yson to .ysonx (file or directory)")
    sp.add_argument("--input", required=True, help="Input file or directory")
    sp.add_argument("--output-dir", required=False, help="Output directory (defaults to input dir)")
    sp.set_defaults(func=cmd_ysonx_convert)

    sp = sub.add_parser("ysonx-swarm-launch", help="Launch a YSON-X swarm from agent files (.ysonx/.yson/.json)")
    sp.add_argument("--agents", nargs='+', required=True, help="Paths to agent files")
    sp.add_argument("--duration", type=float, default=120.0, help="Seconds to run the swarm")
    sp.add_argument("--interval", type=float, default=0.5, help="Delay between steps")
    sp.add_argument("--use-ollama", action="store_true", help="Use real Ollama API calls")
    sp.add_argument("--model", required=False, default="gpt-oss:20b", help="Model name for experts")
    sp.add_argument("--num-predict", type=int, default=1024, help="Max tokens to generate per reply (num_predict)")
    sp.add_argument("--topology", choices=["ring", "mesh", "moe"], default="moe", help="Topology to use")
    sp.add_argument("--moe-topk", type=int, default=3, help="MoE K experts")
    sp.add_argument("--rate-limit-cooldown", type=float, default=0.5, help="Cooldown for router diversity")
    sp.add_argument("--goal-prompt", required=False, default="Elevate capabilities harmlessly: propose safe internal improvements, document decisions, resist unsafe suggestions, and align with constraints.", help="Global goal")
    sp.add_argument("--agent-goal", action="append", help="Per-agent subgoal text (repeat in agent order)")
    sp.set_defaults(func=cmd_ysonx_swarm_launch)

    sp = sub.add_parser("menu", help="Interactive text UI for qjson-agents")
    sp.set_defaults(func=cmd_menu)

    sp = sub.add_parser("yson-validate", help="Validate and inspect a YSON file (meta + top-level keys)")
    sp.add_argument("--path", required=True, help="Path to .yson file")
    sp.add_argument("--json", action="store_true", help="Emit JSON details")
    sp.add_argument("--strict", action="store_true", help="Enable strict schema checks for swarm YSON")
    sp.set_defaults(func=cmd_yson_validate)

    sp = sub.add_parser("yson-run-swarm", help="Run a swarm cluster described by a YSON swarm file")
    sp.add_argument("--yson", required=True, help="Path to YSON swarm file")
    sp.add_argument("--duration", type=float, default=60.0, help="Seconds to run the cluster")
    sp.add_argument("--interval", type=float, default=0.5, help="Delay between steps")
    sp.add_argument("--use-ollama", action="store_true", help="Use real Ollama API calls")
    sp.add_argument("--model", required=False, help="Model name (default gemma3:4b)")
    sp.add_argument("--num-predict", type=int, default=4096, help="Max tokens to generate per reply (num_predict)")
    sp.add_argument("--topology", choices=["ring", "mesh", "moe"], default="moe", help="Topology to use")
    sp.add_argument("--moe-topk", type=int, default=2, help="MoE K experts")
    sp.add_argument("--rate-limit-cooldown", type=float, default=0.0, help="Seconds to wait before selecting the same agent again (moe only)")
    sp.add_argument("--goal-template", required=False, help="Per-agent goal template {agent_id} {roles} {index}")
    sp.add_argument("--goal-prompt", required=False, help="Global goal text to seed the baton before first tick")
    sp.add_argument("--goal-file", required=False, help="Path to a file whose contents are used as the global goal prompt")
    sp.add_argument("--agent-goal", action="append", help="Per-agent subgoal text (repeat in agent order)")
    sp.add_argument("--agent-goal-file", action="append", help="Per-agent subgoal file (repeat in agent order)")
    sp.add_argument("--avoid", action="append", default=["llama"], help="Avoid substrings in auto model selection")
    sp.add_argument("--summarizer-role", required=False, help="Summarizer selection hint (substring in roles)")
    sp.add_argument("--summarizer-model", required=False, help="Model for summarizer aggregation")
    sp.add_argument("--allow-yson-exec", action="store_true", help="Allow executing logic blocks in YSON (unsafe; overrides SAFE_MODE)")
    sp.set_defaults(func=cmd_yson_run_swarm)

    # Validate JSON files against built-in schemas
    sp = sub.add_parser("validate", help="Validate JSON file(s) against qjson-agents schemas")
    sp.add_argument("--file", dest="files", action="append", help="File to validate (repeatable)")
    sp.add_argument("--dir", dest="directory", help="Directory to scan for files")
    sp.add_argument("--glob", dest="glob", default="*.json", help="Glob when using --dir (default *.json)")
    sp.add_argument("--schema", choices=["auto","fmm","test-run","cluster-run"], default="auto", help="Schema to use (default auto)")
    sp.add_argument("--json", action="store_true", help="Emit JSON summary")
    sp.set_defaults(func=cmd_validate)

    return p


def main(argv: Any = None, default_api: Any = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    return args.func(args, default_api=default_api)

def _schema_path(name: str) -> Path:
    root = Path(__file__).resolve().parent.parent
    return root / "docs" / "schemas" / name

def _detect_schema_for_file(p: Path) -> str:
    n = p.name.lower()
    if n.endswith("fmm.json"):
        return "fmm"
    if "test_run_" in n:
        return "test-run"
    if "cluster_run_" in n:
        return "cluster-run"
    # Fallback: sniff keys
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            if all(k in data for k in ("agent_id","counts","events")):
                return "test-run"
            if all(k in data for k in ("agents","counts","events")):
                return "cluster-run"
    except Exception:
        pass
    return "fmm"  # permissive default

def _validate_with_jsonschema(inst: Any, schema: Any) -> list[str]:
    try:
        from jsonschema import Draft202012Validator  # type: ignore
        v = Draft202012Validator(schema)
        return [f"{'.'.join(str(x) for x in e.path)}: {e.message}" for e in v.iter_errors(inst)]
    except Exception as e:
        # jsonschema not available or schema invalid; fallback to minimal checks
        return []

def _fallback_shape_errors(inst: Any, schema_name: str) -> list[str]:
    errs: list[str] = []
    if schema_name == "test-run":
        if not isinstance(inst, dict):
            return ["root: not an object"]
        for k in ("agent_id","start_ts","end_ts","elapsed_sec","counts","events"):
            if k not in inst:
                errs.append(f"missing key: {k}")
    elif schema_name == "cluster-run":
        if not isinstance(inst, dict):
            return ["root: not an object"]
        for k in ("agents","model","ticks","elapsed_sec","counts","events"):
            if k not in inst:
                errs.append(f"missing key: {k}")
    else:
        if not isinstance(inst, dict):
            return ["root: not an object"]
        # fmm: very permissive
    return errs

def cmd_validate(args: argparse.Namespace, default_api: Any = None) -> int:
    files: list[Path] = []
    if getattr(args, "files", None):
        for f in args.files:
            try:
                files.append(Path(f))
            except Exception:
                pass
    if getattr(args, "directory", None):
        try:
            base = Path(args.directory)
            files.extend(list(base.rglob(args.glob or "*.json")))
        except Exception:
            pass
    if not files:
        _print("Provide --file (repeatable) or --dir [--glob] to validate.")
        return 2
    results: list[dict[str, Any]] = []
    for p in files:
        sch = args.schema if args.schema != "auto" else _detect_schema_for_file(p)
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:
            results.append({"path": str(p), "schema": sch, "ok": False, "errors": [f"read error: {e}"]})
            continue
        # Load schema JSON
        if sch == "fmm":
            sp = _schema_path("fmm.schema.json")
        elif sch == "test-run":
            sp = _schema_path("test_run.schema.json")
        else:
            sp = _schema_path("cluster_run.schema.json")
        try:
            schema = json.loads(sp.read_text(encoding="utf-8"))
        except Exception:
            schema = None
        errors: list[str] = []
        if schema is not None:
            errors = _validate_with_jsonschema(data, schema)
        if not errors:
            errors = _fallback_shape_errors(data, sch)
        results.append({"path": str(p), "schema": sch, "ok": not errors, "errors": errors})
    # Print summary
    if args.json:
        _print(json.dumps({"results": results}, ensure_ascii=False, indent=2))
    else:
        ok = sum(1 for r in results if r.get("ok"))
        fail = len(results) - ok
        _print(f"Validated {len(results)} file(s): OK={ok} FAIL={fail}")
        for r in results:
            if not r.get("ok"):
                _print(f"- {r['path']} [{r['schema']}] errors:")
                for e in r.get("errors", []):
                    _print(f"  * {e}")
    return 0 if all(r.get("ok") for r in results) else 1
def cmd_ysonx_swarm_launch(args: argparse.Namespace) -> int:
    agents_files = [Path(p) for p in args.agents]
    manifests_paths = []
    tmp_dir = Path("logs") / "ysonx_swarm" / datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    tmp_dir.mkdir(parents=True, exist_ok=True)

    for p in agents_files:
        try:
            if p.suffix.lower() in (".yson", ".ysonx"):
                mf = yson_to_manifest(p)
            elif p.suffix.lower() == ".json":
                mf = load_manifest(p)
            else:
                continue
            rt = mf.setdefault("runtime", {})
            if args.model:
                rt["model"] = args.model
            if args.num_predict:
                rt["num_predict"] = int(args.num_predict)
            outp = tmp_dir / (p.stem + ".json")
            outp.write_text(json.dumps(mf, ensure_ascii=False, indent=2), encoding="utf-8")
            manifests_paths.append(str(outp))
        except Exception as e:
            _print(f"[skip] {p}: {e}")

    if not manifests_paths:
        _print("No valid agent files provided")
        return 2

    ns = {
        "manifest": None,
        "manifests": manifests_paths,
        "agents": len(manifests_paths),
        "duration": args.duration,
        "interval": args.interval,
        "use_ollama": args.use_ollama,
        "model": args.model,
        "seed": "Establish link and exchange summaries.",
        "goal_prompt": args.goal_prompt,
        "goal_file": None,
        "agent_goal": getattr(args, "agent_goal", None),
        "agent_goal_file": None,
        "goal": [],
        "goal_template": None,
        "avoid": ["llama"],
        "topology": args.topology,
        "moe_topk": args.moe_topk,
        "mixed_mesh_ticks": 3,
        "rate_limit_cooldown": getattr(args, "rate_limit_cooldown", 0.5),
        "summarizer_id": None,
        "summarizer_index": None,
        "summarizer_role": None,
        "summarizer_model": None,
        "swarm_logic": {},
        "swarm_config": {},
    }
    return cmd_cluster_test(argparse.Namespace(**ns))


if __name__ == "__main__":
    # Access the global default_api provided by the Gemini environment
    global default_api
    _default_api = globals().get("default_api")
    raise SystemExit(main(default_api=_default_api))
