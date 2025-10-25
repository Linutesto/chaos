from __future__ import annotations

from typing import Dict
from .common_utils import build_reply, on_start_stub, memory_context_snippet


def on_start(state: Dict, persona: Dict) -> str:
    state["status"] = "ready"
    return on_start_stub()


def on_message(state: Dict, user_text: str, persona: Dict) -> str:
    """state is a mutable dict persisted by your Agent; persona is the decoded manifest"""
    base = build_reply(user_text, persona)
    ctx = memory_context_snippet(state)
    if ctx:
        return f"Context:\n{ctx}\n\n" + base
    return base
