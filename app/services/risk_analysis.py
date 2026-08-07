from datetime import datetime, timedelta, timezone

from app.models.risk import CrashRecord, HistoricalRisk, RiskMetrics


def calculate_historical_risk(
    crashes: list[CrashRecord], latitude: float, longitude: float, radius_meters: int, days: int
) -> HistoricalRisk:
    """Transparent score: crash volume 40, injury crashes 25, fatalities 15,
    vulnerable-user injuries 10, and recent (last 30 days) frequency 10.
    Each component is capped; thresholds scale by period length where appropriate.
    """
    recent_cutoff = datetime.now(timezone.utc) - timedelta(days=min(30, days))
    injury_crashes = sum(c.persons_injured > 0 for c in crashes)
    fatal_crashes = sum(c.persons_killed > 0 for c in crashes)
    cyclist_injuries = sum(c.cyclists_injured for c in crashes)
    pedestrian_injuries = sum(c.pedestrians_injured for c in crashes)
    recent = sum(c.timestamp >= recent_cutoff for c in crashes)
    year_factor = max(days / 365, 1 / 12)
    score = round(
        min(len(crashes) / (50 * year_factor), 1) * 40
        + min(injury_crashes / (15 * year_factor), 1) * 25
        + min(fatal_crashes, 1) * 15
        + min((cyclist_injuries + pedestrian_injuries) / (8 * year_factor), 1) * 10
        + min(recent / 8, 1) * 10
    )
    level = "low" if score < 34 else "moderate" if score < 67 else "high"
    explanations = []
    if not crashes:
        explanations.append("No reported crashes were found in the selected area and period")
    else:
        if len(crashes) >= 25 * year_factor:
            explanations.append("A notable number of crashes were reported in the selected area")
        if injury_crashes:
            explanations.append(f"{injury_crashes} crash(es) involved injuries")
        if fatal_crashes:
            explanations.append(f"{fatal_crashes} crash(es) involved fatalities")
        if cyclist_injuries + pedestrian_injuries:
            explanations.append("Reported crashes involved pedestrians or cyclists")
        if recent:
            explanations.append(f"{recent} crash(es) occurred in the most recent 30 days")
    metrics = RiskMetrics(
        total_crashes=len(crashes), injury_crashes=injury_crashes, fatal_crashes=fatal_crashes,
        cyclist_injuries=cyclist_injuries, pedestrian_injuries=pedestrian_injuries,
        crashes_last_30_days=recent,
    )
    return HistoricalRisk(
        latitude=latitude, longitude=longitude, radius_meters=radius_meters,
        period_days=days, risk_score=score, risk_level=level, metrics=metrics,
        explanation=explanations,
    )
