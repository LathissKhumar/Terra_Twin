import type { HealthResponse } from "@/types/api";
// Synthetic service contract fixture, never included as scientific output.
export const healthy: HealthResponse = {
  status: "healthy", app_name: "TerraTwin", version: "0.1.0",
  system: { environment: "test", debug: false, python_version: "3.12" },
  database: { connected: true, database_version: "test", postgis_available: true,
    postgis_version: "test", error: null },
};

