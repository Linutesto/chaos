from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable, Dict, List

from qjson_agents.plugin_manager import Plugin


def _parse_kv(parts: List[str]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for p in parts:
        if "=" in p:
            k, v = p.split("=", 1)
            out[k.strip()] = v.strip()
    return out


class SwarmForgePlugin(Plugin):
    """Design and deploy new specialized agents (personas).

    Usage:
      /forge create <ID> [role=... model=... goal=... plugins=a,b,c]
      /forge plugins <ID> set=a,b,c | add=a,b | del=a
      /forge goal <ID> <TEXT>
      /forge info <ID>

    Notes:
      - Writes manifest to state/<ID>/manifest.json
      - Stores suggested plugins under runtime.plugins (advisory)
    """

    def get_commands(self) -> Dict[str, Callable[..., Any]]:
        return {"/forge": self.forge}

    def _manifest_path(self, aid: str) -> Path:
        from qjson_agents.memory import agent_dir
        return agent_dir(aid) / "manifest.json"

    def _load_manifest(self, aid: str) -> Dict[str, Any] | None:
        p = self._manifest_path(aid)
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                return None
        return None

    def _save_manifest(self, aid: str, mf: Dict[str, Any]) -> None:
        from qjson_agents.memory import ensure_agent_dirs
        ensure_agent_dirs(aid)
        p = self._manifest_path(aid)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(mf, ensure_ascii=False, indent=2), encoding="utf-8")

    def _normalize(self, mf: Dict[str, Any]) -> Dict[str, Any]:
        try:
            from qjson_agents.qjson_types import normalize_manifest
            return normalize_manifest(mf)
        except Exception:
            return mf

    def forge(self, *parts: str) -> str:
        if not parts:
            return (
                "Usage: /forge create <ID> [role=... model=... goal=... plugins=a,b,c]\n"
                "       /forge plugins <ID> set=a,b,c | add=a,b | del=a\n"
                "       /forge goal <ID> <TEXT> | /forge info <ID>\n"
                "       /forge delegate <ID> <TASK...> | /forge report <ID>"
            )
        sub = parts[0].lower()
        if sub == "create" and len(parts) >= 2:
            aid = parts[1]
            opts = _parse_kv(list(parts[2:]))
            role = opts.get("role", "specialist")
            model = opts.get("model", os.environ.get("QJSON_DEFAULT_MODEL", "gemma3:4b"))
            goal = opts.get("goal", "")
            plugins = [s.strip() for s in (opts.get("plugins", "").split(",") if opts.get("plugins") else []) if s.strip()]
            mf: Dict[str, Any] = {
                "agent_id": aid,
                "origin": "SwarmForge",
                "creator": os.environ.get("USER") or os.environ.get("USERNAME") or "unknown",
                "roles": [role],
                "features": {},
                "core_directives": [
                    "Act safely and transparently; log actions.",
                    "Stay within assigned goal.",
                ],
                "runtime": {"model": model, "plugins": plugins},
            }
            if goal:
                mf.setdefault("goals", {})["global"] = goal
            mf = self._normalize(mf)
            self._save_manifest(aid, mf)
            return f"[forge] created agent '{aid}' with role='{role}', model='{model}', plugins={plugins or '[]'}"
        if sub == "plugins" and len(parts) >= 3:
            aid = parts[1]
            mf = self._load_manifest(aid)
            if not mf:
                return f"[forge] no manifest for {aid}; use /forge create {aid} first"
            opts = _parse_kv(list(parts[2:]))
            cur: List[str] = list((mf.get("runtime", {}) or {}).get("plugins", []) or [])
            if "set" in opts:
                cur = [s.strip() for s in opts["set"].split(",") if s.strip()]
            if "add" in opts:
                cur += [s.strip() for s in opts["add"].split(",") if s.strip()]
            if "del" in opts:
                dels = {s.strip() for s in opts["del"].split(",") if s.strip()}
                cur = [x for x in cur if x not in dels]
            # de-dup preserve order
            seen = set(); uniq: List[str] = []
            for x in cur:
                if x not in seen:
                    uniq.append(x); seen.add(x)
            mf.setdefault("runtime", {})["plugins"] = uniq
            self._save_manifest(aid, mf)
            return f"[forge] plugins for {aid}: {uniq}"
        if sub == "goal" and len(parts) >= 3:
            aid = parts[1]
            goal = " ".join(parts[2:]).strip()
            mf = self._load_manifest(aid)
            if not mf:
                return f"[forge] no manifest for {aid}"
            mf.setdefault("goals", {})["global"] = goal
            self._save_manifest(aid, mf)
            return f"[forge] goal set for {aid}: {goal}"
        if sub == "info" and len(parts) >= 2:
            aid = parts[1]
            mf = self._load_manifest(aid)
            if not mf:
                return f"[forge] no manifest for {aid}"
            runtime = mf.get("runtime", {})
            plugins = (runtime or {}).get("plugins", [])
            return json.dumps({
                "agent_id": mf.get("agent_id"),
                "roles": mf.get("roles"),
                "model": runtime.get("model"),
                "plugins": plugins,
                "goal": (mf.get("goals") or {}).get("global"),
            }, ensure_ascii=False, indent=2)
        if sub == "delegate" and len(parts) >= 3:
            target = parts[1]
            task = " ".join(parts[2:]).strip()
            if not task:
                return "[forge] provide a task to delegate"
            # Write to target's FMM and retrieval
            from qjson_agents.fmm_store import PersistentFractalMemory
            from qjson_agents.retrieval import add_memory
            fmm = PersistentFractalMemory(target)
            rec = {"ts": __import__("time").time(), "task": task, "from": os.environ.get("QJSON_AGENT_ID") or "SwarmLord"}
            fmm.insert(["tasks","queue"], rec); fmm.persist()
            try:
                add_memory(target, f"[task] {task}", {"source": "forge_delegate", "from": rec["from"]})
            except Exception:
                pass
            return f"[forge] delegated to {target}: {task}"
        if sub == "report" and len(parts) >= 2:
            target = parts[1]
            # Read queued tasks from FMM and last 3 retrieval notes
            try:
                from qjson_agents.fmm_store import PersistentFractalMemory
                fmm = PersistentFractalMemory(target)
                tasks = (fmm.tree.get("tasks", {}).get("queue", {}).get("__data__", []))
            except Exception:
                tasks = []
            lines: List[str] = [f"[forge] report for {target}"]
            lines.append(f"tasks_queued={len(tasks)}")
            if tasks:
                for t in tasks[-3:]:
                    lines.append(f"- {t.get('task')}")
            return "\n".join(lines)
        return "[forge] unknown subcommand"
