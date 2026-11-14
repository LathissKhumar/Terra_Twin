/**
 * Core API response interfaces for TerraTwin.
 * Strictly mirrors backend Pydantic models.
 */

export interface SystemInfo {
  environment: string;
  debug: boolean;
  python_version: string;
}

export interface DatabaseHealth {
  connected: boolean;
  database_version: string | null;
  postgis_available: boolean;
  postgis_version: string | null;
  error: string | null;
}

export interface HealthResponse {
  status: "healthy" | "degraded";
  app_name: string;
  version: string;
  system: SystemInfo;
  database: DatabaseHealth;
}

export interface ApiError {
  error: {
    type: string;
    message: string;
    details: Record<string, unknown> | null;
    path: string;
  };
}

