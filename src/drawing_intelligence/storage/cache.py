"""LLM response cache: one JSON file per request hash.

In ephemeral mode the cache lives inside the session workspace and is deleted with it; with
`DI_RETENTION=keep` it lives in `data/cache/` and is shared across sessions, so repeated runs on the same
drawing do not pay twice.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class ResponseCache:
    def __init__(self, folder: Path):
        self.folder = folder

    def _path(self, key: str) -> Path:
        return self.folder / f"{key}.json"

    def get(self, key: str) -> dict[str, Any] | None:
        p = self._path(key)
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

    def put(self, key: str, value: dict[str, Any]) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        self._path(key).write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
