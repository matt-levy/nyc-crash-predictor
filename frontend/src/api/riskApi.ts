import type {
  CameraRisk,
  ExplainedCameraRisk,
  MapRiskResponse,
  NotGeneratedResponse
} from "../types/risk";

async function request<T>(url: string, init?: RequestInit, timeoutMs = 30_000): Promise<T> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
  let response: Response;
  try {
    response = await fetch(url, { ...init, signal: controller.signal });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new Error(`Request timed out after ${Math.round(timeoutMs / 1000)} seconds`);
    }
    throw error;
  } finally {
    window.clearTimeout(timeout);
  }
  if (!response.ok) {
    const payload = await response.json().catch(() => null) as { detail?: string } | null;
    throw new Error(payload?.detail ?? `Request failed (${response.status})`);
  }
  return response.json() as Promise<T>;
}

export const getMapRisk = () =>
  request<MapRiskResponse | NotGeneratedResponse>("/map/risk", undefined, 15_000);

export const refreshMapRisk = (area = "Manhattan", limit = 15) =>
  request("/map/refresh?" + new URLSearchParams({ area, limit: String(limit) }), {
    method: "POST"
  }, 300_000);

export const getCameraRisk = (cameraId: string) =>
  request<CameraRisk>(`/cameras/${encodeURIComponent(cameraId)}/risk`, undefined, 120_000);

export const explainCameraRisk = (cameraId: string) =>
  request<ExplainedCameraRisk>(`/cameras/${encodeURIComponent(cameraId)}/risk/explain`, undefined, 180_000);

export const cameraSnapshotUrl = (cameraId: string) =>
  `/cameras/${encodeURIComponent(cameraId)}/snapshot`;
