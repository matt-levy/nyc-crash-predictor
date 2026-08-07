from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class CrashRecord(BaseModel):
    collision_id: str
    timestamp: datetime
    latitude: float
    longitude: float
    persons_injured: int = 0
    persons_killed: int = 0
    pedestrians_injured: int = 0
    cyclists_injured: int = 0
    motorists_injured: int = 0
    contributing_factors: list[str] = Field(default_factory=list)


class RiskMetrics(BaseModel):
    total_crashes: int
    injury_crashes: int
    fatal_crashes: int
    cyclist_injuries: int
    pedestrian_injuries: int
    crashes_last_30_days: int


class HistoricalRisk(BaseModel):
    latitude: float
    longitude: float
    radius_meters: int
    period_days: int
    risk_score: int = Field(ge=0, le=100)
    risk_level: Literal["low", "moderate", "high"]
    metrics: RiskMetrics
    explanation: list[str]


class VisionDetection(BaseModel):
    class_name: str
    confidence: float = Field(ge=0, le=1)
    x: float
    y: float
    width: float = Field(ge=0)
    height: float = Field(ge=0)


class VisionObservation(BaseModel):
    image_width: int = Field(gt=0)
    image_height: int = Field(gt=0)
    vehicle_count: int = Field(ge=0)
    car_count: int = Field(ge=0)
    truck_count: int = Field(ge=0)
    bus_count: int = Field(ge=0)
    motorcycle_count: int = Field(ge=0)
    bicycle_count: int = Field(ge=0)
    pedestrian_count: int = Field(ge=0)
    detections: list[VisionDetection] = Field(default_factory=list)


class ConflictEntity(BaseModel):
    class_name: str
    confidence: float = Field(ge=0, le=1)


class SpatialConflict(BaseModel):
    type: Literal[
        "pedestrian_vehicle_proximity",
        "bicycle_vehicle_proximity",
        "bicycle_large_vehicle_proximity",
        "dense_mixed_traffic",
    ]
    severity: Literal["low", "moderate", "high"]
    distance: float | None = Field(default=None, ge=0)
    entities: list[ConflictEntity]


class ConflictSummary(BaseModel):
    total_conflicts: int = Field(ge=0)
    pedestrian_vehicle_conflicts: int = Field(ge=0)
    bicycle_vehicle_conflicts: int = Field(ge=0)
    bicycle_large_vehicle_conflicts: int = Field(ge=0)
    dense_mixed_traffic_conflicts: int = Field(ge=0)


class SpatialConflictAnalysis(BaseModel):
    conflicts: list[SpatialConflict]
    summary: ConflictSummary


class Camera(BaseModel):
    id: str
    name: str
    latitude: float
    longitude: float
    area: str
    is_online: bool
    image_url: str


class RiskResponse(BaseModel):
    historical_risk: HistoricalRisk
    current_conditions: VisionObservation | None = None
    combined_risk: None = None


class CombinedRisk(BaseModel):
    """A relative street-risk indicator, not a crash probability."""

    score: int = Field(ge=0, le=100)
    level: Literal["low", "moderate", "high"]
    current_condition_score: int = Field(ge=0, le=100)
    factors: list[str]


class CameraRiskResponse(BaseModel):
    camera: Camera
    historical_risk: HistoricalRisk
    current_conditions: VisionObservation | None = None
    spatial_conflicts: SpatialConflictAnalysis
    combined_risk: CombinedRisk


class CameraAnalysisResponse(BaseModel):
    camera: Camera
    vision: VisionObservation
    spatial_conflicts: SpatialConflictAnalysis


class GeminiAnalysis(BaseModel):
    summary: str = Field(description="Concise summary of the street-risk indicators")
    key_factors: list[str] = Field(description="Strongest factors supported by the input")
    historical_context: str = Field(description="Historical evidence, kept separate from current observations")
    current_context: str = Field(description="Current camera evidence only")
    recommendation: str = Field(description="Cautious decision-support recommendation")


class CameraRiskExplanationResponse(CameraRiskResponse):
    ai_analysis: GeminiAnalysis


class MapRiskPoint(BaseModel):
    camera_id: str
    name: str
    latitude: float
    longitude: float
    risk_score: int = Field(ge=0, le=100)
    risk_level: Literal["low", "moderate", "high"]
    historical_score: int = Field(ge=0, le=100)
    current_condition_score: int = Field(ge=0, le=100)


class MapCameraFailure(BaseModel):
    camera_id: str
    name: str
    reason: str


class MapRiskResult(BaseModel):
    generated_at: datetime
    area: str | None
    duration_seconds: float = Field(ge=0)
    requested_camera_count: int = Field(ge=0)
    successful_camera_count: int = Field(ge=0)
    failed_camera_count: int = Field(ge=0)
    points: list[MapRiskPoint]
    failures: list[MapCameraFailure]


class MapRefreshResponse(BaseModel):
    status: Literal["completed"] = "completed"
    generated_at: datetime
    duration_seconds: float
    requested_camera_count: int
    successful_camera_count: int
    failed_camera_count: int


class MapNotGenerated(BaseModel):
    status: Literal["not_generated"] = "not_generated"
    message: str = "Run POST /map/refresh to generate risk-map data."
