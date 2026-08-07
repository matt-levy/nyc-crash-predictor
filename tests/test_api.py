from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.main import app
from app.models.risk import CrashRecord, VisionDetection, VisionObservation
from app.services.vision_service import VisionResponseError, normalize_workflow_result


SAMPLE = CrashRecord(
    collision_id="123", timestamp=datetime.now(timezone.utc), latitude=40.794668,
    longitude=-73.971788, persons_injured=1, pedestrians_injured=1,
    contributing_factors=["Driver Inattention/Distraction"],
)


async def fake_crashes(**kwargs):
    return [SAMPLE]


VISION = VisionObservation(
    image_width=400, image_height=300,
    vehicle_count=2, car_count=1, truck_count=1, bus_count=0,
    motorcycle_count=0, bicycle_count=1, pedestrian_count=1,
    detections=[
        VisionDetection(class_name="car", confidence=.926, x=264, y=155, width=56, height=20),
        VisionDetection(class_name="truck", confidence=.8, x=10, y=20, width=30, height=40),
        VisionDetection(class_name="bicycle", confidence=.7, x=1, y=2, width=3, height=4),
        VisionDetection(class_name="person", confidence=.9, x=5, y=6, width=7, height=8),
    ],
)


async def fake_analyze(camera):
    return VISION


def test_health():
    assert TestClient(app).get("/health").json() == {"status": "ok"}


def test_nearby_and_risk(monkeypatch):
    monkeypatch.setattr("app.main.get_nearby_crashes", fake_crashes)
    client = TestClient(app)
    params = {"latitude": 40.794668, "longitude": -73.971788}
    nearby = client.get("/crashes/nearby", params=params)
    assert nearby.status_code == 200
    assert nearby.json()[0]["collision_id"] == "123"
    risk = client.get("/risk", params=params)
    assert risk.status_code == 200
    assert risk.json()["historical_risk"]["metrics"]["total_crashes"] == 1


def test_invalid_coordinates():
    response = TestClient(app).get("/risk", params={"latitude": 100, "longitude": -74})
    assert response.status_code == 422


def test_camera_catalog_and_risk(monkeypatch):
    monkeypatch.setattr("app.main.get_nearby_crashes", fake_crashes)
    monkeypatch.setattr("app.main.analyze_camera", fake_analyze)
    client = TestClient(app)
    cameras = client.get("/cameras")
    assert cameras.status_code == 200
    camera_id = cameras.json()[0]["id"]
    assert client.get(f"/cameras/{camera_id}").status_code == 200
    result = client.get(f"/cameras/{camera_id}/risk")
    assert result.status_code == 200
    assert result.json()["camera"]["name"] == "Broadway @ 96 St"
    assert result.json()["current_conditions"]["vehicle_count"] == 2
    assert result.json()["combined_risk"]["score"] >= 0


def test_unknown_camera():
    assert TestClient(app).get("/cameras/not-a-camera").status_code == 404


def test_explain_missing_gemini_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    camera_id = "769a2e94-5bbc-4a03-86a7-39d3a70213f7"
    response = TestClient(app).get(f"/cameras/{camera_id}/risk/explain")
    assert response.status_code == 503
    assert response.json()["detail"] == "GEMINI_API_KEY is not configured"


def test_camera_analyze(monkeypatch):
    monkeypatch.setattr("app.main.analyze_camera", fake_analyze)
    camera_id = "769a2e94-5bbc-4a03-86a7-39d3a70213f7"
    response = TestClient(app).get(f"/cameras/{camera_id}/analyze")
    assert response.status_code == 200
    assert response.json()["vision"]["pedestrian_count"] == 1
    assert "spatial_conflicts" in response.json()


def test_normalize_real_workflow_shape():
    raw = [{
        "output_image": {"type": "base64", "value": "ignored"},
        "model_id": "model/1", "inference_id": "inference-1",
        "vision_event_id": "event-1", "vision_events_error_status": False,
        "vision_events_message": "ok",
        "predictions": {"image": {"width": 400, "height": 300}, "predictions": [
            {"width": 56, "height": 20, "x": 264, "y": 155,
             "confidence": .926, "class_id": 3, "class": "car",
             "detection_id": "d1", "parent_id": "image"},
            {"width": 7, "height": 18, "x": 10, "y": 20,
             "confidence": .81, "class_id": 0, "class": "person",
             "detection_id": "d2", "parent_id": "image"},
        ]}
    }]
    normalized = normalize_workflow_result(raw)
    assert normalized.vehicle_count == 1
    assert normalized.car_count == 1
    assert normalized.pedestrian_count == 1
    assert len(normalized.detections) == 2


def test_empty_and_malformed_predictions():
    assert normalize_workflow_result([{"predictions": {"image": {"width": 400, "height": 300}, "predictions": []}}]).vehicle_count == 0
    try:
        normalize_workflow_result([{"predictions": {}}])
        assert False, "malformed output should fail"
    except VisionResponseError:
        pass
