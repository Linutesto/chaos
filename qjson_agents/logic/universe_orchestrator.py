from __future__ import annotations

"""
Universe-Orchestrator persona logic hooks.

Implements a dependency-free, stateful handler suitable for qjson-agents CLI
logic hooks. Expected entrypoints (exported):
  - on_start(state: dict, persona: dict) -> str
  - on_message(state: dict, user_text: str, persona: dict) -> str

State is a mutable dict persisted by the CLI between turns.
"""

from typing import Dict, List


def _sha256_hex(text: str) -> str:
    import hashlib
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _ensure_state(state: Dict) -> Dict:
    # Initialize expected keys if absent
    state.setdefault("cosmos_id", None)
    state.setdefault("turns", 0)
    state.setdefault("constellations", [])  # list of {turn, snippets}
    state.setdefault("anomalies", [])
    return state


def _generate_cosmos_id(seed: str) -> str:
    h = _sha256_hex(seed)[:8].upper()
    checksum = sum(ord(c) for c in seed) % 97 + 1
    return f"COSMOS-{h}:{checksum}"


def _orbit_summarize(text: str, max_points: int = 3) -> List[str]:
    # Heuristic, dependency-free summarizer that extracts up to N salient lines.
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    scored = []
    for ln in lines:
        score = len(ln)
        if ":" in ln or " - " in ln:
            score += 20
        if any(ch.isdigit() for ch in ln):
            score += 10
        scored.append((score, ln))
    scored.sort(reverse=True, key=lambda x: x[0])
    return [ln for _, ln in scored[: max(1, int(max_points))]]


def _gravitational_priority(tasks: List[Dict]) -> List[Dict]:
    ranked: List[Dict] = []
    for t in tasks:
        impact = int(t.get("impact", 3))
        urgency = int(t.get("urgency", 3))
        gravity = impact * 2 + urgency  # impact weighs double
        ranked.append({**t, "gravity": gravity})
    ranked.sort(key=lambda x: x["gravity"], reverse=True)
    return ranked


def _anomaly(state: Dict, msg: str) -> None:
    state = _ensure_state(state)
    state["anomalies"].append(str(msg))


def on_start(state: Dict, persona: Dict) -> str:
    """Optional startup hook for future use. Returns a small system note."""
    state = _ensure_state(state)
    aid = (persona or {}).get("agent_id") or "AstraPrime"
    seed = f"{aid}|boot"
    state["cosmos_id"] = state.get("cosmos_id") or _generate_cosmos_id(seed)
    return f"[Universe-Orchestrator booted] cosmos_id={state['cosmos_id']}"


def on_message(state: Dict, user_text: str, persona: Dict) -> str:
    """Primary logic entrypoint used by the CLI.

    Mutates state in place and returns a reply string. Supports intents:
    /cosmos, /summarize, /plan, /role, /mem
    """
    state = _ensure_state(state)
    state["turns"] = int(state.get("turns") or 0) + 1

    aid = (persona or {}).get("agent_id") or "AstraPrime"
    if not state.get("cosmos_id"):
        seed = f"{aid}|session"
        state["cosmos_id"] = _generate_cosmos_id(seed)
    cosmos = state.get("cosmos_id") or "COSMOS-UNKNOWN"

    text = (user_text or "").strip()
    orbit = _orbit_summarize(text, max_points=3)
    if orbit:
        state["constellations"].append({"turn": state["turns"], "snippets": orbit})

    lower = text.lower()
    intent = "chat"
    if lower.startswith("/cosmos"):
        intent = "cosmos"
    elif lower.startswith("/plan"):
        intent = "plan"
    elif lower.startswith("/summarize") or "summarize" in lower:
        intent = "summarize"
    elif lower.startswith("/role") or "what role" in lower:
        intent = "role"
    elif lower.startswith("/mem") or "memory" in lower:
        intent = "memory"

    if intent == "cosmos":
        return (
            f"🪐 COSMOS ID: **{cosmos}**\n"
            f"Turns logged: {state['turns']}\n"
            f"Constellations stored: {len(state['constellations'])}\n"
            f"Anomalies: {len(state['anomalies'])}"
        )

    if intent == "summarize":
        bullets = orbit if orbit else ["(no salient lines detected)"]
        return "### Constellation Summary\n" + "\n".join(f"- {b}" for b in bullets)

    if intent == "plan":
        # Parse "/plan desc|impact|urgency, desc|impact|urgency"
        ranked: List[Dict]
        try:
            raw = text.split(" ", 1)[1] if " " in text else ""
            items: List[Dict] = []
            for chunk in [c for c in raw.split(",") if c.strip()]:
                parts = [p.strip() for p in chunk.split("|")]
                if not parts or not parts[0]:
                    continue
                desc = parts[0]
                impact = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 3
                urgency = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 3
                items.append({"desc": desc, "impact": impact, "urgency": urgency})
            ranked = _gravitational_priority(items) if items else []
        except Exception as e:  # defensive
            _anomaly(state, f"/plan parsing error: {e}")
            ranked = []

        if not ranked:
            return "Provide tasks like: `/plan Draft README|5|3, Record demo|4|5`"
        lines = [
            f"1) {t['desc']}  (gravity={t['gravity']} | impact={t['impact']} • urgency={t['urgency']})"
            for t in ranked
        ]
        return "### Gravitational Priority Plan\n" + "\n".join(lines)

    if intent == "role":
        return (
            "**Active Roles:** orchestrator + summarizer + planner\n"
            "- I stabilize chaos (priorities),\n"
            "- weave memory constellations,\n"
            "- and keep safety gravity on at all times. 🛰️"
        )

    if intent == "memory":
        last = state.get("constellations", [])[-3:]
        digest: List[str] = []
        for c in last:
            for s in c.get("snippets", []):
                digest.append(f"t{c.get('turn')}: {s}")
        if not digest:
            digest = ["(no memory yet)"]
        body = "\n".join(f"- {d}" for d in digest)
        return f"### Memory Constellations (latest)\n{body}\n\nEdges conceptual cap: 50 • Hashing: sha256"

    # Default scaffold
    orbit_text = ", ".join(orbit) if orbit else "—"
    return (
        f"**AstraPrime online** (cosmos={cosmos})\n"
        f"**Orbit**: {orbit_text}\n"
        f"**Next**: Tell me if you want `/summarize`, `/plan`, `/cosmos`, `/role`, or `/mem`."
    )

