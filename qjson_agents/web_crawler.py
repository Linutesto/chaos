from __future__ import annotations

import hashlib
import time
import urllib.parse as urlparse
from urllib import request as _urlreq, error as _urlerr, robotparser
from collections import deque
from typing import Any, Deque, Dict, Iterable, List, Optional, Set, Tuple

from .web_outliner import build_outline


class Crawler:
    def __init__(self, *, rate_per_host: float = 1.0, user_agent: str = "qjson-agents/0.1") -> None:
        self.rate_per_host = max(0.05, float(rate_per_host))
        self.user_agent = user_agent
        self._last_fetch: Dict[str, float] = {}
        self._robots: Dict[str, robotparser.RobotFileParser] = {}

    def _robots_ok(self, url: str) -> bool:
        try:
            p = urlparse.urlparse(url)
            base = f"{p.scheme}://{p.netloc}"
            rp = self._robots.get(base)
            if rp is None:
                rp = robotparser.RobotFileParser()
                rp.set_url(urlparse.urljoin(base, "/robots.txt"))
                try:
                    rp.read()
                except Exception:
                    pass
                self._robots[base] = rp
            return rp.can_fetch(self.user_agent, url) if hasattr(rp, "can_fetch") else True
        except Exception:
            return True

    def _rate_limit(self, host: str) -> None:
        now = time.time()
        last = self._last_fetch.get(host, 0.0)
        interval = 1.0 / self.rate_per_host
        wait = last + interval - now
        if wait > 0:
            time.sleep(min(wait, 2.0))
        self._last_fetch[host] = time.time()

    def _fetch(self, url: str, timeout: float = 6.0, max_bytes: int = 512 * 1024) -> str:
        p = urlparse.urlparse(url)
        self._rate_limit(p.netloc)
        req = _urlreq.Request(url, headers={"User-Agent": self.user_agent})
        with _urlreq.urlopen(req, timeout=timeout) as resp:
            data = resp.read(max_bytes)
            return data.decode("utf-8", errors="ignore")

    def _normalize(self, base: str, href: str) -> Optional[str]:
        try:
            u = urlparse.urljoin(base, href)
            pu = urlparse.urlparse(u)
            if pu.scheme not in ("http","https"):
                return None
            # Normalize path (strip fragments)
            clean = pu._replace(fragment="")
            return urlparse.urlunparse(clean)
        except Exception:
            return None

    def _extract_links(self, html_text: str, base_url: str) -> List[str]:
        out: List[str] = []
        # simple href regex
        import re
        for m in re.finditer(r"href\s*=\s*\"([^\"]+)\"|href\s*=\s*'([^']+)'", html_text, re.IGNORECASE):
            href = m.group(1) or m.group(2) or ""
            n = self._normalize(base_url, href)
            if n:
                out.append(n)
        return out

    def crawl(self, seeds: List[str], *, max_depth: int = 1, max_pages: int = 20, allowed_domains: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        frontier: Deque[Tuple[str, int]] = deque()
        seen_urls: Set[str] = set()
        seen_hashes: Set[str] = set()
        out: List[Dict[str, Any]] = []

        def in_scope(u: str) -> bool:
            if not allowed_domains:
                return True
            try:
                host = urlparse.urlparse(u).netloc
                return any(host.endswith(d) for d in allowed_domains)
            except Exception:
                return False

        for s in seeds:
            if in_scope(s):
                frontier.append((s, 0))

        while frontier and len(out) < max_pages:
            url, d = frontier.popleft()
            if d > max_depth or url in seen_urls:
                continue
            if not self._robots_ok(url):
                continue
            try:
                html = self._fetch(url)
            except Exception:
                continue
            seen_urls.add(url)
            outline = build_outline(html, url)
            body = "\n".join((s.get("text") or "") for s in outline.get("sections", []))
            h = hashlib.sha1(body.encode("utf-8", errors="ignore")).hexdigest()
            if h in seen_hashes:
                continue
            seen_hashes.add(h)
            out.append(outline)
            # Enqueue links
            for l in self._extract_links(html, url):
                if in_scope(l) and l not in seen_urls:
                    frontier.append((l, d + 1))
        return out

