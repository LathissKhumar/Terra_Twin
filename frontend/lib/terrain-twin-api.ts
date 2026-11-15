import type { EarthReferenceDataset, TerrainTwinCandidate, TerrainTwinMetadata } from "@/types/terrain-twin";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

export class TerrainTwinApiError extends Error {
  constructor(message: string, public status: number) {
    super(message);
    this.name = "TerrainTwinApiError";
  }
}

async function parseError(response: Response): Promise<never> {
  let message = "Terrain Twin request failed";
  try {
    const body: unknown = await response.json();
    if (typeof body === "object" && body !== null) {
      const record = body as Record<string, unknown>;
      if (typeof record.detail === "string") message = record.detail;
      if (typeof record.error === "object" && record.error !== null) {
        const error = record.error as Record<string, unknown>;
        if (typeof error.message === "string") message = error.message;
      }
    }
  } catch {
    // Keep the stable generic error when the response body is not JSON.
  }
  throw new TerrainTwinApiError(message, response.status);
}

export const terrainTwinApi = {
  artifactUrl(path: string): string {
    if (path.startsWith("http://") || path.startsWith("https://")) {
      return path;
    }
    const cleanPath = path.startsWith("/") ? path : `/${path}`;
    try {
      if (API_BASE_URL.startsWith("http://") || API_BASE_URL.startsWith("https://")) {
        const apiOrigin = new URL(API_BASE_URL).origin;
        return new URL(cleanPath, apiOrigin).toString();
      }
    } catch {
      // fallback
    }
    if (typeof window !== "undefined") {
      return new URL(cleanPath, window.location.origin).toString();
    }
    return cleanPath;
  },

  async listCandidates(signal?: AbortSignal): Promise<TerrainTwinCandidate[]> {
    const response = await fetch(`${API_BASE_URL}/terrain-twins/candidates`, {
      cache: "no-store",
      signal,
    });
    if (!response.ok) return parseError(response);
    return response.json() as Promise<TerrainTwinCandidate[]>;
  },

  async listEarthReferences(signal?: AbortSignal): Promise<EarthReferenceDataset[]> {
    const response = await fetch(`${API_BASE_URL}/datasets?target_body=earth`, { cache: "no-store", signal });
    if (!response.ok) return parseError(response);
    const body = await response.json() as {
      datasets: Array<{ manifest: Omit<EarthReferenceDataset, "available" | "checksum_verified" | "surface_type" | "source_lineage_ids"> & { product_metadata?: Record<string, string | number | null> }; available: boolean; checksum_verified: boolean }>;
    };
    return body.datasets.map(({ manifest, available, checksum_verified }) => ({
      ...manifest,
      available,
      checksum_verified,
      surface_type: typeof manifest.product_metadata?.surface_type === "string" ? manifest.product_metadata.surface_type : null,
      source_lineage_ids: typeof manifest.product_metadata?.source_lineage_ids === "string"
        ? manifest.product_metadata.source_lineage_ids.split(",").map((value) => value.trim()).filter(Boolean)
        : [],
    }));
  },

  async create(candidateId: string, referenceDatasetId: string | null, signal?: AbortSignal): Promise<TerrainTwinMetadata> {
    const controller = new AbortController();
    const abort = () => controller.abort();
    signal?.addEventListener("abort", abort, { once: true });
    if (signal?.aborted) controller.abort();
    const timer = setTimeout(abort, 120_000);
    try {
      const response = await fetch(
        `${API_BASE_URL}/terrain-twins/candidates/${encodeURIComponent(candidateId)}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ max_vertices: 150_000, chunk_cells: 128, vertical_exaggeration: 1, reference_dataset_id: referenceDatasetId }),
          signal: controller.signal,
        },
      );
      if (!response.ok) return parseError(response);
      return response.json() as Promise<TerrainTwinMetadata>;
    } finally {
      clearTimeout(timer);
      signal?.removeEventListener("abort", abort);
    }
  },

  async getExisting(candidateId: string, referenceDatasetId: string | null, signal?: AbortSignal): Promise<TerrainTwinMetadata | null> {
    const query = referenceDatasetId ? `?reference_dataset_id=${encodeURIComponent(referenceDatasetId)}` : "";
    const response = await fetch(
      `${API_BASE_URL}/terrain-twins/candidates/${encodeURIComponent(candidateId)}/existing${query}`,
      { cache: "no-store", signal },
    );
    if (response.status === 404) return null;
    if (!response.ok) return parseError(response);
    return response.json() as Promise<TerrainTwinMetadata>;
  },
};
