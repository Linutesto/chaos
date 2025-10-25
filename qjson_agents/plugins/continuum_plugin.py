from __future__ import annotations

import os
import tarfile
from pathlib import Path
from typing import Any, Callable, Dict

from qjson_agents.plugin_manager import Plugin


class ContinuumPlugin(Plugin):
    """Export/import agent state bundles for transfer across environments.

    Usage:
      /continuum export <AGENT_ID> path=<DIR>
      /continuum import <TAR.GZ> new_id=<ID>
    """

    def get_commands(self) -> Dict[str, Callable[..., Any]]:
        return {"/continuum": self.continuum}

    def continuum(self, *parts: str) -> str:
        if not parts:
            return "Usage: /continuum export <AGENT_ID> path=<DIR> | /continuum import <TAR.GZ> new_id=<ID>"
        sub = parts[0].lower()
        if sub == "export" and len(parts) >= 2:
            aid = parts[1]
            dest = None
            for p in parts[2:]:
                if p.startswith("path="):
                    dest = p.split("=",1)[1]
            if not dest:
                return "[continuum] path=<DIR> is required"
            from qjson_agents.memory import agent_dir
            src = agent_dir(aid)
            if not src.exists():
                return f"[continuum] agent state not found: {src}"
            outdir = Path(dest).expanduser().resolve()
            outdir.mkdir(parents=True, exist_ok=True)
            tar_path = outdir / f"{aid}.tar.gz"
            try:
                with tarfile.open(tar_path, "w:gz") as tar:
                    for name in ("manifest.json","memory.jsonl","events.jsonl","fmm.json"):
                        p = src / name
                        if p.exists():
                            tar.add(p, arcname=name)
                return f"[continuum] exported -> {tar_path}"
            except Exception as e:
                return f"[continuum] export error: {e}"
        if sub == "import" and len(parts) >= 2:
            arc = Path(parts[1]).expanduser().resolve()
            new_id = None
            for p in parts[2:]:
                if p.startswith("new_id="):
                    new_id = p.split("=",1)[1]
            if not new_id:
                return "[continuum] new_id=<ID> is required"
            from qjson_agents.memory import agent_dir, ensure_agent_dirs
            dst = agent_dir(new_id)
            ensure_agent_dirs(new_id)
            try:
                with tarfile.open(arc, "r:gz") as tar:
                    tar.extractall(path=dst)
                return f"[continuum] imported {arc.name} -> {dst}"
            except Exception as e:
                return f"[continuum] import error: {e}"
        return "[continuum] unknown subcommand"

