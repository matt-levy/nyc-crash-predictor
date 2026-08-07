import asyncio

from app.models.risk import MapRiskResult


class MapRiskCache:
    """Process-local, ephemeral latest-result cache."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._latest: MapRiskResult | None = None

    async def get(self) -> MapRiskResult | None:
        async with self._lock:
            return self._latest.model_copy(deep=True) if self._latest else None

    async def set(self, result: MapRiskResult) -> None:
        async with self._lock:
            self._latest = result.model_copy(deep=True)

    async def clear(self) -> None:
        async with self._lock:
            self._latest = None


map_risk_cache = MapRiskCache()
