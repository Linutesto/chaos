from __future__ import annotations

import os
import subprocess as sp
from typing import Any, Callable, Dict, List
from pathlib import Path

from qjson_agents.plugin_manager import Plugin


def _git_root() -> Path:
    env_root = os.environ.get("QJSON_GIT_ROOT")
    if env_root:
        try:
            return Path(env_root).expanduser().resolve()
        except Exception:
            pass
    return Path.cwd().resolve()


def _run_git(args: List[str], *, timeout: float = 5.0) -> str:
    try:
        proc = sp.run(["git", *args], cwd=str(_git_root()), capture_output=True, text=True, timeout=timeout)
        out = (proc.stdout or "") + (proc.stderr or "")
        if len(out) > 16000:
            out = out[:16000]
        return out if out.strip() else f"(exit {proc.returncode})"
    except sp.TimeoutExpired:
        return f"[git] timeout after {timeout}s"
    except Exception as e:
        return f"[git] error: {e}"


class GitPlugin(Plugin):
    """Git repository helpers (read-only by default).

    Usage:
      /git_status [short=1]
      /git_log [N]
      /git_diff [PATH]

    Notes:
      - Working dir is QJSON_GIT_ROOT (defaults to CWD).
      - Write operations intentionally omitted unless explicitly added and gated.
    """

    def get_commands(self) -> Dict[str, Callable[..., Any]]:
        return {
            "/git_status": self.git_status,
            "/git_log": self.git_log,
            "/git_diff": self.git_diff,
        }

    def git_status(self, *parts: str) -> str:
        short = any(p.split("=",1)[0] == "short" and p.split("=",1)[1] in ("1","true","yes","on") for p in parts if "=" in p)
        if short:
            return _run_git(["status", "--porcelain=v1", "-b"])  # brief
        return _run_git(["status"])  # full

    def git_log(self, *parts: str) -> str:
        n = 10
        for p in parts:
            try:
                n = max(1, int(p))
            except Exception:
                if p.startswith("n="):
                    try:
                        n = max(1, int(p.split("=",1)[1]))
                    except Exception:
                        pass
        return _run_git(["--no-pager", "log", "--oneline", f"-n{n}"])

    def git_diff(self, *parts: str) -> str:
        target = parts[0] if parts else None
        if target:
            return _run_git(["--no-pager", "diff", "--stat", "--", target])
        return _run_git(["--no-pager", "diff", "--stat"]) 

