import asyncio
import logging
from pathlib import Path
from time import perf_counter

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.models.risk import (
    Camera, CameraAnalysisResponse, CameraRiskExplanationResponse, CameraRiskResponse,
    CrashRecord, HistoricalRisk, MapNotGenerated, MapRefreshResponse, MapRiskResult,
    RiskResponse, VisionObservation,
)
from app.services.analysis_cache import camera_risk_cache, historical_risk_cache
from app.services.camera_service import (
    CameraCatalogError,
    CameraNotFoundError,
    CameraSnapshotError,
    fetch_snapshot,
    fetch_camera_catalog,
    get_camera,
    list_cameras,
)
from app.services.combined_risk import calculate_combined_risk
from app.services.gemini_service import (
    GeminiConfigurationError, GeminiResponseError, GeminiServiceError,
    GeminiTimeoutError, explain_risk, require_api_key as require_gemini_api_key,
)
from app.services.nyc_open_data import NYCOpenDataError, get_nearby_crashes
from app.services.map_cache import map_risk_cache
from app.services.map_service import generate_map_result
from app.services.risk_analysis import calculate_historical_risk
from app.services.spatial_analysis import analyze_spatial_conflicts
from app.services.vision_service import (
    VisionConfigurationError, VisionResponseError, VisionServiceError,
    VisionTimeoutError, analyze_image_url, require_api_key,
)

app = FastAPI(title="NYC Street Collision Risk API", version="0.1.0")
logger = logging.getLogger(__name__)
FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"


@app.middleware("http")
async def log_request_timing(request: Request, call_next):
    started = perf_counter()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    finally:
        logger.info(
            "http_request_completed method=%s path=%s status=%d duration_seconds=%.3f",
            request.method, request.url.path, status_code, perf_counter() - started,
        )


def search_parameters(
    latitude: float = Query(..., ge=-90, le=90),
    longitude: float = Query(..., ge=-180, le=180),
    radius_meters: int = Query(250, ge=1, le=5000),
    days: int = Query(365, ge=1, le=3650),
) -> dict:
    return locals()


async def crashes_for(parameters: dict) -> list[CrashRecord]:
    try:
        return await get_nearby_crashes(**parameters)
    except NYCOpenDataError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


def historical_cache_key(parameters: dict) -> tuple:
    return (
        round(parameters["latitude"], 6), round(parameters["longitude"], 6),
        parameters["radius_meters"], parameters["days"],
    )


async def historical_for(parameters: dict) -> HistoricalRisk:
    key = historical_cache_key(parameters)
    cached = await historical_risk_cache.get(key)
    if cached is not None:
        return cached
    crashes = await crashes_for(parameters)
    historical = calculate_historical_risk(crashes=crashes, **parameters)
    await historical_risk_cache.set(key, historical)
    return historical


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/crashes/nearby", response_model=list[CrashRecord])
async def nearby(parameters: dict = Depends(search_parameters)) -> list[CrashRecord]:
    return await crashes_for(parameters)


@app.get("/risk", response_model=RiskResponse)
async def risk(parameters: dict = Depends(search_parameters)) -> RiskResponse:
    historical = await historical_for(parameters)
    return RiskResponse(historical_risk=historical)


@app.get("/cameras", response_model=list[Camera])
async def cameras() -> list[Camera]:
    return list_cameras()


def camera_or_404(camera_id: str) -> Camera:
    try:
        return get_camera(camera_id)
    except CameraNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Camera not found") from exc


