from __future__ import annotations

import re
import html
from html.parser import HTMLParser
from typing import Any, Dict, List, Optional, Tuple


DATE_RXES = [
    re.compile(r"\b(20\d{2}|19\d{2})[-/.](0?[1-9]|1[0-2])[-/.](0?[1-9]|[12]\d|3[01])\b"),
    re.compile(r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec|January|February|March|April|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}\b", re.IGNORECASE),
]


class _Node:
    def __init__(self, tag: str, attrs: Dict[str, str]):
        self.tag = tag
        self.attrs = attrs
        self.children: List[_Node] = []
        self.text_parts: List[str] = []

    def append_text(self, t: str) -> None:
        if t:
            self.text_parts.append(t)

    def text(self) -> str:
        return html.unescape("".join(self.text_parts)).strip()


class _Parser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = _Node("document", {})
        self.stack: List[_Node] = [self.root]

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        a = {k: (v or "") for k, v in attrs}
        node = _Node(tag.lower(), a)
        self.stack[-1].children.append(node)
        self.stack.append(node)

    def handle_endtag(self, tag: str) -> None:
        t = tag.lower()
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == t:
                del self.stack[i:]
                break

    def handle_data(self, data: str) -> None:
        self.stack[-1].append_text(data)


def _attr(node: _Node, key: str) -> str:
    return (node.attrs.get(key) or "").strip()


def _has_stopword(node: _Node) -> bool:
    val = (node.attrs.get("class") or "") + " " + (node.attrs.get("id") or "")
    val = val.lower()
    for w in ("nav", "menu", "footer", "sidebar", "cookie", "subscribe"):
        if w in val:
            return True
    return False


def _walk(node: _Node):
    yield node
    for c in node.children:
        yield from _walk(c)


def _find_meta(root: _Node) -> Dict[str, str]:
    meta: Dict[str, str] = {}
    for n in _walk(root):
        if n.tag == "meta":
            name = (_attr(n, "name") or _attr(n, "property")).lower()
            content = _attr(n, "content")
            if name in ("og:title", "twitter:title") and content:
                meta["og:title"] = content
            if name in ("description", "og:description", "twitter:description") and content:
                meta["description"] = content
        if n.tag == "title" and n.text():
            meta.setdefault("title", n.text())
    return meta


def _extract_times(root: _Node) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    # Prefer explicit <time datetime=...>
    for n in _walk(root):
        if n.tag == "time":
            dt = _attr(n, "datetime") or n.text()
            if dt:
                # try classify via nearby label in class or text
                label = (n.text() or "") + " " + ((_attr(n, "class") or "") + " " + (_attr(n, "id") or ""))
                l = label.lower()
                t = "updated" if ("update" in l or "modified" in l) else "published"
                out.append({"type": t, "value": dt, "source": "time"})
    # Regex fallback
    body_text = " ".join(n.text() for n in _walk(root) if n.tag in ("p", "div", "span"))
    for rx in DATE_RXES:
        for m in rx.finditer(body_text):
            out.append({"type": "published", "value": m.group(0), "source": "regex"})
    # Deduplicate by (type,value)
    seen = set()
    uniq: List[Dict[str, str]] = []
    for d in out:
        k = (d.get("type"), d.get("value"))
        if k not in seen:
            uniq.append(d)
            seen.add(k)
    return uniq[:6]


def build_outline(html_text: str, url: str) -> Dict[str, Any]:
    """Parse HTML into a DocOutline structure with sections and dates.

    Best-effort, zero-deps implementation using html.parser.
    """
    p = _Parser()
    try:
        p.feed(html_text)
    except Exception:
        # Continue with partial parse
        pass
    root = p.root
    meta = _find_meta(root)

    # Title + subtitle detection
    doc_title = ""
    # Prefer <h1>
    h1s = [n for n in _walk(root) if n.tag == "h1" and n.text()]
    if h1s:
        doc_title = max((n.text() for n in h1s), key=len)
    if not doc_title:
        doc_title = meta.get("og:title") or meta.get("title") or ""
    subtitle = None
    if h1s:
        # First h2 after first h1
        first_h1 = h1s[0]
        take_next_h2 = False
        for n in _walk(root):
            if n is first_h1:
                take_next_h2 = True
            elif take_next_h2 and n.tag == "h2" and n.text():
                subtitle = n.text()
                break
    if not subtitle:
        subtitle = meta.get("description")

    # Build sections: walk headers and capture following text until next header of same or higher level
    headers = [(n, int(n.tag[1])) for n in _walk(root) if n.tag in {"h1","h2","h3","h4","h5","h6"} and n.text() and not _has_stopword(n)]
    sections: List[Dict[str, Any]] = []
    # Map nodes to order index for simple range tracking
    node_list = list(_walk(root))
    node_index = {id(n): i for i, n in enumerate(node_list)}
    for i, (hn, level) in enumerate(headers):
        start_i = node_index.get(id(hn), 0)
        end_i = len(node_list) - 1
        for hn2, level2 in headers[i+1:]:
            idx2 = node_index.get(id(hn2), start_i)
            if level2 <= level and idx2 > start_i:
                end_i = idx2 - 1
                break
        # Collect text blocks between start_i..end_i, excluding stopwords and headers themselves
        chunks: List[str] = []
        for j in range(start_i + 1, min(end_i + 1, start_i + 600)):
            n = node_list[j]
            if n.tag in ("script","style","nav") or _has_stopword(n):
                continue
            if n.tag in ("p","li","pre","code","blockquote","td") and n.text():
                chunks.append(n.text())
        text = "\n".join(chunks).strip()
        sections.append({
            "level": level,
            "title": hn.text(),
            "text": text,
            "anchors": [ _attr(hn, "id") ] if _attr(hn, "id") else [],
            "figures": [],
            "start_idx": start_i,
            "end_idx": end_i,
        })

    dates = _extract_times(root)
    # Language detection placeholder (default 'en')
    lang = "en"

    return {
        "url": url,
        "title": doc_title or (meta.get("title") or ""),
        "subtitle": subtitle,
        "sections": sections,
        "dates": dates,
        "lang": lang,
    }

