import { useEffect, useRef } from "react";
import maplibregl, { type GeoJSONSource, type Map as MapLibreMap } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";

import { MAP_STYLE_URL } from "../config";
import type { MapPoint } from "../types/risk";

interface Props {
  points: MapPoint[];
  selectedId?: string;
  onSelect: (point: MapPoint) => void;
}

const SOURCE_ID = "risk-points";

function toGeoJSON(points: MapPoint[]): GeoJSON.FeatureCollection {
  return {
    type: "FeatureCollection",
    features: points.map((point) => ({
      type: "Feature",
      geometry: { type: "Point", coordinates: [point.longitude, point.latitude] },
      properties: { ...point }
    }))
  };
}

export function RiskMap({ points, selectedId, onSelect }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const pointsRef = useRef(points);
  const selectRef = useRef(onSelect);

  pointsRef.current = points;
  selectRef.current = onSelect;

  useEffect(() => {
    if (!containerRef.current) return;
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: MAP_STYLE_URL,
      center: [-73.975, 40.758],
      zoom: 11.2,
      minZoom: 9
    });
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "bottom-right");
    map.on("load", () => {
      map.addSource(SOURCE_ID, { type: "geojson", data: toGeoJSON(pointsRef.current) });
      map.addLayer({
        id: "risk-heat",
        type: "heatmap",
        source: SOURCE_ID,
        maxzoom: 16,
        paint: {
          "heatmap-weight": ["interpolate", ["linear"], ["get", "risk_score"], 0, 0, 100, 1],
          "heatmap-intensity": ["interpolate", ["linear"], ["zoom"], 9, 0.8, 15, 2.5],
          "heatmap-radius": ["interpolate", ["linear"], ["zoom"], 9, 20, 15, 52],
          "heatmap-opacity": ["interpolate", ["linear"], ["zoom"], 11, 0.82, 16, 0.25],
          "heatmap-color": [
            "interpolate", ["linear"], ["heatmap-density"],
            0, "rgba(30, 99, 164, 0)", 0.18, "#42a5b3", 0.42, "#f2c14e",
            0.68, "#ef7b45", 1, "#b52d3a"
          ]
        }
      });
      map.addLayer({
        id: "risk-circles",
        type: "circle",
        source: SOURCE_ID,
        paint: {
          "circle-radius": ["interpolate", ["linear"], ["zoom"], 9, 3, 15, 7],
          "circle-color": ["interpolate", ["linear"], ["get", "risk_score"], 0, "#287a70", 50, "#e2a72e", 100, "#a52336"],
          "circle-stroke-color": "#ffffff",
          "circle-stroke-width": ["case", ["==", ["get", "camera_id"], selectedId ?? ""], 3, 1],
          "circle-opacity": 0.88
        }
      });
      map.on("mouseenter", "risk-circles", () => { map.getCanvas().style.cursor = "pointer"; });
      map.on("mouseleave", "risk-circles", () => { map.getCanvas().style.cursor = ""; });
      map.on("click", "risk-circles", (event) => {
        const id = event.features?.[0]?.properties?.camera_id as string | undefined;
        const point = pointsRef.current.find((item) => item.camera_id === id);
        if (point) selectRef.current(point);
      });
    });
    mapRef.current = map;
    return () => { map.remove(); mapRef.current = null; };
  }, []);

  useEffect(() => {
    const source = mapRef.current?.getSource(SOURCE_ID) as GeoJSONSource | undefined;
    source?.setData(toGeoJSON(points));
  }, [points]);

  useEffect(() => {
    if (mapRef.current?.getLayer("risk-circles")) {
      mapRef.current.setPaintProperty(
        "risk-circles", "circle-stroke-width",
        ["case", ["==", ["get", "camera_id"], selectedId ?? ""], 3, 1]
      );
    }
  }, [selectedId]);

  return <div ref={containerRef} className="map" aria-label="NYC street risk map" />;
}
