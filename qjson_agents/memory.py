from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional
import threading


def _now_ts() -> float:
    return time.time()


def agents_home() -> Path:
    base = os.environ.get("QJSON_AGENTS_HOME")
    return Path(base) if base else Path.cwd() / "state"


def agent_dir(agent_id: str) -> Path:
    return agents_home() / agent_id


def ensure_agent_dirs(agent_id: str) -> Path:
    d = agent_dir(agent_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def append_jsonl(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False))
        f.write("\n")
    # Incremental cluster index counters on hot paths
    try:
        fname = path.name
        if fname in ("memory.jsonl", "events.jsonl"):
            _bump_index_counter(path.parent.name, mem_inc=1 if fname == "memory.jsonl" else 0, ev_inc=1 if fname == "events.jsonl" else 0)
    except Exception:
        # Best-effort only; never block appends
        pass


def tail_jsonl(path: Path, n: int = 20) -> List[Dict[str, Any]]:
    """Return last n JSONL entries without reading the whole file into memory.

    Reads from the end in chunks and stops when enough newlines are found.
    """
    if not path.exists() or n <= 0:
        return []
    try:
        # Read from end in binary chunks
        chunk_size = 128 * 1024
        max_chunks = 100 # Safeguard: read at most 100 chunks (12.8MB)
        with path.open("rb") as f:
            f.seek(0, os.SEEK_END)
            end = f.tell()
            pos = end
            buf = bytearray()
            newlines = 0
            chunks_read = 0
            while pos > 0 and newlines <= n * 2 and chunks_read < max_chunks:
                read = min(chunk_size, pos)
                pos -= read
                f.seek(pos)
                chunk = f.read(read)
                buf[:0] = chunk  # prepend
                newlines += chunk.count(b"\n")
                chunks_read += 1
                if newlines >= n + 5:  # some slack
                    break
        text = buf.decode("utf-8", errors="ignore")
        lines = [ln for ln in text.splitlines() if ln.strip()]
        tail = lines[-n:]
        out: List[Dict[str, Any]] = []
        for line in tail:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return out
    except Exception:
        # Fallback to naive method in case of unexpected errors
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except Exception:
            return []
        out: List[Dict[str, Any]] = []
        for line in lines[-n:]:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return out


# ---- Router weights persistence ----

def _router_weights_path() -> Path:
    return agents_home() / "router_weights.json"


def load_router_weights() -> Dict[str, float]:
    p = _router_weights_path()
    if not p.exists():
        return {}
    try:
        with p.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return {str(k): float(v) for k, v in data.items()}
    except Exception:
        pass
    return {}


def save_router_weights(weights: Dict[str, float]) -> None:
    p = _router_weights_path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w", encoding="utf-8") as f:
            json.dump(weights, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# ---- Cluster index helpers ----

def index_path() -> Path:
    return agents_home() / "index.json"

# Debounced writes for index updates
_INDEX_LAST_WRITE: Dict[str, float] = {}
_INDEX_LOCK = threading.Lock()
_INDEX_DEBOUNCE_SEC = 1.0

def _write_index(idx: Dict[str, Any]) -> None:
    write_json(index_path(), idx)

def _bump_index_counter(agent_id: str, *, mem_inc: int = 0, ev_inc: int = 0) -> None:
    if not agent_id:
        return
    with _INDEX_LOCK:
        idx = load_cluster_index()
        agents = idx.setdefault("agents", {})
        entry = agents.get(agent_id, {})
        # Ensure manifest path and created_ts are present if missing
        d = agent_dir(agent_id)
        mpath = d / "manifest.json"
        entry.setdefault("manifest_path", str(mpath))
        if "created_ts" not in entry:
            try:
                entry["created_ts"] = mpath.stat().st_mtime
            except Exception:
                entry["created_ts"] = _now_ts()
        counters = entry.get("counters") or {}
        # Initialize counters if absent using a cheap 0 start
        mem_lines = int(counters.get("memory_lines") or 0)
        ev_lines = int(counters.get("events_lines") or 0)
        if mem_inc:
            mem_lines += int(mem_inc)
        if ev_inc:
            ev_lines += int(ev_inc)
        entry["counters"] = {"memory_lines": mem_lines, "events_lines": ev_lines}
        agents[agent_id] = entry
        idx["updated"] = _now_ts()
        # Debounce writes per agent to reduce churn
        now = _now_ts()
        last = float(_INDEX_LAST_WRITE.get(agent_id) or 0.0)
        if now - last >= _INDEX_DEBOUNCE_SEC:
            _write_index(idx)
            _INDEX_LAST_WRITE[agent_id] = now


def _safe_count_lines(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        with path.open("r", encoding="utf-8") as f:
            return sum(1 for _ in f)
    except Exception:
        return 0


def load_cluster_index() -> Dict[str, Any]:
    p = index_path()
    if not p.exists():
        return {"updated": _now_ts(), "agents": {}}
    try:
        with p.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"updated": _now_ts(), "agents": {}}


def update_cluster_index_entry(agent_id: str, parent_id: Optional[str] = None) -> None:
    idx = load_cluster_index()
    d = agent_dir(agent_id)
    mpath = d / "manifest.json"
    mem = d / "memory.jsonl"
    ev = d / "events.jsonl"

    entry = idx.get("agents", {}).get(agent_id, {})
    entry["parent_id"] = parent_id
    entry["manifest_path"] = str(mpath)
    if "created_ts" not in entry:
        try:
            entry["created_ts"] = mpath.stat().st_mtime
        except Exception:
            entry["created_ts"] = _now_ts()
    # Only compute counters if absent; otherwise trust incremental bumps
    counters = entry.get("counters") or {}
    if "memory_lines" not in counters:
        counters["memory_lines"] = _safe_count_lines(mem)
    if "events_lines" not in counters:
        counters["events_lines"] = _safe_count_lines(ev)
    entry["counters"] = counters

    idx.setdefault("agents", {})[agent_id] = entry
    idx["updated"] = _now_ts()
    # Debounce writes similar to bump to reduce churn from hot paths
    now = _now_ts()
    last = float(_INDEX_LAST_WRITE.get(agent_id) or 0.0)
    if now - last >= _INDEX_DEBOUNCE_SEC:
        write_json(index_path(), idx)
        _INDEX_LAST_WRITE[agent_id] = now


def refresh_cluster_index() -> Dict[str, Any]:
    base = agents_home()
    out: Dict[str, Any] = {"updated": _now_ts(), "agents": {}}
    if not base.exists():
        write_json(index_path(), out)
        return out
    for sub in base.iterdir():
        if not sub.is_dir():
            continue
        mpath = sub / "manifest.json"
        if not mpath.exists():
            continue
        try:
            with mpath.open("r", encoding="utf-8") as f:
                manifest = json.load(f)
        except Exception:
            manifest = {}
        agent_id = manifest.get("agent_id") or sub.name
        ancestry = manifest.get("ancestry", {}) if isinstance(manifest, dict) else {}
        parent_id = ancestry.get("parent_id")
        mem = sub / "memory.jsonl"
        ev = sub / "events.jsonl"
        entry = {
            "parent_id": parent_id,
            "manifest_path": str(mpath),
            "created_ts": getattr(mpath.stat(), "st_mtime", _now_ts()),
            "counters": {
                "memory_lines": _safe_count_lines(mem),
                "events_lines": _safe_count_lines(ev),
            },
        }
        out["agents"][agent_id] = entry
    out["updated"] = _now_ts()
    write_json(index_path(), out)
    return out
