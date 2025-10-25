from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable, Dict, List

from qjson_agents.plugin_manager import Plugin


def _roots() -> List[Path]:
    raw = os.environ.get("QJSON_FS_ROOTS", "").strip()
    roots: List[Path] = []
    if raw:
        for p in raw.split(os.pathsep):
            p = p.strip()
            if not p:
                continue
            try:
                roots.append(Path(os.path.expanduser(os.path.expandvars(p))).resolve())
            except Exception:
                continue
    if not roots:
        roots.append(Path.cwd().resolve())
    return roots


def _is_allowed(path: Path) -> bool:
    try:
        rp = path.resolve()
    except Exception:
        return False
    for r in _roots():
        try:
            rp.relative_to(r)
            return True
        except Exception:
            continue
    return False


class FileSystemPlugin(Plugin):
    """Local file system utilities.

    Usage:
      /fs_list [PATH] [glob=PAT] [max=N]
      /fs_read <PATH> [max_bytes=N]
      /fs_write <PATH> <TEXT|@file> [append=1]

    Safety:
      - Read/write restricted to QJSON_FS_ROOTS (os.pathsep-separated). Default: CWD.
      - Writes require QJSON_FS_WRITE=1. Max write length 100k chars.
    """

    def get_commands(self) -> Dict[str, Callable[..., Any]]:
        return {
            "/fs_list": self.fs_list,
            "/fs_read": self.fs_read,
            "/fs_write": self.fs_write,
        }

    def fs_list(self, *parts: str) -> str:
        base = Path(parts[0]).expanduser() if parts else Path(".")
        try:
            base = base.resolve()
        except Exception:
            return f"[fs] invalid path: {base}"
        if not _is_allowed(base):
            return f"[fs] path not allowed by QJSON_FS_ROOTS: {base}"
        glob_pat = None
        maxn = 200
        for p in parts[1:]:
            if p.startswith("glob="):
                glob_pat = p.split("=", 1)[1]
            elif p.startswith("max="):
                try:
                    maxn = max(1, int(p.split("=", 1)[1]))
                except Exception:
                    pass
        try:
            paths: List[Path] = []
            if base.is_file():
                paths = [base]
            else:
                if glob_pat:
                    paths = list(base.rglob(glob_pat))[:maxn]
                else:
                    paths = list(base.iterdir())[:maxn]
        except Exception as e:
            return f"[fs] error listing: {e}"
        lines: List[str] = []
        lines.append(f"[fs] Listing {base} (max={maxn}{', glob='+glob_pat if glob_pat else ''}) roots={','.join(str(r) for r in _roots())}")
        for p in paths:
            t = "f" if p.is_file() else ("d" if p.is_dir() else "?")
            try:
                sz = p.stat().st_size if p.is_file() else 0
            except Exception:
                sz = 0
            rel = p
            lines.append(f"{t} {rel} {sz}B")
        return "\n".join(lines)

    def fs_read(self, *parts: str) -> str:
        if not parts:
            return "Usage: /fs_read <PATH> [max_bytes=N]"
        path = Path(parts[0]).expanduser()
        try:
            path = path.resolve()
        except Exception:
            return f"[fs] invalid path: {path}"
        if not _is_allowed(path):
            return f"[fs] path not allowed by QJSON_FS_ROOTS: {path}"
        max_bytes = 64 * 1024
        for p in parts[1:]:
            if p.startswith("max_bytes="):
                try:
                    max_bytes = max(1, int(p.split("=", 1)[1]))
                except Exception:
                    pass
        if not path.exists() or not path.is_file():
            return f"[fs] not a file: {path}"
        try:
            data = path.read_bytes()[:max_bytes]
            try:
                txt = data.decode("utf-8", errors="ignore")
            except Exception:
                txt = data.decode("latin1", errors="ignore")
            preview = txt
            return f"[fs] read {len(data)} bytes from {path}\n{preview}"
        except Exception as e:
            return f"[fs] read error: {e}"

    def fs_write(self, *parts: str) -> str:
        if not parts:
            return "Usage: /fs_write <PATH> <TEXT|@file> [append=1]"
        if os.environ.get("QJSON_FS_WRITE", "0") != "1":
            return "[fs] writes disabled. Set QJSON_FS_WRITE=1 to enable."
        path = Path(parts[0]).expanduser()
        try:
            path = path.resolve()
        except Exception:
            return f"[fs] invalid path: {path}"
        if not _is_allowed(path):
            return f"[fs] path not allowed by QJSON_FS_ROOTS: {path}"
        if len(parts) < 2:
            return "Usage: /fs_write <PATH> <TEXT|@file> [append=1]"
        append = False
        for p in parts[2:]:
            if p.lower().startswith("append="):
                append = p.split("=", 1)[1] in ("1","true","yes","on")
        src = parts[1]
        if src.startswith("@"):
            # load from file
            sp = Path(src[1:]).expanduser()
            try:
                data = sp.read_text(encoding="utf-8", errors="ignore")
            except Exception as e:
                return f"[fs] could not read source {sp}: {e}"
        else:
            data = " ".join(parts[1:])
        if len(data) > 100_000:
            data = data[:100_000]
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            mode = "a" if append else "w"
            with path.open(mode, encoding="utf-8", errors="ignore") as fh:
                fh.write(data)
            return f"[fs] wrote {len(data)} chars to {path} (append={append})"
        except Exception as e:
            return f"[fs] write error: {e}"

