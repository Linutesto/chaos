from __future__ import annotations

import hashlib
import time
import uuid
from typing import Any, Dict, List

from .fmm_store import PersistentFractalMemory
from .retrieval import add_memory


def _ts() -> float:
    return time.time()


def _chunks(text: str, *, size: int = 1000, overlap: int = 150) -> List[str]:
    out: List[str] = []
    if not text:
        return out
    i = 0
    n = len(text)
    while i < n:
        out.append(text[i : i + size])
        i += max(1, size - overlap)
    return out


def upsert_outline(agent_id: str, outline: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Insert outline into fractal memory and retrieval index.

    Returns list of DocChunk metadata dicts.
    """
    url = outline.get("url") or ""
    title = outline.get("title") or ""
    lang = outline.get("lang") or "en"
    dates = outline.get("dates") or []
    published = next((d.get("value") for d in dates if d.get("type") == "published"), None)
    updated = next((d.get("value") for d in dates if d.get("type") == "updated"), None)
    doc_id = str(uuid.uuid5(uuid.NAMESPACE_URL, url)) if url else str(uuid.uuid4())
    crawl_at = _ts()

    fmm = PersistentFractalMemory(agent_id)
    # fmm path: web/{host}/{year}/...
    try:
        from urllib.parse import urlparse
        host = urlparse(url).netloc or "local"
    except Exception:
        host = "local"
    ym = time.strftime("%Y", time.gmtime(crawl_at))

    chunks_meta: List[Dict[str, Any]] = []
    section_idx = 0
    for sec in outline.get("sections", []):
        level = int(sec.get("level") or 0)
        stitle = str(sec.get("title") or "")
        text = str(sec.get("text") or "")
        section_idx += 1
        for i, ch in enumerate(_chunks(text, size=1000, overlap=150)):
            chunk_id = i
            meta = {
                "doc_id": doc_id,
                "chunk_id": chunk_id,
                "url": url,
                "title": title,
                "section": stitle,
                "level": level,
                "text": ch,
                "published_at": published,
                "updated_at": updated,
                "crawl_at": crawl_at,
                "lang": lang,
                "hash": hashlib.sha1(ch.encode("utf-8", errors="ignore")).hexdigest(),
            }
            # Insert into retrieval store
            add_memory(agent_id, ch, meta)
            # Insert into fractal memory path
            path = ["web", host, ym, title or stitle or "untitled", f"sec{section_idx}-h{level}"]
            try:
                fmm.insert(path, {"url": url, "title": title, "section": stitle, "level": level, "text": ch, "ts": crawl_at})
            except Exception:
                pass
            chunks_meta.append(meta)
    return chunks_meta

