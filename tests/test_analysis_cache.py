import asyncio

from app.main import build_camera_risk, historical_for
from app.models.risk import Camera, CrashRecord, VisionObservation
from app.services.analysis_cache import camera_risk_cache, historical_risk_cache


CAMERA = Camera(
    id="cache-camera", name="Cache Camera", latitude=40.75, longitude=-73.98,
    area="Manhattan", is_online=True, image_url="https://example.com/image.jpg",
)
VISION = VisionObservation(
    image_width=352, image_height=240, vehicle_count=1, car_count=1,
    truck_count=0, bus_count=0, motorcycle_count=0, bicycle_count=0,
    pedestrian_count=1, detections=[],
)


def test_historical_results_are_cached(monkeypatch):
    asyncio.run(historical_risk_cache.clear())
    calls = 0

    async def crashes(**kwargs):
        nonlocal calls
        calls += 1
        return []

    monkeypatch.setattr("app.main.get_nearby_crashes", crashes)
    parameters = {
        "latitude": 40.751234, "longitude": -73.981234,
        "radius_meters": 250, "days": 365,
    }
    first = asyncio.run(historical_for(parameters))
    second = asyncio.run(historical_for(parameters))
    assert first == second
    assert calls == 1


def test_camera_result_cache_and_forced_refresh(monkeypatch):
    asyncio.run(camera_risk_cache.clear())
    asyncio.run(historical_risk_cache.clear())
    vision_calls = 0

    async def analyze(camera):
        nonlocal vision_calls
        vision_calls += 1
        return VISION

    async def crashes(**kwargs):
        return [CrashRecord(
            collision_id="1", timestamp="2026-08-01T00:00:00Z",
            latitude=CAMERA.latitude, longitude=CAMERA.longitude,
        )]

    monkeypatch.setattr("app.main.analyze_camera", analyze)
    monkeypatch.setattr("app.main.get_nearby_crashes", crashes)
    first = asyncio.run(build_camera_risk(CAMERA, 250, 365))
    second = asyncio.run(build_camera_risk(CAMERA, 250, 365))
    assert first == second
    assert vision_calls == 1

    asyncio.run(build_camera_risk(CAMERA, 250, 365, force_refresh=True))
    assert vision_calls == 2
