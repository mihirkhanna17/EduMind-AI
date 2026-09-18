"""Ephemeral server-side state (in-flight assessments, active thread pointers).

In-memory for MVP. The interface mirrors Redis string ops (get/set/delete with
JSON values) so a RedisSessionStore can replace `store` without touching callers.
"""

from __future__ import annotations

import json
import time


class InMemorySessionStore:
    def __init__(self) -> None:
        self._data: dict[str, tuple[float, str]] = {}

    def get(self, key: str) -> dict | None:
        item = self._data.get(key)
        if item is None:
            return None
        expires_at, payload = item
        if expires_at < time.monotonic():
            del self._data[key]
            return None
        return json.loads(payload)

    def set(self, key: str, value: dict, ttl_seconds: int = 24 * 3600) -> None:
        self._data[key] = (time.monotonic() + ttl_seconds, json.dumps(value))

    def delete(self, key: str) -> None:
        self._data.pop(key, None)


store = InMemorySessionStore()
