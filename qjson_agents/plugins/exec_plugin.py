from __future__ import annotations

import os
import shlex
import subprocess as sp
from pathlib import Path
from typing import Any, Callable, Dict

from qjson_agents.plugin_manager import Plugin


class CodeExecPlugin(Plugin):
    """Execute Python code in a subprocess (gated).

    Usage:
      /py <CODE...>
      /py @file.py

    Safety:
      - Requires QJSON_ALLOW_EXEC=1
      - Timeout controlled by QJSON_EXEC_TIMEOUT (default 5s)
      - Output capped to 16k
    """

    def get_commands(self) -> Dict[str, Callable[..., Any]]:
        return {"/py": self.py}

    def py(self, *parts: str) -> str:
        if os.environ.get("QJSON_ALLOW_EXEC", "0") != "1":
            return "[exec] disabled. Set QJSON_ALLOW_EXEC=1 to enable."
        if not parts:
            return "Usage: /py <CODE...> | /py @file.py"
        timeout = 5.0
        try:
            timeout = float(os.environ.get("QJSON_EXEC_TIMEOUT", "5"))
        except Exception:
            pass
        pybin = os.environ.get("QJSON_EXEC_PY", "python")
        code = None
        arg0 = parts[0]
        if arg0.startswith("@"):
            p = Path(arg0[1:]).expanduser()
            try:
                code = p.read_text(encoding="utf-8", errors="ignore")
            except Exception as e:
                return f"[exec] failed to read {p}: {e}"
        else:
            code = " ".join(parts)
        try:
            proc = sp.run([pybin, "-c", code], capture_output=True, text=True, timeout=timeout)
            out = (proc.stdout or "") + (proc.stderr or "")
            if len(out) > 16_000:
                out = out[:16_000]
            return f"[py] exit={proc.returncode}\n{out}"
        except sp.TimeoutExpired:
            return f"[py] timeout after {timeout}s"
        except Exception as e:
            return f"[py] error: {e}"

