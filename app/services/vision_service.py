import asyncio
import logging
import os
from time import perf_counter
from typing import Any

from pydantic import ValidationError

from app.models.risk import VisionDetection, VisionObservation

logger = logging.getLogger("uvicorn.error")

ROBOFLOW_API_URL = "https://serverless.roboflow.com"
ROBOFLOW_WORKSPACE = "star-developer-4303"
ROBOFLOW_WORKFLOW_ID = "custom-workflow-2"
VEHICLE_CLASSES = {"car", "truck", "bus", "motorcycle"}


class VisionServiceError(Exception):
    pass


class VisionConfigurationError(VisionServiceError):
    pass


class VisionTimeoutError(VisionServiceError):
    pass


class VisionResponseError(VisionServiceError):
    pass


def require_api_key() -> str:
    api_key = os.getenv("ROBOFLOW_API_KEY")
    if not api_key:
        raise VisionConfigurationError("ROBOFLOW_API_KEY is not configured")
    return api_key


def normalize_workflow_result(result: Any) -> VisionObservation:
    try:
        first_result = result[0]
        prediction_output = first_result["predictions"]
        predictions = prediction_output["predictions"]
        image = prediction_output["image"]
        if not isinstance(first_result, dict) or not isinstance(predictions, list):
            raise TypeError
        detections = [
            VisionDetection(
                class_name=item["class"], confidence=item["confidence"],
                x=item["x"], y=item["y"], width=item["width"], height=item["height"],
            )
            for item in predictions
        ]
    except (IndexError, KeyError, TypeError, ValidationError) as exc:
        raise VisionResponseError("Roboflow returned malformed Workflow output") from exc

    class_counts = {name: 0 for name in VEHICLE_CLASSES}
    bicycle_count = 0
    pedestrian_count = 0
    for detection in detections:
        class_name = detection.class_name.lower()
        if class_name in class_counts:
            class_counts[class_name] += 1
        elif class_name == "bicycle":
            bicycle_count += 1
        elif class_name == "person":
            pedestrian_count += 1
    return VisionObservation(
        image_width=image["width"], image_height=image["height"],
        vehicle_count=sum(class_counts.values()), car_count=class_counts["car"],
        truck_count=class_counts["truck"], bus_count=class_counts["bus"],
        motorcycle_count=class_counts["motorcycle"], bicycle_count=bicycle_count,
        pedestrian_count=pedestrian_count, detections=detections,
    )


def _run_workflow(image_url: str, api_key: str) -> Any:
    from inference_sdk import InferenceHTTPClient

    client = InferenceHTTPClient(api_url=ROBOFLOW_API_URL, api_key=api_key)
    return client.run_workflow(
        workspace_name=ROBOFLOW_WORKSPACE,
        workflow_id=ROBOFLOW_WORKFLOW_ID,
        images={"image": image_url},
        use_cache=False,
    )


async def analyze_image_url(image_url: str) -> VisionObservation:
    api_key = require_api_key()
    started = perf_counter()
    logger.info("roboflow_workflow_started workflow_id=%s", ROBOFLOW_WORKFLOW_ID)
    try:
        result = await asyncio.to_thread(_run_workflow, image_url, api_key)
    except Exception as exc:
        logger.warning(
            "roboflow_workflow_failed duration_seconds=%.3f error_type=%s",
            perf_counter() - started, type(exc).__name__,
        )
        if "timeout" in type(exc).__name__.lower() or "timed out" in str(exc).lower():
            raise VisionTimeoutError("Roboflow Workflow request timed out") from exc
        raise VisionServiceError("Roboflow Workflow request failed") from exc
    observation = normalize_workflow_result(result)
    logger.info(
        "roboflow_workflow_completed duration_seconds=%.3f detection_count=%d",
        perf_counter() - started, len(observation.detections),
    )
    return observation
