from app.models.risk import VisionDetection, VisionObservation
from app.services.combined_risk import score_current_conditions
from app.services.spatial_analysis import (
    analyze_spatial_conflicts,
    bounding_box_edges,
    center_distance,
    intersection_area,
    normalized_center_distance,
)


def detection(class_name: str, x: float, y: float, width: float = 20, height: float = 20):
    return VisionDetection(
        class_name=class_name, confidence=.9, x=x, y=y, width=width, height=height
    )


def observation(detections):
    classes = [item.class_name for item in detections]
    return VisionObservation(
        image_width=400, image_height=300,
        vehicle_count=sum(name in {"car", "truck", "bus", "motorcycle"} for name in classes),
        car_count=classes.count("car"), truck_count=classes.count("truck"),
        bus_count=classes.count("bus"), motorcycle_count=classes.count("motorcycle"),
        bicycle_count=classes.count("bicycle"), pedestrian_count=classes.count("person"),
        detections=detections,
    )


def test_geometry_utilities():
    first = detection("person", 100, 100, 20, 40)
    second = detection("car", 120, 100, 30, 20)
    assert bounding_box_edges(first) == (90, 110, 80, 120)
    assert center_distance(first, second) == 20
    assert normalized_center_distance(first, second, 400, 300) == .05
    assert intersection_area(first, second) == 100


def test_person_far_from_vehicle():
    result = analyze_spatial_conflicts(
        observation([detection("person", 20, 20), detection("car", 380, 280)])
    )
    assert result.summary.total_conflicts == 0


def test_person_close_to_vehicle():
    result = analyze_spatial_conflicts(
        observation([detection("person", 100, 100), detection("car", 120, 100)])
    )
    assert result.summary.pedestrian_vehicle_conflicts == 1
    assert result.conflicts[0].severity == "high"


def test_bicycle_close_to_car():
    result = analyze_spatial_conflicts(
        observation([detection("bicycle", 100, 100), detection("car", 140, 100)])
    )
    assert result.summary.bicycle_vehicle_conflicts == 1
    assert result.summary.bicycle_large_vehicle_conflicts == 0


def test_bicycle_close_to_truck():
    result = analyze_spatial_conflicts(
        observation([detection("bicycle", 100, 100), detection("truck", 140, 100)])
    )
    assert result.summary.bicycle_vehicle_conflicts == 1
    assert result.summary.bicycle_large_vehicle_conflicts == 1


def test_multiple_vulnerable_road_user_conflicts_and_dense_traffic():
    items = [
        detection("person", 100, 100), detection("person", 110, 110),
        detection("bicycle", 120, 100), detection("car", 130, 100),
        detection("car", 140, 110), detection("truck", 150, 100),
    ]
    result = analyze_spatial_conflicts(observation(items))
    assert result.summary.pedestrian_vehicle_conflicts >= 2
    assert result.summary.bicycle_vehicle_conflicts >= 1
    assert result.summary.bicycle_large_vehicle_conflicts >= 1
    assert result.summary.dense_mixed_traffic_conflicts == 1


def test_no_detections():
    assert analyze_spatial_conflicts(observation([])).summary.total_conflicts == 0


def test_conflict_adjusted_score_stays_in_range():
    items = [detection("person", 100, 100) for _ in range(20)] + [
        detection("truck", 105, 100) for _ in range(20)
    ] + [detection("bicycle", 110, 100) for _ in range(20)]
    current = observation(items)
    spatial = analyze_spatial_conflicts(current)
    score = score_current_conditions(current, spatial)
    assert 0 <= score <= 100
    assert score == 100
