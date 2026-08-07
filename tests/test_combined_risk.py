from app.models.risk import HistoricalRisk, RiskMetrics, VisionObservation
from app.services.combined_risk import calculate_combined_risk, score_current_conditions


def observation(**overrides) -> VisionObservation:
    values = {
        "image_width": 400, "image_height": 300,
        "vehicle_count": 0, "car_count": 0, "truck_count": 0, "bus_count": 0,
        "motorcycle_count": 0, "bicycle_count": 0, "pedestrian_count": 0,
    }
    values.update(overrides)
    return VisionObservation(**values)


def historical(score: int) -> HistoricalRisk:
    return HistoricalRisk(
        latitude=40.79, longitude=-73.97, radius_meters=250, period_days=365,
        risk_score=score,
        risk_level="low" if score < 34 else "moderate" if score < 67 else "high",
        metrics=RiskMetrics(
            total_crashes=0, injury_crashes=0, fatal_crashes=0,
            cyclist_injuries=0, pedestrian_injuries=0, crashes_last_30_days=0,
        ),
        explanation=[],
    )


def test_empty_street():
    assert score_current_conditions(observation()) == 0


def test_low_activity():
    assert score_current_conditions(observation(vehicle_count=2, car_count=2, pedestrian_count=1)) == 9


def test_heavy_traffic():
    result = score_current_conditions(observation(vehicle_count=30, car_count=30))
    assert result == 40


def test_many_pedestrians():
    assert score_current_conditions(observation(pedestrian_count=20)) == 30


def test_cyclists_present():
    result = calculate_combined_risk(historical(50), observation(bicycle_count=2))
    assert result.current_condition_score == 12
    assert "Cyclists currently present" in result.factors


def test_large_vehicles_present():
    result = calculate_combined_risk(
        historical(50), observation(vehicle_count=3, truck_count=2, bus_count=1)
    )
    assert result.current_condition_score == 22
    assert "Large vehicles currently present" in result.factors


def test_score_never_exceeds_100():
    crowded = observation(
        vehicle_count=1000, car_count=500, truck_count=200, bus_count=100,
        motorcycle_count=200, bicycle_count=100, pedestrian_count=1000,
    )
    assert score_current_conditions(crowded) == 100
    combined = calculate_combined_risk(historical(100), crowded)
    assert combined.score == 100
    assert combined.level == "high"


def test_weighted_combined_score_and_threshold():
    current = observation(vehicle_count=10, car_count=10, pedestrian_count=6)
    result = calculate_combined_risk(historical(80), current)
    assert result.current_condition_score == 48
    assert result.score == 70
    assert result.level == "high"
