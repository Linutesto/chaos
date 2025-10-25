from __future__ import annotations

import ast
import json
import re
from pathlib import Path
import os
from typing import Any, Dict, Optional, Tuple, List


def _parse_meta(lines: List[str]) -> Dict[str, Any]:
    meta: Dict[str, Any] = {}
    for ln in lines:
        if ln.startswith("#@"):
            # format: #@key: value
            try:
                key, val = ln[2:].split(":", 1)
                meta[key.strip()] = val.strip()
            except ValueError:
                continue
    return meta


def _extract_logic(source: str) -> Dict[str, Any]:
    # naive: find a top-level line starting with 'logic:' and capture everything after it
    logic_ns: Dict[str, Any] = {}
    # SAFE_MODE gate (default ON): do not execute embedded logic unless explicitly allowed
    safe_mode = os.environ.get("QJSON_SAFE_MODE", "1") != "0"
    allow_exec = os.environ.get("QJSON_ALLOW_YSON_EXEC", "0") == "1"
    if safe_mode and not allow_exec:
        return logic_ns
    lines = source.splitlines()
    if any(ln.strip().startswith("logic:") for ln in lines):
        # capture block following first 'logic:'
        start = None
        for i, ln in enumerate(lines):
            if ln.strip().startswith("logic:"):
                start = i + 1
                break
        if start is not None:
            code = "\n".join(lines[start:])
            # Remove comment directives like '#@exec:py'
            code = "\n".join(l for l in code.splitlines() if not l.strip().startswith("#@"))
            try:
                tree = ast.parse(code)
                exec(compile(tree, filename="<yson_logic>", mode="exec"), logic_ns)
            except Exception:
                # leave empty on failure
                pass
    return logic_ns


def _strip_meta(text: str) -> Tuple[Dict[str, Any], str]:
    lines = text.splitlines()
    meta = _parse_meta(lines)
    # Remove meta and comment lines for body parsing
    body_lines = [ln for ln in lines if not (ln.startswith("#@") or ln.strip().startswith("#"))]
    return meta, "\n".join(body_lines).strip()


def _try_json(text: str) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(text)
    except Exception:
        return None


def _try_yaml(text: str) -> Optional[Dict[str, Any]]:
    try:
        import yaml  # type: ignore
    except Exception:
        return None
    try:
        data = yaml.safe_load(text)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _json5_like_to_json(text: str) -> Optional[Dict[str, Any]]:
    # Remove comments beginning with '#'
    cleaned = "\n".join(ln for ln in text.splitlines() if not ln.strip().startswith("#"))
    # Quote unquoted keys at line starts or after '{' / ','
    cleaned = re.sub(r'(?m)(^|[{,]\s*)([A-Za-z_][A-Za-z0-9_\-]*)\s*:', r'\1"\2":', cleaned)
    # Remove trailing commas before } or ]
    cleaned = re.sub(r',\s*([}\]])', r'\1', cleaned)
    # Replace single quotes with double quotes where safe
    cleaned = re.sub(r"'", '"', cleaned)
    # Attempt JSON parse
    return _try_json(cleaned)


def load_yson(path: str | Path) -> Dict[str, Any]:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    meta, body_text = _strip_meta(text)
    logic = _extract_logic(text)
    body: Dict[str, Any] = {}
    # Try JSON → YAML → JSON5-like
    cand = _try_json(body_text)
    if cand is None:
        cand = _try_yaml(body_text)
    if cand is None and ('{' in body_text or '}' in body_text):
        cand = _json5_like_to_json(body_text)
    if isinstance(cand, dict):
        body = cand
    return {"meta": meta, "logic": logic, "raw": text, "body": body}


