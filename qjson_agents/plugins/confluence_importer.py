from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, List
import os
import json

from qjson_agents.plugin_manager import Plugin


def _make_outline_from_text(text: str, url: str, title: str) -> Dict[str, Any]:
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


class ConfluenceImporter(Plugin):
    """Import Confluence HTML/MD/TXT exports into the active agent's index.

    Usage: /confluence_import <PATH>
    - PATH may be a file or directory. HTML/HTM files are outlined; MD/TXT ingested as text.
    - Outlines are upserted via the web indexer; text falls back to system memory + retrieval add.
    """

    def get_commands(self) -> Dict[str, Callable[..., Any]]:
        return {"/confluence_import": self.import_path}

    def import_path(self, *parts: str) -> str:
        if not parts:
            return "Usage: /confluence_import <PATH>"
        p = Path(parts[0]).expanduser().resolve()
        if not p.exists():
            return f"Path not found: {p}"
        agent_id = os.environ.get("QJSON_AGENT_ID") or "Confluence"
        count = 0
        skipped = 0
        from qjson_agents.web_indexer import upsert_outline
        try:
            from qjson_agents.web_outliner import build_outline
        except Exception:
            build_outline = None  # type: ignore

        def handle_file(fp: Path) -> None:
            nonlocal count, skipped
            ext = fp.suffix.lower()
            try:
                if ext in (".html", ".htm") and build_outline is not None:
                    text = fp.read_text(encoding="utf-8", errors="ignore")
                    outline = build_outline(text, str(fp))
                    upsert_outline(agent_id, outline)
                    count += 1
                elif ext in (".md", ".txt"):
                    raw = fp.read_text(encoding="utf-8", errors="ignore")
                    outline = _make_outline_from_text(raw, str(fp), fp.stem)
                    upsert_outline(agent_id, outline)
                    count += 1
                else:
                    skipped += 1
            except Exception:
                skipped += 1

        if p.is_dir():
            for fp in p.rglob("*"):
                if fp.is_file():
                    handle_file(fp)
        else:
            handle_file(p)
        return f"[confluence_import] imported={count} skipped={skipped} -> {agent_id}"

