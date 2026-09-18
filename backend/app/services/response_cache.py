"""Lightweight response cache so near-identical explanations aren't regenerated.

Keyed by the caller (e.g. teaching: f"teach:{concept_id}:{cohort_key}").
In-memory for MVP; the interface is deliberately Redis-shaped (get/set/ttl)
so a RedisResponseCache can be swapped in behind `cache` without touching callers.
"""

from __future__ import annotations

import time


class InMemoryResponseCache:
    def __init__(self) -> None:
        self._store: dict[str, tuple[float, str]] = {}

    def get(self, key: str) -> str | None:
        item = self._store.get(key)
        if item is None:
            return None
        expires_at, value = item
        if expires_at < time.monotonic():
            del self._store[key]
            return None
        return value

    def set(self, key: str, value: str, ttl_seconds: int = 7 * 24 * 3600) -> None:
        self._store[key] = (time.monotonic() + ttl_seconds, value)


cache = InMemoryResponseCache()