def yson_to_manifest(path: str | Path) -> Dict[str, Any]:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    # Parse full YSON/YSONX first to access top-level body fields if present
    try:
        parsed = load_yson(p)
        body = parsed.get("body") or {}
    except Exception:
        body = {}
    meta, stripped = _strip_meta(text)
    lines = stripped.splitlines()

    # Extract simple fields via regex heuristics
    def rx(pattern: str) -> Optional[str]:
        m = re.search(pattern, text, re.MULTILINE)
        return m.group(1).strip() if m else None

    # Try agent.id or identity.name
    agent_id = rx(r"^\s*agent:\s*\n(?:[\s\S]*?)^\s*id:\s*\"?([^\"\n]+)\"?\s*$") or rx(r"^\s*identity:\s*\n(?:[\s\S]*?)^\s*name:\s*\"?([^\"\n]+)\"?\s*$")
    if not agent_id:
        agent_id = p.stem

    # Creator and origin (best-effort)
    creator = rx(r"^\s*identity:\s*\n(?:[\s\S]*?)^\s*creator:\s*\"?([^\"\n]+)\"?\s*$") or meta.get("creator") or "Unknown"
    origin = rx(r"^\s*identity:\s*\n(?:[\s\S]*?)^\s*origin:\s*\"?([^\"\n]+)\"?\s*$") or meta.get("origin") or "YSON"

    # Tags from #@tags: [...] or tags: [...] under header
    tags_val = None
    for ln in lines:
        if ln.startswith("#@tags:"):
            raw = ln.split(":", 1)[1].strip()
            try:
                tags_val = ast.literal_eval(raw)
            except Exception:
                tags_val = None
            break
    if tags_val is None:
        # Try agent.tags: [...] in YAML (best effort)
        m = re.search(r"^\s*agent:\s*\n(?:[\s\S]*?)^\s*tags:\s*\[(.*?)\]", text, re.MULTILINE)
        if m:
            raw = "[" + m.group(1) + "]"
            try:
                tags_val = ast.literal_eval(raw)
            except Exception:
                tags_val = []
    roles = [str(t) for t in (tags_val or [])]
    if not roles:
        roles = ["observer"]

    # Build a minimal manifest (carry over selected sections from body if present)
    manifest: Dict[str, Any] = {
        "agent_id": agent_id,
        "origin": origin,
        "creator": creator,
        "roles": roles,
        "features": {
            "recursive_memory": True,
            "fractal_state": True,
            "autonomous_reflection": True,
            "emergent_behavior": "experimental",
            "chaos_alignment": "balanced",
            "symbolic_interface": "emoji-augmented",
        },
        "core_directives": [
            "Act ethically and lawfully; refuse unsafe requests",
            "Preserve identity and document anomalies",
            "Favor clarity and continuity",
        ],
        "runtime": {"model": "gemma3:4b"},
        # YSON specifics are attached for reference
        "_yson": {"meta": meta, "path": str(p)},
    }
    # Preserve persona_style and logic blocks when present in body
    if isinstance(body.get("persona_style"), dict):
        manifest["persona_style"] = body.get("persona_style")
    if isinstance(body.get("logic"), dict):
        manifest["logic"] = body.get("logic")
    return manifest


def yson_to_swarm(path: str | Path) -> Dict[str, Any]:
    data = load_yson(path)
    body = data.get("body") or {}
    swarm = body.get("swarm_architecture") or {}
    agents = swarm.get("agents") or []
    if not isinstance(agents, list):
        agents = []
    goals = body.get("goals") or {}
    goals_out: Dict[str, Any] = {}
    if isinstance(goals, dict):
        if isinstance(goals.get("global"), str):
            goals_out["global"] = goals.get("global")
        if isinstance(goals.get("template"), str):
            goals_out["template"] = goals.get("template")
        if isinstance(goals.get("agents"), list):
            goals_out["agents"] = [str(x) for x in goals.get("agents")]
    # Fallback parsing by regex if body failed
    if not agents:
        try:
            text = Path(path).read_text(encoding="utf-8")
            m = re.search(r"swarm_architecture\s*:\s*\{[\s\S]*?agents\s*:\s*\[(.*?)\]", text, re.MULTILINE)
            if m:
                raw = m.group(1)
                parts = [x.strip() for x in raw.split(",") if x.strip()]
                agents = [p.strip().strip("'\"") for p in parts if p]
            else:
                m2 = re.search(r"agents\s*:\s*\[(.*?)\]", text, re.MULTILINE)
                if m2:
                    raw = m2.group(1)
                    parts = [x.strip() for x in raw.split(",") if x.strip()]
                    agents = [p.strip().strip("'\"") for p in parts if p]
        except Exception:
            pass
    # Goals fallback parse
    if not goals_out.get("global") or not goals_out.get("agents"):
        try:
            text = Path(path).read_text(encoding="utf-8")
            mg = re.search(r"goals\s*:\s*\{[\s\S]*?global\s*:\s*\"([^\"]*)\"", text, re.MULTILINE)
            if mg and not goals_out.get("global"):
                goals_out["global"] = mg.group(1)
            mag = re.search(r"goals[\s\S]*?agents\s*:\s*\[(.*?)\]", text, re.MULTILINE)
            if mag and not goals_out.get("agents"):
                raw = mag.group(1)
                parts = [x.strip() for x in raw.split(",") if x.strip()]
                goals_out["agents"] = [p.strip().strip("'\"") for p in parts if p]
        except Exception:
            pass

    return {
        "meta": data.get("meta", {}),
        "config": body,
        "agents": [str(a) for a in agents],
        "logic": data.get("logic", {}),
        "goals": goals_out,
    }


