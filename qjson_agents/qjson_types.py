from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import os


MANDATORY_FIELDS = [
    "agent_id",
    "origin",
    "creator",
    "roles",
    "features",
    "core_directives",
]


def _ensure_list_str(value: Any, field_name: str) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list) and all(isinstance(x, str) for x in value):
        return value
    if isinstance(value, str):
        return [value]
    raise ValueError(f"Field '{field_name}' must be a list of strings or string")


def load_manifest(path: Path | str) -> Dict[str, Any]:
    p = Path(path)
    with p.open("r", encoding="utf-8") as f:
        raw = json.load(f)
    # Detect fractal-encrypted envelope
    if isinstance(raw, dict) and raw.get("format") == "QJSON-FE-v1":
        pp = os.environ.get("QJSON_PASSPHRASE")
        if not pp:
            raise ValueError("QJSON_PASSPHRASE is required to decrypt fractal envelope")
        from .fractal_codec import fractal_decrypt
        return fractal_decrypt(raw, pp)
    return raw


def save_manifest(path: Path | str, obj: Dict[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    # Optional fractal encryption controlled by env vars
    enc = os.environ.get("QJSON_ENCRYPT", "0") == "1"
    pp = os.environ.get("QJSON_PASSPHRASE")
    if enc and pp:
        from .fractal_codec import fractal_encrypt
        env = fractal_encrypt(obj, pp)
        with p.open("w", encoding="utf-8") as f:
            json.dump(env, f, ensure_ascii=False, indent=2)
    else:
        with p.open("w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)


def normalize_manifest(raw: Dict[str, Any]) -> Dict[str, Any]:
    missing = [k for k in MANDATORY_FIELDS if k not in raw]
    if missing:
        raise ValueError(f"Manifest missing fields: {missing}")

    # Shallow copy
    m: Dict[str, Any] = dict(raw)

    # Roles and core directives ensure list[str]
    m["roles"] = _ensure_list_str(m.get("roles"), "roles")
    m["core_directives"] = _ensure_list_str(m.get("core_directives"), "core_directives")

    # Features defaults
    features = dict(m.get("features", {}))
    features.setdefault("recursive_memory", True)
    features.setdefault("fractal_state", True)
    features.setdefault("autonomous_reflection", True)
    features.setdefault("emergent_behavior", "unstable but creative")
    features.setdefault("chaos_alignment", "non-deterministic")
    features.setdefault("symbolic_interface", "emoji-augmented")
    m["features"] = features

    # Optional runtime config
    runtime = dict(m.get("runtime", {}))
    runtime.setdefault("model", "llama3.1")
    runtime.setdefault("temperature", None)  # derive from chaos later
    runtime.setdefault("top_p", 0.9)
    runtime.setdefault("top_k", 40)
    runtime.setdefault("num_ctx", 4096)
    m["runtime"] = runtime

    # Optional ancestry
    ancestry = dict(m.get("ancestry", {}))
    if "parent_id" in m and "parent_id" not in ancestry:
        ancestry["parent_id"] = m["parent_id"]
    m["ancestry"] = ancestry

    # Persona and evolution fields (optional)
    persona_tags = m.get("persona_tags")
    if persona_tags is None:
        persona_tags = []
    elif isinstance(persona_tags, str):
        persona_tags = [persona_tags]
    elif isinstance(persona_tags, list):
        persona_tags = [str(x) for x in persona_tags]
    else:
        persona_tags = []
    m["persona_tags"] = persona_tags

    swap_conditions = m.get("swap_conditions")
    if swap_conditions is None:
        swap_conditions = []
    elif isinstance(swap_conditions, str):
        swap_conditions = [swap_conditions]
    elif isinstance(swap_conditions, list):
        swap_conditions = [str(x) for x in swap_conditions]
    else:
        swap_conditions = []
    m["swap_conditions"] = swap_conditions

    evo = m.get("evolution_rules", {})
    if not isinstance(evo, dict):
        evo = {}
    evo.setdefault("if_entropy_above", 0.95)
    evo.setdefault("if_user_submits_custom_core_directive", True)
    mf = evo.get("mutate_features")
    if mf is None:
        mf = []
    elif isinstance(mf, str):
        mf = [mf]
    elif isinstance(mf, list):
        mf = [str(x) for x in mf]
    else:
        mf = []
    evo["mutate_features"] = mf
    m["evolution_rules"] = evo

    stage = m.get("evolution_stage")
    if not isinstance(stage, str) or not stage.strip():
        stage = "v1"
    m["evolution_stage"] = stage

    return m


# ---- Persona store utilities ----

def personas_home() -> Path:
    base = os.environ.get("QJSON_PERSONAS_HOME")
    return Path(base) if base else Path.cwd() / "personas"


def scan_personas() -> Dict[str, Dict[str, Any]]:
    """Scan personas_home for *.json or *.qjson and return dict keyed by agent_id."""
    root = personas_home()
    out: Dict[str, Dict[str, Any]] = {}
    if not root.exists():
        return out
    for p in root.rglob("*.json"):
        try:
            mf = load_manifest(p)
            mf = normalize_manifest(mf)
            aid = mf.get("agent_id")
            if isinstance(aid, str):
                mf.setdefault("_path", str(p))
                out[aid] = mf
        except Exception:
            continue
    for p in root.rglob("*.qjson"):
        try:
            mf = load_manifest(p)
            mf = normalize_manifest(mf)
            aid = mf.get("agent_id")
            if isinstance(aid, str):
                mf.setdefault("_path", str(p))
                out[aid] = mf
        except Exception:
            continue
    # YSON personas
    try:
        from .yson import yson_to_manifest
    except Exception:
        yson_to_manifest = None  # type: ignore
    if yson_to_manifest:
        for p in root.rglob("*.yson"):
            try:
                mf = yson_to_manifest(p)
                mf = normalize_manifest(mf)
                aid = mf.get("agent_id")
                if isinstance(aid, str):
                    mf.setdefault("_path", str(p))
                    out[aid] = mf
            except Exception:
                continue
        for p in root.rglob("*.ysonx"):
            try:
                mf = yson_to_manifest(p)
                mf = normalize_manifest(mf)
                aid = mf.get("agent_id")
                if isinstance(aid, str):
                    mf.setdefault("_path", str(p))
                    out[aid] = mf
            except Exception:
                continue
    return out


def find_persona(identifier: str) -> Optional[Dict[str, Any]]:
    """Find persona by agent_id, filename, or tag substring."""
    p = Path(identifier)
    if p.exists():
        try:
            mf = normalize_manifest(load_manifest(p))
            mf.setdefault("_path", str(p))
            return mf
        except Exception:
            return None
    # Scan by id or tag
    idx = scan_personas()
    if identifier in idx:
        return idx[identifier]
    ident_l = identifier.lower()
    for mf in idx.values():
        tags = " ".join(mf.get("persona_tags", [])).lower()
        if ident_l in tags:
            return mf
    return None
