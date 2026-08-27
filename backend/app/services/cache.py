from __future__ import annotations

import hashlib
import json
import time
from collections import OrderedDict
from typing import Any

from app.config import settings


class TTLCache:
    """Small in-process LRU + TTL cache for search result pools.

    Deliberately in-process: this is an MVP running as a single API container.
    If the API is ever scaled to multiple replicas, swap this for Redis so the
    pool is shared and pagination stays consistent across replicas.
    """

    def __init__(self, *, max_entries: int = 256, ttl_seconds: int | None = None) -> None:
        self._store: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self._max_entries = max_entries
        self._ttl = ttl_seconds if ttl_seconds is not None else settings.search_cache_ttl_seconds

    def get(self, key: str) -> Any | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if expires_at < time.monotonic():
            self._store.pop(key, None)
            return None
        self._store.move_to_end(key)
        return value

    def set(self, key: str, value: Any) -> None:
        self._store[key] = (time.monotonic() + self._ttl, value)
        self._store.move_to_end(key)
        while len(self._store) > self._max_entries:
            self._store.popitem(last=False)

    def clear(self) -> None:
        self._store.clear()


def make_key(**parts: Any) -> str:
    payload = json.dumps(parts, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


search_pool_cache = TTLCache()