async def analyze_camera(selected: Camera) -> VisionObservation:
    if not selected.is_online:
        raise HTTPException(status_code=409, detail="Camera is offline")
    try:
        require_api_key()
        return await analyze_image_url(selected.image_url)
    except VisionConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except VisionTimeoutError as exc:
        raise HTTPException(status_code=504, detail=str(exc)) from exc
    except (VisionResponseError, VisionServiceError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/cameras/{camera_id}", response_model=Camera)
async def camera(camera_id: str) -> Camera:
    return camera_or_404(camera_id)


@app.get("/cameras/{camera_id}/snapshot")
async def camera_snapshot(camera_id: str) -> Response:
    selected = camera_or_404(camera_id)
    try:
        snapshot = await fetch_snapshot(selected)
    except CameraSnapshotError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return Response(
        content=snapshot.content,
        media_type=snapshot.content_type,
        headers={"Cache-Control": "no-store"},
    )


@app.get("/cameras/{camera_id}/analyze", response_model=CameraAnalysisResponse)
async def camera_analyze(camera_id: str) -> CameraAnalysisResponse:
    selected = camera_or_404(camera_id)
    vision = await analyze_camera(selected)
    spatial = analyze_spatial_conflicts(vision)
    return CameraAnalysisResponse(camera=selected, vision=vision, spatial_conflicts=spatial)


@app.get("/cameras/{camera_id}/risk", response_model=CameraRiskResponse)
async def camera_risk(
    camera_id: str,
    radius_meters: int = Query(250, ge=1, le=5000),
    days: int = Query(365, ge=1, le=3650),
) -> CameraRiskResponse:
    selected = camera_or_404(camera_id)
    return await build_camera_risk(selected, radius_meters, days)


async def build_camera_risk(
    selected: Camera, radius_meters: int, days: int, force_refresh: bool = False,
) -> CameraRiskResponse:
    cache_key = (selected.id, radius_meters, days)
    if not force_refresh:
        cached = await camera_risk_cache.get(cache_key)
        if cached is not None:
            return cached
    parameters = {
        "latitude": selected.latitude,
        "longitude": selected.longitude,
        "radius_meters": radius_meters,
        "days": days,
    }
    vision, historical = await asyncio.gather(
        analyze_camera(selected), historical_for(parameters)
    )
    spatial = analyze_spatial_conflicts(vision)
    combined = calculate_combined_risk(historical, vision, spatial)
    result = CameraRiskResponse(
        camera=selected,
        historical_risk=historical,
        current_conditions=vision,
        spatial_conflicts=spatial,
        combined_risk=combined,
    )
    await camera_risk_cache.set(cache_key, result)
    return result


@app.get(
    "/cameras/{camera_id}/risk/explain",
    response_model=CameraRiskExplanationResponse,
)
async def camera_risk_explain(
    camera_id: str,
    radius_meters: int = Query(250, ge=1, le=5000),
    days: int = Query(365, ge=1, le=3650),
) -> CameraRiskExplanationResponse:
    selected = camera_or_404(camera_id)
    try:
        require_gemini_api_key()
        risk_result = await build_camera_risk(selected, radius_meters, days)
        analysis = await explain_risk(risk_result)
    except GeminiConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except GeminiTimeoutError as exc:
        raise HTTPException(status_code=504, detail=str(exc)) from exc
    except (GeminiResponseError, GeminiServiceError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return CameraRiskExplanationResponse(
        **risk_result.model_dump(), ai_analysis=analysis
    )


@app.post("/map/refresh", response_model=MapRefreshResponse)
async def refresh_risk_map(
    area: str | None = Query("Manhattan", min_length=1, max_length=50),
    limit: int = Query(15, ge=1, le=50),
) -> MapRefreshResponse:
    try:
        cameras = await fetch_camera_catalog()
    except CameraCatalogError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    async def analyze(selected: Camera) -> CameraRiskResponse:
        return await build_camera_risk(
            selected, radius_meters=250, days=365, force_refresh=True
        )

    result = await generate_map_result(cameras, area, limit, analyze)
    await map_risk_cache.set(result)
    return MapRefreshResponse(
        generated_at=result.generated_at,
        duration_seconds=result.duration_seconds,
        requested_camera_count=result.requested_camera_count,
        successful_camera_count=result.successful_camera_count,
        failed_camera_count=result.failed_camera_count,
    )


@app.get("/map/risk", response_model=MapRiskResult | MapNotGenerated)
async def get_risk_map() -> MapRiskResult | MapNotGenerated:
    result = await map_risk_cache.get()
    return result if result is not None else MapNotGenerated()


# These routes remain last so every backend/API route takes precedence over the SPA.
if (FRONTEND_DIST / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="frontend-assets")


@app.get("/", include_in_schema=False)
async def frontend_index():
    index = FRONTEND_DIST / "index.html"
    if not index.is_file():
        raise HTTPException(status_code=404, detail="Frontend has not been built")
    return FileResponse(index)


@app.get("/{frontend_path:path}", include_in_schema=False)
async def frontend_fallback(frontend_path: str):
    api_prefixes = {
        "api", "health", "crashes", "risk", "cameras", "map",
        "docs", "redoc", "openapi.json",
    }
    if frontend_path.split("/", 1)[0] in api_prefixes:
        raise HTTPException(status_code=404, detail="Not found")
    index = FRONTEND_DIST / "index.html"
    if not index.is_file():
        raise HTTPException(status_code=404, detail="Frontend has not been built")
    return FileResponse(index)
