from __future__ import annotations

import os
from typing import Any, Callable, Dict, List

import requests

from qjson_agents.plugin_manager import Plugin


def _parse_headers(parts: List[str]) -> Dict[str, str]:
    h: Dict[str, str] = {}
    for p in parts:
        if p.startswith("h:") or p.startswith("H:"):
            kv = p.split(":", 1)[1]
            if "=" in kv:
                k, v = kv.split("=", 1)
                h[k.strip()] = v.strip()
    return h


class GenericAPIPlugin(Plugin):
    """Generic REST API calls (gated by QJSON_ALLOW_NET=1).

    Usage:
      /api_get <URL> [h:K=V ...] [timeout=N] [max=N]
      /api_post <URL> body='{"k":"v"}' [ct=application/json] [h:K=V ...] [timeout=N] [max=N]

    Notes:
      - Network calls require QJSON_ALLOW_NET=1
      - Timeout default 6s; response body preview capped by max (default 4000 chars)
    """

    def get_commands(self) -> Dict[str, Callable[..., Any]]:
        return {
            "/api_get": self.api_get,
            "/api_post": self.api_post,
        }

    def _allowed(self) -> bool:
        return os.environ.get("QJSON_ALLOW_NET", "0") == "1"

    def api_get(self, *parts: str) -> str:
        if not self._allowed():
            return "[api] network disabled. Set QJSON_ALLOW_NET=1 to enable."
        if not parts:
            return "Usage: /api_get <URL> [h:K=V ...] [timeout=N] [max=N]"
        url = parts[0]
        headers = _parse_headers(list(parts[1:]))
        timeout = 6.0
        maxc = 4000
        for p in parts[1:]:
            if p.startswith("timeout="):
                try:
                    timeout = float(p.split("=", 1)[1])
                except Exception:
                    pass
            elif p.startswith("max="):
                try:
                    maxc = max(256, int(p.split("=", 1)[1]))
                except Exception:
                    pass
        try:
            r = requests.get(url, headers=headers, timeout=timeout)
            txt = (r.text or "")
            if len(txt) > maxc:
                txt = txt[:maxc]
            return f"[api] GET {r.status_code} {r.reason}\n{txt}"
        except Exception as e:
            return f"[api] error: {e}"

    def api_post(self, *parts: str) -> str:
        if not self._allowed():
            return "[api] network disabled. Set QJSON_ALLOW_NET=1 to enable."
        if not parts:
            return "Usage: /api_post <URL> body='{}' [ct=application/json] [h:K=V ...] [timeout=N] [max=N]"
        url = parts[0]
        headers = _parse_headers(list(parts[1:]))
        body = ""
        ctype = None
        timeout = 6.0
        maxc = 4000
        for p in parts[1:]:
            if p.startswith("body="):
                body = p.split("=", 1)[1]
            elif p.startswith("ct="):
                ctype = p.split("=", 1)[1]
            elif p.startswith("timeout="):
                try:
                    timeout = float(p.split("=", 1)[1])
                except Exception:
                    pass
            elif p.startswith("max="):
                try:
                    maxc = max(256, int(p.split("=", 1)[1]))
                except Exception:
                    pass
        if ctype:
            headers.setdefault("Content-Type", ctype)
        try:
            r = requests.post(url, data=body.encode("utf-8"), headers=headers, timeout=timeout)
            txt = (r.text or "")
            if len(txt) > maxc:
                txt = txt[:maxc]
            return f"[api] POST {r.status_code} {r.reason}\n{txt}"
        except Exception as e:
            return f"[api] error: {e}"

