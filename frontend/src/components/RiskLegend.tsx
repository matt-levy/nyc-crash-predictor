export function RiskLegend() {
  return (
    <div className="legend" aria-label="Street risk legend">
      <span>Street Risk</span>
      <div className="legend-scale" />
      <div className="legend-labels"><small>Low</small><small>Moderate</small><small>High</small></div>
    </div>
  );
}
