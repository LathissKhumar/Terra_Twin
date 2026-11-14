import type { HealthResponse } from "@/types/api";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

export class ApiClientError extends Error {
  constructor(message: string, public status: number) {
    super(message);
    this.name = "ApiClientError";
  }
}
function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}
export function isHealthResponse(value: unknown): value is HealthResponse {
  if (!isRecord(value) || !isRecord(value.database) || !isRecord(value.system)) return false;
  const db = value.database;
  const sys = value.system;
  const nullableString = (v: unknown) => v === null || typeof v === "string";
  return (value.status === "healthy" || value.status === "degraded")
    && typeof value.app_name === "string" && typeof value.version === "string"
    && typeof sys.environment === "string" && typeof sys.debug === "boolean"
    && typeof sys.python_version === "string"
    && typeof db.connected === "boolean" && typeof db.postgis_available === "boolean"
    && nullableString(db.database_version) && nullableString(db.postgis_version)
    && nullableString(db.error)
    && (value.status === "healthy" ? db.connected && db.postgis_available : !(db.connected && db.postgis_available));
}
export const api = {
  async getHealth(signal?: AbortSignal): Promise<HealthResponse> {
    const controller = new AbortController();
    const abort = () => controller.abort();
    signal?.addEventListener("abort", abort, { once: true });
    if (signal?.aborted) controller.abort();
    const timer = setTimeout(abort, 5000);
    try {
      const response = await fetch(API_BASE_URL + "/health", {
        signal: controller.signal, cache: "no-store",
      });
      if (response.status !== 200 && response.status !== 503) {
        throw new ApiClientError("Backend request failed", response.status);
      }
      const data: unknown = await response.json();
      if (!isHealthResponse(data) || (response.status === 200) !== (data.status === "healthy")) {
        throw new ApiClientError("Invalid health response", response.status);
      }
      return data;
    } catch (error) {
      if (error instanceof ApiClientError) throw error;
      throw new ApiClientError("Backend unavailable or response unreadable", 0);
    } finally {
      clearTimeout(timer);
      signal?.removeEventListener("abort", abort);
    }
  },
};

