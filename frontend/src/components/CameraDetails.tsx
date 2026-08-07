import { useEffect, useState } from "react";

import { cameraSnapshotUrl, explainCameraRisk, getCameraRisk } from "../api/riskApi";
import type { CameraRisk, GeminiAnalysis, MapPoint } from "../types/risk";

interface Props {
  point: MapPoint;
  onClose: () => void;
}

export function CameraDetails({ point, onClose }: Props) {
  const [detail, setDetail] = useState<CameraRisk | null>(null);
  const [analysis, setAnalysis] = useState<GeminiAnalysis | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [explaining, setExplaining] = useState(false);

  useEffect(() => {
    let active = true;
    setDetail(null); setAnalysis(null); setError(null); setLoading(true);
    getCameraRisk(point.camera_id)
      .then((result) => { if (active) setDetail(result); })
      .catch((reason: Error) => { if (active) setError(reason.message); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [point.camera_id]);

  const explain = async () => {
    setExplaining(true); setError(null);
    try {
      const result = await explainCameraRisk(point.camera_id);
      setAnalysis(result.ai_analysis);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Explanation failed");
    } finally {
      setExplaining(false);
    }
  };

  const conditions = detail?.current_conditions;
  const displayedScore = detail?.combined_risk.score ?? point.risk_score;
  const displayedLevel = detail?.combined_risk.level ?? point.risk_level;
  const historicalScore = detail?.historical_risk.risk_score ?? point.historical_score;
  const currentScore = detail?.combined_risk.current_condition_score ?? point.current_condition_score;
  return (
    <aside className="camera-panel" aria-label={`${point.name} details`}>
      <button className="close-button" onClick={onClose} aria-label="Close camera details">×</button>
      <img
        className="snapshot"
        src={cameraSnapshotUrl(point.camera_id)}
        alt={`Current traffic camera view at ${point.name}`}
      />
      <div className="panel-body">
        <p className="eyebrow">Live camera</p>
        <h2>{point.name}</h2>
        <div className="score-row">
          <div><strong>{displayedScore}</strong><span>Street Risk</span></div>
          <span className={`risk-pill ${displayedLevel}`}>{displayedLevel}</span>
        </div>
        <div className="score-breakdown">
          <span>Historical <b>{historicalScore}</b></span>
          <span>Current <b>{currentScore}</b></span>
        </div>

        {loading && <p className="muted">Analyzing current camera conditions…</p>}
        {conditions && (
          <div className="observations">
            <span><b>{conditions.vehicle_count}</b> vehicles</span>
            <span><b>{conditions.pedestrian_count}</b> pedestrians</span>
            <span><b>{conditions.bicycle_count}</b> bicycles</span>
            <span><b>{conditions.truck_count + conditions.bus_count}</b> large vehicles</span>
            <span><b>{detail.spatial_conflicts.summary.total_conflicts}</b> proximity indicators</span>
          </div>
        )}

        {!analysis && (
          <button className="explain-button" onClick={explain} disabled={explaining || loading}>
            {explaining ? "Explaining…" : "Explain risk"}
          </button>
        )}
        {analysis && (
          <section className="ai-analysis">
            <p className="eyebrow">AI explanation</p>
            <p>{analysis.summary}</p>
            <ul>{analysis.key_factors.map((factor) => <li key={factor}>{factor}</li>)}</ul>
            <p className="recommendation">{analysis.recommendation}</p>
          </section>
        )}
        {error && <p className="error">{error}</p>}
      </div>
    </aside>
  );
}
