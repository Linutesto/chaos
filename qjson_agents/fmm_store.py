from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List
import atexit
import os
import time
import threading

from .memory import agent_dir


_FMM_CACHE: Dict[str, "PersistentFractalMemory"] = {}
_FMM_LOCK = threading.Lock()


class PersistentFractalMemory:
    """Per-agent persistent fractal memory with batched writes.

    - Instances are shared per agent_id within the current process.
    - Inserts mark the store dirty; persists every N inserts or when flush() is called.
    - Batch size and debounce can be tuned via env:
        QJSON_FMM_BATCH_SIZE (default 10)
        QJSON_FMM_FLUSH_SEC  (default 2.0)
    """

    def __new__(cls, agent_id: str):
        with _FMM_LOCK:
            inst = _FMM_CACHE.get(agent_id)
            if inst is not None:
                return inst
            inst = super().__new__(cls)
            _FMM_CACHE[agent_id] = inst
            return inst

    def __init__(self, agent_id: str):
        # Guard re-init for shared instance
        if getattr(self, "_initialized", False):
            return
        self._initialized = True
        self.agent_id = agent_id
        self.path = agent_dir(agent_id) / "fmm.json"
        self.tree: Dict[str, Any] = {}
        self._dirty = False
        self._since = time.time()
        self._inserts = 0
        self._batch_size = max(1, int(os.environ.get("QJSON_FMM_BATCH_SIZE", "10")))
        try:
            self._flush_sec = float(os.environ.get("QJSON_FMM_FLUSH_SEC", "2.0"))
        except Exception:
            self._flush_sec = 2.0
        if self.path.exists():
            try:
                self.tree = json.loads(self.path.read_text(encoding="utf-8"))
            except Exception:
                self.tree = {}

    def insert(self, topic_path: List[str], data: Dict[str, Any]) -> None:
        node = self.tree
        for part in topic_path:
            node = node.setdefault(part, {})
        node.setdefault("__data__", []).append(data)
        self._dirty = True
        self._inserts += 1
        # Time/size-based flush
        now = time.time()
        if self._inserts >= self._batch_size or (now - self._since) >= self._flush_sec:
            self.persist()
            self._since = now
            self._inserts = 0

    def persist(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self._dirty:
            return
        self.path.write_text(json.dumps(self.tree, ensure_ascii=False, indent=2), encoding="utf-8")
        self._dirty = False


def _flush_all_fmm() -> None:
    with _FMM_LOCK:
        for inst in list(_FMM_CACHE.values()):
            try:
                inst.persist()
            except Exception:
                pass


atexit.register(_flush_all_fmm)
