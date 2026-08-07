import type {
  CameraRisk,
  ExplainedCameraRisk,
  MapRiskResponse,
  NotGeneratedResponse
} from "../types/risk";

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) {
    const payload = await response.json().catch(() => null) as { detail?: string } | null;
    throw new Error(payload?.detail ?? `Request failed (${response.status})`);
  }
  return response.json() as Promise<T>;
}

export const getMapRisk = () =>
  request<MapRiskResponse | NotGeneratedResponse>("/map/risk");

export const refreshMapRisk = (area = "Manhattan", limit = 15) =>
  request("/map/refresh?" + new URLSearchParams({ area, limit: String(limit) }), {
    method: "POST"
  });

export const getCameraRisk = (cameraId: string) =>
  request<CameraRisk>(`/cameras/${encodeURIComponent(cameraId)}/risk`);

export const explainCameraRisk = (cameraId: string) =>
  request<ExplainedCameraRisk>(`/cameras/${encodeURIComponent(cameraId)}/risk/explain`);

export const cameraSnapshotUrl = (cameraId: string) =>
  `/cameras/${encodeURIComponent(cameraId)}/snapshot`;
