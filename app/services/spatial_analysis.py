from math import hypot

from app.models.risk import (
    ConflictEntity,
    ConflictSummary,
    SpatialConflict,
    SpatialConflictAnalysis,
    VisionDetection,
    VisionObservation,
)

DEFAULT_PROXIMITY_THRESHOLD = 0.15
VEHICLES = {"car", "truck", "bus", "motorcycle"}
VULNERABLE_ROAD_USERS = {"person", "bicycle"}
LARGE_VEHICLES = {"truck", "bus"}


def bounding_box_edges(detection: VisionDetection) -> tuple[float, float, float, float]:
    return (
        detection.x - detection.width / 2,
        detection.x + detection.width / 2,
        detection.y - detection.height / 2,
        detection.y + detection.height / 2,
    )


def center_distance(first: VisionDetection, second: VisionDetection) -> float:
    return hypot(first.x - second.x, first.y - second.y)


def normalized_center_distance(
    first: VisionDetection, second: VisionDetection, image_width: int, image_height: int
) -> float:
    return hypot((first.x - second.x) / image_width, (first.y - second.y) / image_height)


def intersection_area(first: VisionDetection, second: VisionDetection) -> float:
    first_left, first_right, first_top, first_bottom = bounding_box_edges(first)
    second_left, second_right, second_top, second_bottom = bounding_box_edges(second)
    width = max(0.0, min(first_right, second_right) - max(first_left, second_left))
    height = max(0.0, min(first_bottom, second_bottom) - max(first_top, second_top))
    return width * height


def _severity(distance: float, overlaps: bool) -> str:
    """Overlap or <=0.05 is high, <=0.10 moderate, and <=0.15 low."""
    if overlaps or distance <= 0.05:
        return "high"
    if distance <= 0.10:
        return "moderate"
    return "low"


def _entity(detection: VisionDetection) -> ConflictEntity:
    return ConflictEntity(
        class_name=detection.class_name, confidence=detection.confidence
    )


def analyze_spatial_conflicts(
    observation: VisionObservation,
    proximity_threshold: float = DEFAULT_PROXIMITY_THRESHOLD,
) -> SpatialConflictAnalysis:
    """Find single-image spatial indicators; these are not observed near-misses."""
    vehicles = [d for d in observation.detections if d.class_name.lower() in VEHICLES]
    vulnerable = [
        d for d in observation.detections if d.class_name.lower() in VULNERABLE_ROAD_USERS
    ]
    conflicts: list[SpatialConflict] = []

    for road_user in vulnerable:
        for vehicle in vehicles:
            distance = normalized_center_distance(
                road_user, vehicle, observation.image_width, observation.image_height
            )
            overlaps = intersection_area(road_user, vehicle) > 0
            if distance > proximity_threshold and not overlaps:
                continue
            road_user_class = road_user.class_name.lower()
            vehicle_class = vehicle.class_name.lower()
            common = {
                "severity": _severity(distance, overlaps),
                "distance": round(distance, 4),
                "entities": [_entity(road_user), _entity(vehicle)],
            }
            conflict_type = (
                "pedestrian_vehicle_proximity"
                if road_user_class == "person"
                else "bicycle_vehicle_proximity"
            )
            conflicts.append(SpatialConflict(type=conflict_type, **common))
            if road_user_class == "bicycle" and vehicle_class in LARGE_VEHICLES:
                conflicts.append(
                    SpatialConflict(type="bicycle_large_vehicle_proximity", **common)
                )

    proximity_count = sum(c.type != "bicycle_large_vehicle_proximity" for c in conflicts)
    if len(vehicles) >= 3 and len(vulnerable) >= 3 and proximity_count >= 3:
        conflicts.append(
            SpatialConflict(
                type="dense_mixed_traffic",
                severity="high" if proximity_count >= 6 else "moderate",
                distance=None,
                entities=[],
            )
        )

    def count(conflict_type: str) -> int:
        return sum(conflict.type == conflict_type for conflict in conflicts)

    summary = ConflictSummary(
        total_conflicts=len(conflicts),
        pedestrian_vehicle_conflicts=count("pedestrian_vehicle_proximity"),
        bicycle_vehicle_conflicts=count("bicycle_vehicle_proximity"),
        bicycle_large_vehicle_conflicts=count("bicycle_large_vehicle_proximity"),
        dense_mixed_traffic_conflicts=count("dense_mixed_traffic"),
    )
    return SpatialConflictAnalysis(conflicts=conflicts, summary=summary)
