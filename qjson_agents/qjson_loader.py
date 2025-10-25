from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from .qjson_types import load_manifest, normalize_manifest


class QJSONLoader:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def load_agent(self) -> Dict[str, Any]:
        data = load_manifest(self.path)
        return normalize_manifest(data)

