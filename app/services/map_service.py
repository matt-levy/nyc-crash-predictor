import asyncio
import logging
import os
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from time import perf_counter

from app.models.risk import (
    Camera, CameraRiskResponse, MapCameraFailure, MapRiskPoint, MapRiskResult,
)

logger = logging.getLogger(__name__)

CameraAnalyzer = Callable[[Camera], Awaitable[CameraRiskResponse]]


def configured_concurrency() -> int:
    try:
        value = int(os.getenv("MAP_ANALYSIS_CONCURRENCY", "5"))
    except ValueError:
        return 5
    return max(1, min(value, 20))


def select_cameras(cameras: list[Camera], area: str | None, limit: int) -> list[Camera]:
    requested_area = area.casefold() if area else None
    return [
        camera for camera in cameras
        if camera.is_online and (
            requested_area is None or camera.area.casefold() == requested_area
        )
    ][:limit]


def _failure_reason(exc: Exception) -> str:
    detail = getattr(exc, "detail", None)
    message = str(detail or exc or "analysis failed")
    return message[:200]


async def generate_map_result(
    cameras: list[Camera], area: str | None, limit: int, analyzer: CameraAnalyzer,
    concurrency: int | None = None,
) -> MapRiskResult:
    selected = select_cameras(cameras, area, limit)
    semaphore = asyncio.Semaphore(concurrency or configured_concurrency())
    started = perf_counter()

    async def analyze(camera: Camera):
        async with semaphore:
            camera_started = perf_counter()
            logger.info("map_camera_analysis_started camera_id=%s", camera.id)
            try:
                result = await analyzer(camera)
                logger.info(
                    "map_camera_analysis_completed camera_id=%s duration_seconds=%.3f risk_score=%d",
                    camera.id, perf_counter() - camera_started, result.combined_risk.score,
                )
                return MapRiskPoint(
                    camera_id=camera.id, name=camera.name,
                    latitude=camera.latitude, longitude=camera.longitude,
                    risk_score=result.combined_risk.score,
                    risk_level=result.combined_risk.level,
                    historical_score=result.historical_risk.risk_score,
                    current_condition_score=result.combined_risk.current_condition_score,
                )
            except Exception as exc:
                logger.warning(
                    "map_camera_analysis_failed camera_id=%s duration_seconds=%.3f error_type=%s reason=%s",
                    camera.id, perf_counter() - camera_started, type(exc).__name__,
                    _failure_reason(exc),
                )
                return MapCameraFailure(
                    camera_id=camera.id, name=camera.name,
                    reason=_failure_reason(exc),
                )

    outcomes = await asyncio.gather(*(analyze(camera) for camera in selected))
    points = [item for item in outcomes if isinstance(item, MapRiskPoint)]
    failures = [item for item in outcomes if isinstance(item, MapCameraFailure)]
    result = MapRiskResult(
        generated_at=datetime.now(timezone.utc), area=area,
        duration_seconds=round(perf_counter() - started, 3),
        requested_camera_count=len(selected), successful_camera_count=len(points),
        failed_camera_count=len(failures), points=points, failures=failures,
    )
    logger.info(
        "map_refresh_analysis_completed duration_seconds=%.3f requested=%d successful=%d failed=%d concurrency=%d",
        result.duration_seconds, len(selected), len(points), len(failures),
        concurrency or configured_concurrency(),
    )
    return result
