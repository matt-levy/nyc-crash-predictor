import asyncio
import json
import os
from typing import Any

from pydantic import ValidationError

from app.models.risk import CameraRiskResponse, GeminiAnalysis

GEMINI_MODEL = "gemini-3.6-flash"
SYSTEM_INSTRUCTION = """You explain structured evidence for a street-safety decision-support dashboard.
The deterministic street-risk score has already been calculated. Do not recalculate, change, or
reinterpret its numeric value. Never describe it as crash probability or claim a crash will occur.
Spatial proximity indicators from one still image are not confirmed near misses, collisions,
predicted collisions, or proof of dangerous driving. Do not invent facts absent from the input.
Clearly distinguish historical crash evidence from current camera observations. Identify the
strongest supported factors and remain concise. Use cautious terms such as elevated risk
conditions, risk indicators, and current street conditions."""


class GeminiServiceError(Exception):
    pass


class GeminiConfigurationError(GeminiServiceError):
    pass


class GeminiTimeoutError(GeminiServiceError):
    pass


class GeminiResponseError(GeminiServiceError):
    pass


def require_api_key() -> str:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise GeminiConfigurationError("GEMINI_API_KEY is not configured")
    return api_key


def build_evidence(risk: CameraRiskResponse) -> dict[str, Any]:
    """Return only normalized evidence; detections and images are intentionally excluded."""
    historical = risk.historical_risk
    current = risk.current_conditions
    conflicts = risk.spatial_conflicts.summary
    combined = risk.combined_risk
    if current is None:
        raise GeminiResponseError("Current camera conditions are unavailable")
    return {
        "camera": {
            "name": risk.camera.name,
            "latitude": risk.camera.latitude,
            "longitude": risk.camera.longitude,
        },
        "historical_risk": {
            "score": historical.risk_score,
            "level": historical.risk_level,
            "total_crashes": historical.metrics.total_crashes,
            "injury_crashes": historical.metrics.injury_crashes,
            "fatal_crashes": historical.metrics.fatal_crashes,
            "pedestrian_injuries": historical.metrics.pedestrian_injuries,
            "cyclist_injuries": historical.metrics.cyclist_injuries,
        },
        "current_conditions": {
            "vehicle_count": current.vehicle_count,
            "car_count": current.car_count,
            "truck_count": current.truck_count,
            "bus_count": current.bus_count,
            "motorcycle_count": current.motorcycle_count,
            "bicycle_count": current.bicycle_count,
            "pedestrian_count": current.pedestrian_count,
        },
        "spatial_conflicts": conflicts.model_dump(),
        "combined_risk": {
            "score": combined.score,
            "level": combined.level,
            "current_condition_score": combined.current_condition_score,
            "deterministic_factors": combined.factors,
        },
    }


def _generate(api_key: str, evidence: dict[str, Any]) -> Any:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)
    return client.models.generate_content(
        model=GEMINI_MODEL,
        contents="Explain this structured street-risk evidence:\n" + json.dumps(evidence),
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            response_mime_type="application/json",
            response_schema=GeminiAnalysis,
        ),
    )


def _parse_response(response: Any) -> GeminiAnalysis:
    try:
        if isinstance(response.parsed, GeminiAnalysis):
            return response.parsed
        if response.parsed is not None:
            return GeminiAnalysis.model_validate(response.parsed)
        return GeminiAnalysis.model_validate_json(response.text)
    except (AttributeError, TypeError, ValueError, ValidationError) as exc:
        raise GeminiResponseError("Gemini returned malformed structured output") from exc


async def explain_risk(risk: CameraRiskResponse) -> GeminiAnalysis:
    api_key = require_api_key()
    evidence = build_evidence(risk)
    try:
        response = await asyncio.to_thread(_generate, api_key, evidence)
    except Exception as exc:
        if "timeout" in type(exc).__name__.lower() or "timed out" in str(exc).lower():
            raise GeminiTimeoutError("Gemini request timed out") from exc
        raise GeminiServiceError("Gemini request failed") from exc
    return _parse_response(response)
