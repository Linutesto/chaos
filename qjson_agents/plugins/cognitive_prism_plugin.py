from __future__ import annotations

import json
import time
from typing import Any, Callable, Dict, List
import os

from qjson_agents.plugin_manager import Plugin


DEFAULT_HATS = [
    ("optimist", "Highlight opportunities, best-case outcomes, and upside."),
    ("pessimist", "Identify risks, failure modes, and constraints."),
    ("creative", "Propose novel approaches and analogies."),
    ("critic", "Challenge assumptions and test robustness."),
]


def _ts() -> float:
    import time as _t
    return _t.time()


class CognitivePrismPlugin(Plugin):
    """Multi-perspective analysis using configurable "thinking hats".

    Usage:
      /prism <QUESTION...> [hats=a,b,c]

    Behavior:
      - Records perspectives into Fractal Memory under analysis/prism/<ts>/
      - Returns a concise synthesized outline (no LLM required)
    """

    def get_commands(self) -> Dict[str, Callable[..., Any]]:
        return {"/prism": self.prism}

    def prism(self, *parts: str) -> str:
        if not parts:
            return "Usage: /prism <QUESTION...> [hats=a,b,c]"
        # Parse hats option
        raw = list(parts)
        opts = [p for p in raw if p.startswith("hats=")]
        hats: List[str] = []
        if opts:
            hats = [s.strip() for s in opts[0].split("=",1)[1].split(",") if s.strip()]
            for p in opts:
                raw.remove(p)
        question = " ".join(raw).strip()
        if not hats:
            hats = [h for h,_ in DEFAULT_HATS]
        # Dynamic generation: hats=auto chooses a themed set
        if len(hats) == 1 and hats[0].lower() in ("auto","gen","dynamic"):
            hats = self._auto_hats(question)
        # Build entries
        entries: List[Dict[str, str]] = []
        guidance = {k:v for k,v in DEFAULT_HATS}
        for h in hats:
            g = guidance.get(h, "Provide a useful perspective.")
            # No LLM call; just structure the task and store guidance
            entries.append({
                "hat": h,
                "prompt": f"{h}: {g}",
                "note": f"Compose an analysis for: {question}",
            })
        # Store in FMM under analysis/prism
        agent_id = os.environ.get("QJSON_AGENT_ID") or "Prism"
        try:
            from qjson_agents.fmm_store import PersistentFractalMemory
            fmm = PersistentFractalMemory(agent_id)
            path = ["analysis","prism", time.strftime("%Y%m%d-%H%M%S", time.gmtime(_ts()))]
            for e in entries:
                fmm.insert(path, {"ts": _ts(), "question": question, **e})
            fmm.persist()
        except Exception:
            pass
        # Return a synthesized preview
        bullets = [f"- {e['hat']}: {e['prompt']}" for e in entries]
        header = "### Cognitive Prism: Multi-perspective plan"
        return header + "\n" + "\n".join(bullets)

    def _auto_hats(self, question: str) -> List[str]:
        q = (question or "").lower()
        base = [h for h,_ in DEFAULT_HATS]
        extras: List[str] = []
        if any(k in q for k in ("api","network","http","web")):
            extras.append("engineer")
        if any(k in q for k in ("ux","user","customer","human")):
            extras.append("user")
        if any(k in q for k in ("risk","security","failure","bug")):
            extras.append("security")
        if not extras:
            extras = ["visionary","skeptic"]
        # pick up to 4 unique hats
        out: List[str] = []
        for h in base + extras:
            if h not in out:
                out.append(h)
            if len(out) >= 4:
                break
        return out