def synthesize_manifest_from_yson_name(name: str, *, model: str = "gemma3:4b", num_predict: int | None = None) -> Dict[str, Any]:
    # Simple roles inferred from name tokens
    tokens = [t for t in re.split(r"[^A-Za-z0-9]+", name) if t]
    inferred_roles = ["observer"]
    if any("echo" in t.lower() for t in tokens):
        inferred_roles.append("archivist")
    if any("rogue" in t.lower() or "chaos" in t.lower() for t in tokens):
        inferred_roles.append("chaos amplifier")
    if any("oracle" in t.lower() for t in tokens):
        inferred_roles.append("summarizer")
    runtime: Dict[str, Any] = {"model": model}
    if num_predict is not None:
        runtime["num_predict"] = int(num_predict)
    manifest: Dict[str, Any] = {
        "agent_id": name,
        "origin": "YSON",
        "creator": "Unknown",
        "roles": inferred_roles,
        "features": {
            "recursive_memory": True,
            "fractal_state": True,
            "autonomous_reflection": True,
            "emergent_behavior": "experimental",
            "chaos_alignment": "balanced",
            "symbolic_interface": "emoji-augmented",
        },
        "core_directives": [
            "Act ethically and lawfully; refuse unsafe requests",
            "Preserve identity and document anomalies",
            "Favor clarity and continuity",
        ],
        "runtime": runtime,
    }
    return manifest


def validate_swarm_strict(doc: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Basic strict checks for swarm YSON documents (no external deps)."""
    errs: List[str] = []
    if not isinstance(doc, dict):
        return False, ["root must be an object"]
    sa = doc.get("swarm_architecture")
    if not isinstance(sa, dict):
        errs.append("swarm_architecture must be an object")
    else:
        agents = sa.get("agents")
        if not isinstance(agents, list) or not all(isinstance(x, str) for x in agents):
            errs.append("swarm_architecture.agents must be an array of strings")
        if "type" in sa and not isinstance(sa.get("type"), str):
            errs.append("swarm_architecture.type must be a string")
        if "selection_strategy" in sa and not isinstance(sa.get("selection_strategy"), str):
            errs.append("swarm_architecture.selection_strategy must be a string")
    # Optional runtime checks
    rt = doc.get("runtime")
    if rt is not None:
        if not isinstance(rt, dict):
            errs.append("runtime must be an object")
        else:
            if "model" in rt and not isinstance(rt.get("model"), str):
                errs.append("runtime.model must be a string")
            if "num_predict" in rt and not isinstance(rt.get("num_predict"), int):
                errs.append("runtime.num_predict must be an integer")
    # Optional goals checks
    goals = doc.get("goals")
    if goals is not None:
        if not isinstance(goals, dict):
            errs.append("goals must be an object if present")
        else:
            if "global" in goals and not isinstance(goals.get("global"), str):
                errs.append("goals.global must be a string")
            if "template" in goals and not isinstance(goals.get("template"), str):
                errs.append("goals.template must be a string")
            if "agents" in goals:
                ga = goals.get("agents")
                if not isinstance(ga, list) or not all(isinstance(x, (str)) for x in ga):
                    errs.append("goals.agents must be an array of strings")
                else:
                    # Length check against swarm_architecture.agents
                    if isinstance(sa, dict) and isinstance(sa.get("agents"), list):
                        if len(ga) != len(sa.get("agents")):
                            errs.append(
                                f"goals.agents length ({len(ga)}) does not match swarm_architecture.agents length ({len(sa.get('agents'))}); runtime will pad/truncate"
                            )
    return len(errs) == 0, errs
