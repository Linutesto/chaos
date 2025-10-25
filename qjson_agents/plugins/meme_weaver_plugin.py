from __future__ import annotations

import json
import os
from typing import Any, Callable, Dict, List

from qjson_agents.plugin_manager import Plugin


FORMATS = ["tweet", "thread", "meme-text", "tagline", "script", "copypasta"]
ANGLES = ["humor", "insight", "contrarian", "wholesome", "edgy", "educational"]


class MemeWeaverPlugin(Plugin):
    """Analyze a topic and generate meme-ready snippets (offline-safe).

    Usage:
      /meme analyze <TOPIC>
      /meme generate text <TOPIC> [style=humor|insight|...] [format=tweet|meme-text|...]
    """

    def get_commands(self) -> Dict[str, Callable[..., Any]]:
        return {"/meme": self.meme}

    def meme(self, *parts: str) -> str:
        if not parts:
            return "Usage: /meme analyze <TOPIC> | /meme generate text <TOPIC> [style=...] [format=...]"
        sub = parts[0].lower()
        if sub == "analyze" and len(parts) >= 2:
            topic = " ".join(parts[1:]).strip()
            # Offline heuristics: propose angles + formats
            ang = ANGLES[:3]
            fmts = FORMATS[:3]
            suggestions = {
                "topic": topic,
                "angles": ang,
                "formats": fmts,
                "cta": "Use /meme generate text <TOPIC> style=<angle> format=<fmt>",
            }
            return json.dumps(suggestions, ensure_ascii=False, indent=2)
        if sub == "generate" and len(parts) >= 3:
            kind = parts[1].lower()
            if kind != "text":
                return "[meme] only 'text' generation supported for now"
            raw = parts[2:]
            # Parse options
            style = None
            fmt = None
            keep: List[str] = []
            for p in raw:
                if p.startswith("style="):
                    style = p.split("=",1)[1]
                elif p.startswith("format="):
                    fmt = p.split("=",1)[1]
                else:
                    keep.append(p)
            topic = " ".join(keep).strip()
            style = style or ANGLES[0]
            fmt = fmt or "tweet"
            # Template-based generation
            text = self._template_text(topic, style, fmt)
            # Store as a memory line for the active agent
            try:
                from qjson_agents.retrieval import add_memory
                aid = os.environ.get("QJSON_AGENT_ID") or "MemeWeaver"
                add_memory(aid, text, {"source": "meme-weaver", "style": style, "format": fmt, "topic": topic})
            except Exception:
                pass
            return text
        return "[meme] unknown subcommand"

    def _template_text(self, topic: str, style: str, fmt: str) -> str:
        t = topic or "this"
        if fmt == "tweet":
            return f"{t}: {style} take — {self._style_line(style)} #AI #memes"
        if fmt == "thread":
            return f"Thread: {t}\n1) {self._style_line(style)}\n2) What it means: ...\n3) Try this: ..."
        if fmt == "meme-text":
            return f"Top: When {t} hits\nBottom: {self._style_line(style)}"
        if fmt == "tagline":
            return f"{t}: {self._style_line(style)}"
        if fmt == "script":
            return f"[{style} narrator] Once upon a {t}, we realized {self._style_line(style)}."
        if fmt == "copypasta":
            return f"Listen up about {t}. {self._style_line(style)} That's it. That's the post."
        return f"{t}: {self._style_line(style)}"

    def _style_line(self, style: str) -> str:
        m = {
            "humor": "lol but seriously",
            "insight": "the overlooked detail matters",
            "contrarian": "everyone misses the opposite",
            "wholesome": "be kind; build together",
            "edgy": "we ship the uncomfortable truth",
            "educational": "here's the 101 in 10s",
        }
        return m.get(style, "make it memorable")

