import asyncio
import copy
import logging
import os
from time import monotonic
from typing import Any

logger = logging.getLogger("uvicorn.error")


class TTLCache:
    """Small process-local TTL cache with copy-on-read/write semantics."""

    def __init__(self, ttl_env: str, default_ttl: int) -> None:
        self._ttl_env = ttl_env
        self._default_ttl = default_ttl
        self._items: dict[tuple[Any, ...], tuple[float, Any]] = {}
        self._lock = asyncio.Lock()

    def _ttl(self) -> int:
        try:
            return max(0, int(os.getenv(self._ttl_env, str(self._default_ttl))))
        except ValueError:
            return self._default_ttl

    async def get(self, key: tuple[Any, ...]) -> Any | None:
        async with self._lock:
            item = self._items.get(key)
            if item is None:
                logger.info("analysis_cache_miss cache=%s", self._ttl_env)
                return None
            expires_at, value = item
            if expires_at <= monotonic():
                self._items.pop(key, None)
                logger.info("analysis_cache_expired cache=%s", self._ttl_env)
                return None
            logger.info("analysis_cache_hit cache=%s", self._ttl_env)
            return copy.deepcopy(value)

    async def set(self, key: tuple[Any, ...], value: Any) -> None:
        ttl = self._ttl()
        if ttl == 0:
            return
        async with self._lock:
            self._items[key] = (monotonic() + ttl, copy.deepcopy(value))

    async def clear(self) -> None:
        async with self._lock:
            self._items.clear()


historical_risk_cache = TTLCache("HISTORICAL_RISK_CACHE_TTL_SECONDS", 21600)
camera_risk_cache = TTLCache("CAMERA_RISK_CACHE_TTL_SECONDS", 300)
