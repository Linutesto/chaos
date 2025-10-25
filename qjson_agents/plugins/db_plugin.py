from __future__ import annotations

import os
import sqlite3
from typing import Any, Callable, Dict, List
from pathlib import Path

from qjson_agents.plugin_manager import Plugin


class SQLitePlugin(Plugin):
    """SQLite database interaction (local file DBs).

    Usage:
      /sql_open <PATH> [ro=1]
      /sql_query <SQL> [max=N] [json=1]
      /sql_tables
      /sql_close

    Notes:
      - Defaults to read-only open (ro=1). Set ro=0 to open writable.
      - Row cap default: QJSON_SQL_MAX_ROWS (200)
      - No external dependencies; SQLite only.
    """

    def __init__(self, tools: Dict[str, Any] | None = None) -> None:
        super().__init__(tools)
        self._conn: sqlite3.Connection | None = None
        self._path: str | None = None

    def get_commands(self) -> Dict[str, Callable[..., Any]]:
        return {
            "/sql_open": self.sql_open,
            "/sql_query": self.sql_query,
            "/sql_tables": self.sql_tables,
            "/sql_close": self.sql_close,
        }

    def sql_open(self, *parts: str) -> str:
        if not parts:
            return "Usage: /sql_open <PATH> [ro=1]"
        path = Path(parts[0]).expanduser().resolve()
        ro = True
        for p in parts[1:]:
            if p.startswith("ro="):
                ro = p.split("=", 1)[1] in ("1","true","yes","on")
        try:
            if ro:
                uri = f"file:{path}?mode=ro"
                conn = sqlite3.connect(uri, uri=True)
            else:
                conn = sqlite3.connect(str(path))
            self._conn = conn
            self._path = str(path)
            return f"[sql] opened {path} ro={ro}"
        except Exception as e:
            return f"[sql] open error: {e}"

    def sql_close(self, *parts: str) -> str:
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None
            p = self._path or "(unknown)"
            self._path = None
            return f"[sql] closed {p}"
        return "[sql] no open connection"

    def _ensure(self) -> sqlite3.Connection | None:
        return self._conn

    def sql_tables(self, *parts: str) -> str:
        con = self._ensure()
        if not con:
            return "[sql] no open connection; use /sql_open <PATH>"
        try:
            rows = list(con.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;"))
            if not rows:
                return "[sql] no tables"
            names = [r[0] for r in rows]
            return "[sql] tables:\n" + "\n".join(f"- {n}" for n in names)
        except Exception as e:
            return f"[sql] error: {e}"

    def sql_query(self, *parts: str) -> str:
        if not parts:
            return "Usage: /sql_query <SQL> [max=N] [json=1]"
        con = self._ensure()
        if not con:
            return "[sql] no open connection; use /sql_open <PATH>"
        sql = parts[0]
        max_rows = 200
        as_json = False
        for p in parts[1:]:
            if p.startswith("max="):
                try:
                    max_rows = max(1, int(p.split("=", 1)[1]))
                except Exception:
                    pass
            elif p.startswith("json="):
                as_json = p.split("=", 1)[1] in ("1","true","yes","on")
        try:
            cur = con.execute(sql)
            cols = [d[0] for d in cur.description] if cur.description else []
            rows = cur.fetchmany(max_rows)
            if as_json:
                import json
                out_rows = [dict(zip(cols, r)) for r in rows]
                return json.dumps({"columns": cols, "rows": out_rows}, ensure_ascii=False, indent=2)
            # pretty text
            lines: List[str] = []
            lines.append("[sql] columns: " + ", ".join(cols))
            for r in rows:
                lines.append(" | ".join(str(x) for x in r))
            return "\n".join(lines)
        except Exception as e:
            return f"[sql] error: {e}"

