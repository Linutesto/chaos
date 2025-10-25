from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Iterator
from urllib import request, error


class OllamaClient:
    def __init__(self, base_url: Optional[str] = None, timeout: float = 120.0):
        self.base_url = base_url or os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
        self.timeout = timeout

    def _post_json(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        data = json.dumps(payload).encode("utf-8")
        req = request.Request(url, data=data, headers={"Content-Type": "application/json"})
        try:
            with request.urlopen(req, timeout=self.timeout) as resp:
                body = resp.read()
                return json.loads(body.decode("utf-8"))
        except error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="ignore") if hasattr(e, "read") else str(e)
            raise RuntimeError(f"Ollama HTTP {e.code}: {detail}") from e
        except error.URLError as e:
            raise RuntimeError(f"Ollama connection error: {e}") from e

    def _get_json(self, path: str) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        req = request.Request(url, method="GET")
        try:
            with request.urlopen(req, timeout=self.timeout) as resp:
                body = resp.read()
                return json.loads(body.decode("utf-8"))
        except error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="ignore") if hasattr(e, "read") else str(e)
            raise RuntimeError(f"Ollama HTTP {e.code}: {detail}") from e
        except error.URLError as e:
            raise RuntimeError(f"Ollama connection error: {e}") from e

    def chat(
        self,
        *,
        model: str,
        messages: List[Dict[str, str]],
        options: Optional[Dict[str, Any]] = None,
        stream: bool = False,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": stream,
        }
        if options:
            payload["options"] = options
        return self._post_json("/api/chat", payload)

    def chat_stream(
        self,
        *,
        model: str,
        messages: List[Dict[str, str]],
        options: Optional[Dict[str, Any]] = None,
    ) -> Iterator[str]:
        """Yield content chunks from Ollama streaming API (newline-delimited JSON)."""
        import json as _json
        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": True,
        }
        if options:
            payload["options"] = options
        url = f"{self.base_url}/api/chat"
        data = _json.dumps(payload).encode("utf-8")
        req = request.Request(url, data=data, headers={"Content-Type": "application/json"})
        try:
            with request.urlopen(req, timeout=self.timeout) as resp:
                buf = ""
                while True:
                    line = resp.readline()
                    if not line:
                        break
                    try:
                        obj = _json.loads(line.decode("utf-8"))
                    except Exception:
                        continue
                    # Typical shape: {"message": {"content": "..."}, "done": false}
                    msg = obj.get("message") or {}
                    content = msg.get("content") or obj.get("response")
                    if isinstance(content, str) and content:
                        if content.startswith(buf):
                            delta = content[len(buf):]
                            if delta:
                                yield delta
                            buf = content
                        else:
                            # fallback: yield whole content
                            yield content
                            buf = content
                    if obj.get("done") is True:
                        break
        except error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="ignore") if hasattr(e, "read") else str(e)
            raise RuntimeError(f"Ollama HTTP {e.code}: {detail}") from e
        except error.URLError as e:
            raise RuntimeError(f"Ollama connection error: {e}") from e

    def tags(self) -> List[Dict[str, Any]]:
        data = self._get_json("/api/tags")
        models = data.get("models", [])
        if not isinstance(models, list):
            return []
        return models
