import asyncio
from types import SimpleNamespace

import pytest

from app.models.risk import CameraRiskResponse
from app.services import gemini_service


def risk_response() -> CameraRiskResponse:
    return CameraRiskResponse.model_validate({
        "camera": {
            "id": "camera-1", "name": "Broadway @ 96 St", "latitude": 40.79,
            "longitude": -73.97, "area": "Manhattan", "is_online": True,
            "image_url": "https://example.com/current.jpg",
        },
        "historical_risk": {
            "latitude": 40.79, "longitude": -73.97, "radius_meters": 250,
            "period_days": 365, "risk_score": 75, "risk_level": "high",
            "metrics": {
                "total_crashes": 100, "injury_crashes": 20, "fatal_crashes": 1,
                "cyclist_injuries": 4, "pedestrian_injuries": 8,
                "crashes_last_30_days": 2,
            },
            "explanation": ["Historical evidence"],
        },
        "current_conditions": {
            "image_width": 352, "image_height": 240, "vehicle_count": 7,
            "car_count": 4, "truck_count": 2, "bus_count": 1,
            "motorcycle_count": 0, "bicycle_count": 1, "pedestrian_count": 9,
            "detections": [{
                "class_name": "person", "confidence": .9, "x": 10, "y": 20,
                "width": 5, "height": 10,
            }],
        },
        "spatial_conflicts": {
            "conflicts": [],
            "summary": {
                "total_conflicts": 3, "pedestrian_vehicle_conflicts": 2,
                "bicycle_vehicle_conflicts": 1,
                "bicycle_large_vehicle_conflicts": 0,
                "dense_mixed_traffic_conflicts": 0,
            },
        },
        "combined_risk": {
            "score": 81, "level": "high", "current_condition_score": 95,
            "factors": ["High historical collision frequency"],
        },
    })


def valid_analysis():
    return {
        "summary": "Elevated street-risk conditions are present.",
        "key_factors": ["High historical collision frequency"],
        "historical_context": "Historical records indicate elevated risk conditions.",
        "current_context": "Current observations show mixed road-user activity.",
        "recommendation": "Use increased caution and review current conditions.",
    }


def test_evidence_excludes_images_and_detections():
    evidence = gemini_service.build_evidence(risk_response())
    assert "image_url" not in evidence["camera"]
    assert "detections" not in evidence["current_conditions"]
    assert evidence["combined_risk"]["score"] == 81


def test_missing_api_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(gemini_service.GeminiConfigurationError):
        asyncio.run(gemini_service.explain_risk(risk_response()))


def test_structured_response(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(
        gemini_service, "_generate",
        lambda api_key, evidence: SimpleNamespace(parsed=valid_analysis(), text=None),
    )
    result = asyncio.run(gemini_service.explain_risk(risk_response()))
    assert result.summary.startswith("Elevated")
    assert risk_response().combined_risk.score == 81


def test_malformed_response(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(
        gemini_service, "_generate",
        lambda api_key, evidence: SimpleNamespace(parsed=None, text="not-json"),
    )
    with pytest.raises(gemini_service.GeminiResponseError):
        asyncio.run(gemini_service.explain_risk(risk_response()))


def test_api_failure(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    def fail(api_key, evidence):
        raise RuntimeError("service unavailable")

    monkeypatch.setattr(gemini_service, "_generate", fail)
    with pytest.raises(gemini_service.GeminiServiceError, match="request failed"):
        asyncio.run(gemini_service.explain_risk(risk_response()))


def test_error_details_are_sanitized():
    class ClientError(Exception):
        code = 403
        status = "PERMISSION_DENIED"
        message = "api_key=test-secret\nAccess denied for test-secret"

    status, reason, message = gemini_service._safe_error_details(
        ClientError(), "test-secret"
    )

    assert status == "403"
    assert reason == "PERMISSION_DENIED"
    assert "test-secret" not in message
    assert "[REDACTED]" in message
    assert "\n" not in message
