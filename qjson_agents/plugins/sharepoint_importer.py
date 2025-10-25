from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict
import os

from qjson_agents.plugin_manager import Plugin


def _make_outline(title: str, url: str, text: str) -> Dict[str, Any]:
    return {
        "url": url,
        "title": title,
        "subtitle": None,
        "sections": [
            {"level": 2, "title": "Body", "text": text, "anchors": [], "figures": []}
        ],
        "dates": [],
        "lang": "en",
    }


class SharePointImporter(Plugin):
    """Import SharePoint exported pages (HTML/TXT/MD) into the agent's index.

    Usage: /sharepoint_import <PATH>
    - Treats HTML as outlineable pages; MD/TXT as plain text sections.
    - Ingests recursively from directories.
    """

    def get_commands(self) -> Dict[str, Callable[..., Any]]:
        return {"/sharepoint_import": self.import_path}

    def import_path(self, *parts: str) -> str:
        if not parts:
            return "Usage: /sharepoint_import <PATH>"
        p = Path(parts[0]).expanduser().resolve()
        if not p.exists():
            return f"Path not found: {p}"
        agent_id = os.environ.get("QJSON_AGENT_ID") or "SharePoint"
        from qjson_agents.web_indexer import upsert_outline
        try:
            from qjson_agents.web_outliner import build_outline
        except Exception:
            build_outline = None  # type: ignore
        count = 0
        skipped = 0

        def do_file(fp: Path) -> None:
            nonlocal count, skipped
            ext = fp.suffix.lower()
            try:
                if ext in (".html", ".htm") and build_outline is not None:
                    html = fp.read_text(encoding="utf-8", errors="ignore")
                    outline = build_outline(html, str(fp))
                    upsert_outline(agent_id, outline)
                    count += 1
                elif ext in (".md", ".txt"):
                    raw = fp.read_text(encoding="utf-8", errors="ignore")
                    upsert_outline(agent_id, _make_outline(fp.stem, str(fp), raw))
                    count += 1
                else:
                    skipped += 1
            except Exception:
                skipped += 1

        if p.is_dir():
            for fp in p.rglob("*"):
                if fp.is_file():
                    do_file(fp)
        else:
            do_file(p)

        return f"[sharepoint_import] imported={count} skipped={skipped} -> {agent_id}"

