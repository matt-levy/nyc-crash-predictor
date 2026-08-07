export type RiskLevel = "low" | "moderate" | "high";

export interface MapPoint {
  camera_id: string;
  name: string;
  latitude: number;
  longitude: number;
  risk_score: number;
  risk_level: RiskLevel;
  historical_score: number;
  current_condition_score: number;
}

export interface MapRiskResponse {
  generated_at: string;
  area: string | null;
  duration_seconds: number;
  requested_camera_count: number;
  successful_camera_count: number;
  failed_camera_count: number;
  points: MapPoint[];
  failures: Array<{ camera_id: string; name: string; reason: string }>;
}

export interface NotGeneratedResponse {
  status: "not_generated";
  message: string;
}

export interface CameraRisk {
  camera: {
    id: string;
    name: string;
    latitude: number;
    longitude: number;
    area: string;
    is_online: boolean;
    image_url: string;
  };
  historical_risk: { risk_score: number; risk_level: RiskLevel };
  current_conditions: {
    vehicle_count: number;
    pedestrian_count: number;
    bicycle_count: number;
    truck_count: number;
    bus_count: number;
  };
  spatial_conflicts: { summary: { total_conflicts: number } };
  combined_risk: {
    score: number;
    level: RiskLevel;
    current_condition_score: number;
    factors: string[];
  };
}

export interface GeminiAnalysis {
  summary: string;
  key_factors: string[];
  historical_context: string;
  current_context: string;
  recommendation: string;
}

export interface ExplainedCameraRisk extends CameraRisk {
  ai_analysis: GeminiAnalysis;
}
