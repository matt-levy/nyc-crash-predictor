import { useCallback, useEffect, useState } from "react";

import { getMapRisk, refreshMapRisk } from "./api/riskApi";
import { CameraDetails } from "./components/CameraDetails";
import { RiskLegend } from "./components/RiskLegend";
import { RiskMap } from "./components/RiskMap";
import type { MapPoint, MapRiskResponse } from "./types/risk";

export default function App() {
  const [mapData, setMapData] = useState<MapRiskResponse | null>(null);
  const [notGenerated, setNotGenerated] = useState(false);
  const [selected, setSelected] = useState<MapPoint | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadMap = useCallback(async () => {
    const result = await getMapRisk();
    if ("status" in result) {
      setNotGenerated(true); setMapData(null);
    } else {
      setNotGenerated(false); setMapData(result);
    }
  }, []);

  useEffect(() => {
    loadMap().catch((reason: Error) => setError(reason.message)).finally(() => setLoading(false));
  }, [loadMap]);

  const refresh = async () => {
    setLoading(true); setError(null);
    try {
      await refreshMapRisk("Manhattan", 15);
      await loadMap();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Refresh failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="app-shell">
      <RiskMap
        points={mapData?.points ?? []}
        selectedId={selected?.camera_id}
        onSelect={setSelected}
      />
      <header className="map-header">
        <div className="brand-mark" />
        <h1>NYC Street Risk</h1>
      </header>
      <button className="refresh-button" onClick={refresh} disabled={loading}>
        <span className={loading ? "spinner" : "refresh-icon"} />
        {loading ? "Analyzing…" : "Refresh conditions"}
      </button>
      <RiskLegend />

      {!loading && notGenerated && !error && (
        <div className="empty-overlay">
          <p className="eyebrow">No current risk data</p>
          <h2>Analyze NYC street conditions</h2>
          <button onClick={refresh}>Analyze NYC</button>
        </div>
      )}
      {loading && !mapData && <div className="loading-overlay"><span className="spinner" /> Preparing map…</div>}
      {!loading && error && !mapData && (
        <div className="empty-overlay">
          <p className="eyebrow">Map request failed</p>
          <h2>{error}</h2>
          <button onClick={() => {
            setLoading(true); setError(null);
            loadMap().catch((reason: Error) => setError(reason.message)).finally(() => setLoading(false));
          }}>Retry</button>
        </div>
      )}
      {error && mapData && <div className="toast" role="alert">{error}<button onClick={() => setError(null)}>×</button></div>}
      {selected && <CameraDetails point={selected} onClose={() => setSelected(null)} />}

      <p className="disclaimer">
        Risk scores are relative indicators based on historical collision data and current visual conditions. They do not predict individual crashes.
      </p>
    </main>
  );
}
