import asyncio

from fastapi.testclient import TestClient

from app.main import app
from app.models.risk import Camera, CameraRiskResponse
from app.services.map_cache import map_risk_cache
from app.services.map_service import configured_concurrency, generate_map_result, select_cameras


def camera(index: int, area: str = "Manhattan", online: bool = True) -> Camera:
    return Camera(
        id=f"camera-{index}", name=f"Camera {index}", latitude=40.7 + index / 1000,
        longitude=-73.9 - index / 1000, area=area, is_online=online,
        image_url=f"https://example.com/{index}.jpg",
    )


def risk(selected: Camera, score: int = 60) -> CameraRiskResponse:
    return CameraRiskResponse.model_validate({
        "camera": selected,
        "historical_risk": {
            "latitude": selected.latitude, "longitude": selected.longitude,
            "radius_meters": 250, "period_days": 365, "risk_score": 60,
            "risk_level": "moderate", "metrics": {
                "total_crashes": 10, "injury_crashes": 2, "fatal_crashes": 0,
                "cyclist_injuries": 0, "pedestrian_injuries": 1,
                "crashes_last_30_days": 0,
            }, "explanation": [],
        },
        "current_conditions": {
            "image_width": 352, "image_height": 240, "vehicle_count": 1,
            "car_count": 1, "truck_count": 0, "bus_count": 0,
            "motorcycle_count": 0, "bicycle_count": 0, "pedestrian_count": 1,
            "detections": [],
        },
        "spatial_conflicts": {"conflicts": [], "summary": {
            "total_conflicts": 0, "pedestrian_vehicle_conflicts": 0,
            "bicycle_vehicle_conflicts": 0, "bicycle_large_vehicle_conflicts": 0,
            "dense_mixed_traffic_conflicts": 0,
        }},
        "combined_risk": {
            "score": score, "level": "moderate", "current_condition_score": 6,
            "factors": [],
        },
    })


def clear_cache():
    asyncio.run(map_risk_cache.clear())


def test_get_before_refresh():
    clear_cache()
    response = TestClient(app).get("/map/risk")
    assert response.status_code == 200
    assert response.json()["status"] == "not_generated"


def test_area_filtering_limit_and_online_filter():
    cameras = [camera(1), camera(2, "Queens"), camera(3, online=False), camera(4)]
    selected = select_cameras(cameras, "manhattan", 1)
    assert [item.id for item in selected] == ["camera-1"]


def test_safe_maximum_limit():
    response = TestClient(app).post("/map/refresh?limit=51")
    assert response.status_code == 422


def test_concurrency_configuration(monkeypatch):
    monkeypatch.setenv("MAP_ANALYSIS_CONCURRENCY", "7")
    assert configured_concurrency() == 7
    monkeypatch.setenv("MAP_ANALYSIS_CONCURRENCY", "100")
    assert configured_concurrency() == 20
    monkeypatch.setenv("MAP_ANALYSIS_CONCURRENCY", "invalid")
    assert configured_concurrency() == 5


def test_bounded_concurrency():
    active = 0
    maximum = 0

    async def analyze(selected):
        nonlocal active, maximum
        active += 1
        maximum = max(maximum, active)
        await asyncio.sleep(.01)
        active -= 1
        return risk(selected)

    result = asyncio.run(generate_map_result(
        [camera(i) for i in range(8)], "Manhattan", 8, analyze, concurrency=3
    ))
    assert result.successful_camera_count == 8
    assert maximum == 3


def test_one_failure_and_all_failures():
    async def partly_fails(selected):
        if selected.id == "camera-2":
            raise RuntimeError("snapshot unavailable")
        return risk(selected)

    partial = asyncio.run(generate_map_result(
        [camera(1), camera(2)], "Manhattan", 2, partly_fails
    ))
    assert partial.successful_camera_count == 1
    assert partial.failed_camera_count == 1
    assert partial.failures[0].reason == "snapshot unavailable"

    async def always_fails(selected):
        raise RuntimeError("inference failed")

    failed = asyncio.run(generate_map_result(
        [camera(1), camera(2)], "Manhattan", 2, always_fails
    ))
    assert failed.successful_camera_count == 0
    assert failed.failed_camera_count == 2


def test_refresh_updates_cache_and_get_does_no_analysis(monkeypatch):
    clear_cache()
    calls = 0

    async def catalog():
        return [camera(1), camera(2), camera(3, "Queens")]

    async def analyze(selected, radius_meters, days):
        nonlocal calls
        calls += 1
        return risk(selected, 60 + calls)

    async def gemini_must_not_run(*args, **kwargs):
        raise AssertionError("Gemini must not run during map refresh")

    monkeypatch.setattr("app.main.fetch_camera_catalog", catalog)
    monkeypatch.setattr("app.main.build_camera_risk", analyze)
    monkeypatch.setattr("app.main.explain_risk", gemini_must_not_run)
    client = TestClient(app)
    refreshed = client.post("/map/refresh?area=Manhattan&limit=10")
    assert refreshed.status_code == 200
    assert refreshed.json()["requested_camera_count"] == 2
    assert refreshed.json()["successful_camera_count"] == 2
    assert calls == 2

    first = client.get("/map/risk")
    second = client.get("/map/risk")
    assert first.json() == second.json()
    assert len(first.json()["points"]) == 2
    assert calls == 2
