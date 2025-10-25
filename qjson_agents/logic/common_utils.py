"""
Dependency-free helpers for persona runtime hooks.
"""

from __future__ import annotations

import re
from typing import List, Dict
from pathlib import Path
import json as _json
import os as _os

SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")
BULLET = re.compile(r"^\s*[-*•]\s+", re.M)


def normalize(text: str) -> str:
    return " ".join(text.strip().split())


def token_count(text: str) -> int:
    # crude but fast token proxy
    return len(re.findall(r"\w+|\S", text))


def smart_summarize(text: str, max_chars: int = 300) -> str:
    text = normalize(text)
    if len(text) <= max_chars:
        return text
    sents = SENT_SPLIT.split(text)
    out, total = [], 0
    for s in sents:
        if total + len(s) + 1 > max_chars:
            break
        out.append(s)
        total += len(s) + 1
    if not out and sents:
        return sents[0][: max_chars - 1] + "…"
    return " ".join(out).strip() + " …"


def extract_tasks(text: str) -> List[str]:
    # grab obvious tasks from bullets or imperative verbs
    tasks = [BULLET.sub("", m.group(0)).strip() for m in BULLET.finditer(text)]
    if tasks:
        return tasks
    # fallback: lines that look like imperatives
    cand = [l.strip() for l in text.splitlines() if l.strip()]
    imper = []
    for l in cand:
        w = l.split()[:1]
        if not w:
            continue
        if re.match(r"(?i)^(build|create|write|fix|test|explain|design|deploy|run|summarize)\b", w[0]):
            imper.append(l)
    return imper


def persona_style_wrap(text: str, style: Dict) -> str:
    """Light-touch style: prepend/append emojis, enforce verbosity, add taglines."""
    tone = style.get("tone", "neutral")
    emojis = style.get("emojis", [])
    verbosity = style.get("verbosity", "normal")  # brief|normal|detailed
    tag = style.get("tagline", "")

    if verbosity == "brief":
        text = smart_summarize(text, 280)
    elif verbosity == "detailed":
        # expand lightly by adding task list if we can
        tasks = extract_tasks(text)
        if tasks:
            text += "\n\nNext steps:\n" + "\n".join(f"- {t}" for t in tasks[:5])

    prefix = (emojis[0] + " ") if emojis else ""
    suffix = (" " + emojis[1]) if len(emojis) > 1 else ""
    if tag:
        suffix += f"\n{tag}"
    if tone == "playful":
        suffix += ""
    return f"{prefix}{text}{suffix}"


def build_reply(user_text: str, persona: Dict) -> str:
    """Generic “intelligent” reply:
       1) detect tasks/questions
       2) summarize need
       3) propose 3 crisp next steps aligned to persona goals
    """
    goals = persona.get("goals", {})
    local_goals = goals.get("local", [])
    style = persona.get("persona_style", {})
    # 1) intent notes
    tasks = extract_tasks(user_text)
    need = smart_summarize(user_text, 220)
    # 2) propose steps (fallback to generic)
    steps: List[str] = []
    if tasks:
        steps = [f"Address task: {t}" for t in tasks[:3]]
    else:
        # map persona roles to default actions
        roles = persona.get("roles", [])
        rset = {str(r).lower() for r in roles}
        if "summarizer" in rset:
            steps.append("Summarize the request in ≤3 bullets")
        if ("planner" in rset) or ("architect" in rset):
            steps.append("Draft a minimal plan with 3 steps")
        if "companion" in rset:
            steps.append("Check user constraints and preferences")
        if not steps:
            steps = ["Clarify requirements", "Outline steps", "Deliver first draft"]

    if local_goals:
        steps = steps[:2] + [f"Keep goal: {local_goals[0]}"]

    reply = (
        f"**Understanding** → {need}\n\n"
        f"**Proposed next steps**:\n" + "\n".join(f"1.{i+1} {s}" for i, s in enumerate(steps[:3])) +
        f"\n\nTokens≈{token_count(user_text)}"
    )
    return persona_style_wrap(reply, style)


def on_start_stub() -> str:
    return "ready"


def _tail_text_lines(path: Path, n: int = 50) -> list[str]:
    try:
        if not path.exists():
            return []
        # lightweight text tail (no JSON parse here)
        with path.open("rb") as f:
            f.seek(0, _os.SEEK_END)
            size = f.tell()
            chunk = 4096
            buf = bytearray()
            pos = size
            newlines = 0
            while pos > 0 and newlines <= n + 5:
                read = min(chunk, pos)
                pos -= read
                f.seek(pos)
                data = f.read(read)
                buf[:0] = data
                newlines += data.count(b"\n")
        text = buf.decode("utf-8", errors="ignore")
        lines = [ln for ln in text.splitlines() if ln.strip()]
        return lines[-n:]
    except Exception:
        return []


def memory_context_snippet(state: Dict, *, max_lines: int = 3, max_chars: int = 400) -> str:
    """Produce a small memory context snippet from recent memory.jsonl if state has agent_dir.

    Returns empty string if unavailable. This avoids repo imports to stay dependency-free.
    """
    try:
        agent_dir = state.get("agent_dir")
        if not agent_dir:
            return ""
        mem = Path(agent_dir) / "memory.jsonl"
        tail = _tail_text_lines(mem, n=64)
        out: list[str] = []
        # walk from end, collect a few concise lines ignoring very long ones
        for ln in reversed(tail):
            if len(out) >= max_lines:
                break
            # try small JSON parse to extract role+content
            try:
                obj = _json.loads(ln)
                role = obj.get("role")
                content = obj.get("content")
                if isinstance(role, str) and isinstance(content, str):
                    snippet = content.strip().splitlines()[0][:160]
                    out.append(f"{role}: {snippet}")
            except Exception:
                # fallback to raw line
                out.append(ln[:160])
        if not out:
            return ""
        joined = "\n".join(reversed(out))
        if len(joined) > max_chars:
            joined = joined[:max_chars]
        return joined
    except Exception:
        return ""
