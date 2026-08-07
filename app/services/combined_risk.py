from app.models.risk import (
    CombinedRisk, HistoricalRisk, SpatialConflictAnalysis, VisionObservation,
)


def risk_level(score: int) -> str:
    """Low is 0-33, moderate is 34-66, and high is 67-100."""
    if score < 34:
        return "low"
    if score < 67:
        return "moderate"
    return "high"


def score_current_conditions(
    observation: VisionObservation, spatial: SpatialConflictAnalysis | None = None
) -> int:
    """Score visible street interaction conditions from 0 to 100.

    Capped components:
    - all vehicles: 3 points each, up to 40
    - pedestrians: 3 points each, up to 30
    - bicycles: 6 points each, up to 12
    - trucks: 4 additional points each, up to 8
    - buses: 5 additional points each, up to 5
    - motorcycles: 5 additional points each, up to 5
    - pedestrian/vehicle proximity: 4 each, up to 12
    - bicycle/vehicle proximity: 6 each, up to 12
    - bicycle/large-vehicle proximity: 8 each, up to 16
    - dense mixed traffic: 10

    Type-specific points intentionally supplement the general vehicle count because
    these road users create different interaction and visibility conditions.
    """
    score = (
        min(observation.vehicle_count * 3, 40)
        + min(observation.pedestrian_count * 3, 30)
        + min(observation.bicycle_count * 6, 12)
        + min(observation.truck_count * 4, 8)
        + min(observation.bus_count * 5, 5)
        + min(observation.motorcycle_count * 5, 5)
    )
    if spatial is not None:
        summary = spatial.summary
        score += (
            min(summary.pedestrian_vehicle_conflicts * 4, 12)
            + min(summary.bicycle_vehicle_conflicts * 6, 12)
            + min(summary.bicycle_large_vehicle_conflicts * 8, 16)
            + min(summary.dense_mixed_traffic_conflicts, 1) * 10
        )
    return min(score, 100)


def calculate_combined_risk(
    historical: HistoricalRisk,
    observation: VisionObservation,
    spatial: SpatialConflictAnalysis | None = None,
) -> CombinedRisk:
    """Combine stable history (70%) with one current visual observation (30%)."""
    current_score = score_current_conditions(observation, spatial)
    score = max(0, min(round(historical.risk_score * 0.70 + current_score * 0.30), 100))

    factors: list[str] = []
    if historical.risk_score >= 67:
        factors.append("High historical collision frequency")
    elif historical.risk_score >= 34:
        factors.append("Moderate historical collision frequency")
    if observation.pedestrian_count >= 8:
        factors.append("High pedestrian activity")
    if observation.vehicle_count >= 10:
        factors.append("High vehicle activity")
    if observation.bicycle_count > 0:
        factors.append("Cyclists currently present")
    if observation.truck_count + observation.bus_count > 0:
        factors.append("Large vehicles currently present")
    if observation.motorcycle_count > 0:
        factors.append("Motorcycles currently present")
    if spatial is not None:
        summary = spatial.summary
        if summary.pedestrian_vehicle_conflicts:
            factors.append("Pedestrian and vehicle proximity detected")
        if summary.bicycle_vehicle_conflicts:
            factors.append("Cyclist and vehicle proximity detected")
        if summary.bicycle_large_vehicle_conflicts:
            factors.append("Cyclist near large vehicle")
        if summary.dense_mixed_traffic_conflicts:
            factors.append("Dense interaction between vehicles and vulnerable road users")
    if not factors:
        factors.append("No elevated historical or current-condition factors detected")

    return CombinedRisk(
        score=score,
        level=risk_level(score),
        current_condition_score=current_score,
        factors=factors,
    )
