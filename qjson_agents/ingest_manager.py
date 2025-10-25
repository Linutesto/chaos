#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ingest_manager.py
Drop-in module to handle file & directory ingestion from the chat CLI.
Supports /inject (ysonx, json, yaml, txt) and /inject_py (python files).
Also persists ingestion summaries into the agent's system memory and FMM.
"""

from __future__ import annotations

import json
import os
import re
import traceback
from pathlib import Path
import os
import re
from typing import Dict, List, Iterable
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    import yaml  # type: ignore
except Exception:  # optional dependency
    yaml = None  # type: ignore

# In-repo imports for memory persistence
from .memory import append_jsonl, agent_dir, _now_ts
from .fmm_store import PersistentFractalMemory

# In-memory store of injected data (can be hooked into agent memory later)
agent_context: Dict[str, List[Dict[str, object]]] = {}


# ──────────────────────────────────────────────
# 📦 BASIC FILE OPS
# ──────────────────────────────────────────────

def read_file(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()


def _normalize_user_path(raw: str) -> Path:
    s = (raw or "").strip().strip('"').strip("'")
    # Expand env vars and home
    s = os.path.expandvars(os.path.expanduser(s))
    # Collapse whitespace around slashes (helps when UI inserts spaces/newlines)
    s = re.sub(r"\s*/\s*", "/", s)
    # If still not found, try collapsing consecutive whitespace
    if not s:
        return Path("")
    return Path(s)


def list_files_in_path(path: str) -> List[str]:
    p = _normalize_user_path(path)
    if p.exists() and p.is_file():
        return [str(p)]
    if p.exists() and p.is_dir():
        return [str(x) for x in sorted(p.iterdir()) if x.is_file()]
    # Fallback: if the normalized form still doesn't exist, try removing stray spaces around slashes again
    alt = re.sub(r"\s+", " ", (path or "").strip())
    alt = re.sub(r"\s*/\s*", "/", alt)
    q = Path(os.path.expandvars(os.path.expanduser(alt)))
    if q.exists() and q.is_file():
        return [str(q)]
    if q.exists() and q.is_dir():
        return [str(x) for x in sorted(q.iterdir()) if x.is_file()]
    return []


def scan_path(path: str, allowed_ext: Iterable[str], recursive: bool = True) -> List[str]:
    base = _normalize_user_path(path)
    out: List[str] = []
    allowed = set(x.lower() for x in allowed_ext)
    if base.exists() and base.is_file():
        ext = base.suffix.lower()
        if ext in allowed:
            out.append(str(base))
        return out
    if not base.exists() or not base.is_dir():
        return out
    if recursive:
        for p in base.rglob("*"):
            if p.is_file() and p.suffix.lower() in allowed:
                out.append(str(p))
    else:
        for p in sorted(base.iterdir()):
            if p.is_file() and p.suffix.lower() in allowed:
                out.append(str(p))
    return out


# ──────────────────────────────────────────────
# 🧠 YSONX PARSER (YAML + JSON + Python)
# ──────────────────────────────────────────────

def parse_ysonx(raw: str) -> Dict[str, object]:
    """
    Splits YSONX-like content into 3 sections: YAML | JSON | Python by '---' markers when present.
    If parsing fails, returns a raw payload with an error.
    """
    try:
        parts = re.split(r"\n---+\n", raw)
        yml, js, py = (parts + ["", "", ""])[:3]

        yml_dict = yaml.safe_load(yml) if yaml and yml.strip() else {}
        js_dict = json.loads(js) if js.strip() else {}
        py_code = py.strip()

        return {
            "type": "ysonx",
            "yaml": yml_dict,
            "json": js_dict,
            "python_code": py_code,
        }
    except Exception as e:
        traceback.print_exc()
        return {"type": "ysonx", "raw": raw, "error": str(e)}


# ──────────────────────────────────────────────
# 🐍 PYTHON PARSER (SAFE EVAL HOOK)
# ──────────────────────────────────────────────

def parse_python_file(raw: str) -> Dict[str, object]:
    """
    Store python source code safely without executing by default.
    (Optional exec can be added later for dynamic agents)
    """
    return {"type": "python", "source": raw}


# ──────────────────────────────────────────────
# 🧠 MEMORY REGISTRATION
# ──────────────────────────────────────────────

def _persist_ingest_event(agent_id: str, files: List[str], kind: str) -> None:
    try:
        d = agent_dir(agent_id)
        append_jsonl(
            d / "events.jsonl",
            {
                "ts": _now_ts(),
                "type": "ingest",
                "meta": {"files": files, "kind": kind},
            },
        )
    except Exception:
        pass
    try:
        fmm = PersistentFractalMemory(agent_id)
        fmm.insert(["ingest", kind], {"ts": _now_ts(), "files": files})
    except Exception:
        pass


def register_to_agent_memory(agent_id: str | None, path: str, data: dict) -> None:
    if agent_id is None:
        agent_id = "_GLOBAL_"
    agent_context.setdefault(agent_id, []).append({"path": path, "data": data})
    print(f"[•] Loaded: {os.path.basename(path)} ({data.get('type','unknown')})")


def list_agent_memory(agent_id: str) -> None:
    if agent_id not in agent_context:
        print(f"[!] No memory for agent {agent_id}")
        return
    print(f"=== Memory for agent [{agent_id}] ===")
    for idx, entry in enumerate(agent_context[agent_id]):
        d = entry.get("data", {}) if isinstance(entry, dict) else {}
        print(f"{idx+1:02d}) {entry.get('path')}  [{d.get('type','unknown')}]")
    print("====================================")


def clear_agent_memory(agent_id: str) -> None:
    agent_context.pop(agent_id, None)
    print(f"[x] Memory cleared for agent [{agent_id}]")


# ──────────────────────────────────────────────
# 🧰 INGESTION ENTRYPOINTS
# ──────────────────────────────────────────────

def ingest_path(path: str, agent_id: str | None = None) -> None:
    files = list_files_in_path(path)
    count = 0
    for file_path in files:
        ext = Path(file_path).suffix.lower()
        raw = read_file(file_path)
        data = None

        if ext == ".ysonx":
            data = parse_ysonx(raw)
        elif ext in [".json", ".yaml", ".yml", ".txt"]:
            data = {"type": ext.strip("."), "raw": raw}
        else:
            print(f"[!] Skipping unsupported file: {file_path}")
            continue

        register_to_agent_memory(agent_id, file_path, data)
        count += 1

    if agent_id:
        _persist_ingest_event(agent_id, files, kind="inject")
    print(f"[+] Ingested {count} file(s) into agent [{agent_id}] ✅")


def ingest_path_py(path: str, agent_id: str | None = None) -> None:
    files = list_files_in_path(path)
    count = 0
    kept: List[str] = []
    for file_path in files:
        ext = Path(file_path).suffix.lower()
        if ext != ".py":
            print(f"[!] Skipping non-Python file: {file_path}")
            continue
        raw = read_file(file_path)
        data = parse_python_file(raw)
        register_to_agent_memory(agent_id, file_path, data)
        count += 1
        kept.append(file_path)

    if agent_id:
        _persist_ingest_event(agent_id, kept, kind="inject_py")
    print(f"[+] Ingested {count} Python file(s) into agent [{agent_id}] 🐍✅")


def ingest_files_to_memory(paths: List[str], agent_id: str, *, truncate_limit: int | None = 8000, source: str = "inject_mem") -> int:
    # Parallelize file reading (I/O bound); append to memory.jsonl sequentially
    from .memory import agent_dir as _agent_dir, _now_ts as _now
    from .memory import append_jsonl as _append
    lock = threading.Lock()
    out_count = 0
    results: List[tuple[str, str]] = []
    # Optional retrieval seeding from ingested files
    seed_retrieval = os.environ.get("QJSON_RETRIEVAL_INGEST", "0") == "1" or os.environ.get("QJSON_RETRIEVAL") == "1"
    try:
        retr_cap = int(os.environ.get("QJSON_RETRIEVAL_INGEST_CAP", "2000"))
    except Exception:
        retr_cap = 2000

    def _read(fp: str) -> tuple[str, str] | None:
        try:
            raw = read_file(fp)
            if isinstance(truncate_limit, int) and truncate_limit > 0 and len(raw) > truncate_limit:
                preview = raw[:truncate_limit] + "\n...[truncated]..."
            else:
                preview = raw
            return (fp, preview)
        except Exception:
            print(f"[inject_mem error] {fp}")
            return None

    max_workers = 4
    try:
        envw = os.environ.get("QJSON_INGEST_WORKERS")
        if envw:
            max_workers = max(1, int(envw))
    except Exception:
        pass

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = [ex.submit(_read, p) for p in paths]
        for fut in as_completed(futs):
            res = fut.result()
            if res is None:
                continue
            results.append(res)

    # Append sequentially to preserve ordering (best-effort)
    retr_batch: List[tuple[str, Dict[str, object], float | None]] = []
    for fp, preview in results:
        content = f"[inject_mem] {fp}\n\n" + preview
        with lock:
            _append(_agent_dir(agent_id) / "memory.jsonl", {"ts": _now(), "role": "system", "content": content, "meta": {"source": source, "path": fp}})
        out_count += 1
        if seed_retrieval:
            try:
                # Truncate preview for embedding cost control
                text_for_embed = preview[:max(128, retr_cap)] if isinstance(retr_cap, int) and retr_cap > 0 else preview
                retr_batch.append((text_for_embed, {"source": source, "path": fp}, None))
            except Exception:
                pass

    if seed_retrieval and retr_batch:
        try:
            from .retrieval import add_batch as _retr_add_batch
            _retr_add_batch(agent_id, retr_batch)
        except Exception:
            pass

    # Batch FMM insert once per ingestion to avoid heavy churn
    if out_count:
        try:
            fmm = PersistentFractalMemory(agent_id)
            fmm.insert(["ingest", source], {"ts": _now(), "files": paths})
        except Exception:
            pass
        _persist_ingest_event(agent_id, paths, kind=source)
    return out_count


def ingest_path_recursive(path: str, agent_id: str, *, truncate_limit: int | None = 8000) -> int:
    allowed = [".json", ".yson", ".ysonx", ".txt", ".md"]
    files = scan_path(path, allowed, recursive=True)
    if not files:
        print(f"[inject] No valid files at: {path}")
        return 0
    n = ingest_files_to_memory(files, agent_id, truncate_limit=truncate_limit, source="inject")
    print(f"[inject] Wrote {n} system message(s) from {path} into memory.jsonl")
    return n


def ingest_path_py_recursive(path: str, agent_id: str, *, truncate_limit: int | None = 8000) -> int:
    files = scan_path(path, [".py"], recursive=True)
    if not files:
        print(f"[inject_py] No Python files at: {path}")
        return 0
    n = ingest_files_to_memory(files, agent_id, truncate_limit=truncate_limit, source="inject_py")
    print(f"[inject_py] Wrote {n} system message(s) from {path} into memory.jsonl")
    return n


if __name__ == "__main__":
    # Example manual test
    ingest_path("./personas", "Lila-v∞")
    ingest_path_py("./scripts", "Lila-v∞")
    list_agent_memory("Lila-v∞")
