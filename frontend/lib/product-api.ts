const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

export function resolveApiUrl(path: string, baseUrl: string = API): string {
  if (path.startsWith("http://") || path.startsWith("https://")) {
    return path;
  }
  const cleanPath = path.startsWith("/") ? path : `/${path}`;
  try {
    if (baseUrl.startsWith("http://") || baseUrl.startsWith("https://")) {
      return new URL(cleanPath, baseUrl).toString();
    }
  } catch {
    // fallback
  }
  if (typeof window !== "undefined") {
    return new URL(cleanPath, window.location.origin).toString();
  }
  return cleanPath;
}

export type DatasetEntry = { manifest: {
  id: string; target_body: "mars" | "moon" | "earth"; provider: string; product: string;
  version: string | null; bounds: [number, number, number, number]; width: number; height: number;
  pixel_resolution_x: number; pixel_resolution_y: number; resolution_unit: string;
  vertical_units: string; vertical_reference: string; product_metadata: Record<string, unknown>;
}; available: boolean; checksum_verified: boolean; raster_size_bytes: number | null };
export type DatasetCatalog = { adapters: Record<string, unknown>; datasets: DatasetEntry[]; storage_limit_bytes: number };
export type MissionCatalog = { mission_profiles: Array<Record<string, unknown>>; supported_bodies: string[]; reference_regions: Array<{
  region_id: string; label: string; body: string; source_dataset_ids: string[]; coverage_status: string;
  last_processed_center_lon_lat: [number, number] | null; coverage: Array<[number, number, number, number]>;
}>; earth_search_defaults?: Array<{ dataset_id: string; last_processed_center_lon_lat: [number, number] | null }>; unavailable_bodies: string[] };
export type Job = { job_id: string; status: "queued" | "running" | "succeeded" | "failed" | "interrupted";
  stage: string; progress_percent: number; created_at: string; updated_at: string; finished_at: string | null;
  result_run_id: string | null; failure_code: string | null; failure_message: string | null; reused_existing_job: boolean };
export type Candidate = { candidate_id: string; centroid_wgs84: [number, number]; geographic_boundary_wgs84: Array<[number, number]>;
  status: "eligible" | "insufficient_evidence"; ranking: number | null; weighted_distance: number | null;
  evidence_coverage: number; missing_features: string[]; feature_comparisons: Record<string, {
    units: string; normalized_distance: number | null; reference_median: number | null; candidate_median: number | null;
    reference_coverage: number; candidate_coverage: number; method: string
  }> };
export type CandidatePage = { items: Candidate[]; total: number; searched_boundary_wgs84: [number, number, number, number];
  generated_window_count: number; evaluated_window_count: number; eligible_candidate_count: number; ranked_candidate_count: number; warnings: string[] };

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API}${path}`, { cache: "no-store", ...init });
  if (!response.ok) {
    const payload: unknown = await response.json().catch(() => null);
    const message = typeof payload === "object" && payload !== null && "error" in payload
      ? String((payload as { error?: { message?: string } }).error?.message ?? response.statusText)
      : typeof payload === "object" && payload !== null && "detail" in payload
        ? String((payload as { detail?: string }).detail ?? response.statusText)
        : `${response.status} ${response.statusText}`;
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}
export const productApi = {
  url: API,
  missions: (signal?: AbortSignal) => request<MissionCatalog>("/missions", { signal }),
  datasets: (signal?: AbortSignal) => request<DatasetCatalog>("/datasets", { signal }),
  acquireMars: () => request<DatasetEntry["manifest"]>("/datasets/acquire/mola-jezero", { method: "POST" }),
  acquireHiRISEJezero: () => request<DatasetEntry["manifest"]>("/datasets/acquire/hirise-jezero", { method: "POST" }),
  acquireEarth: (latitude: number, longitude: number) => request<DatasetEntry["manifest"]>(`/datasets/acquire/copernicus-glo30?latitude=${latitude}&longitude=${longitude}`, { method: "POST" }),
  uploadDataset: (file: File, targetBody: "mars" | "moon" | "earth", values: { vertical_units: string; vertical_reference: string; provider: string; product: string; attribution: string }) => {
    const query = new URLSearchParams({ target_body: targetBody, ...values });
    return request<DatasetEntry["manifest"]>(`/datasets/upload?${query}`, { method: "POST", headers: { "X-Filename": file.name, "Content-Type": "image/tiff" }, body: file });
  },
  submit: (payload: Record<string, unknown>) => request<Job>("/discovery/jobs", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) }),
  job: (id: string, signal?: AbortSignal) => request<Job>(`/discovery/jobs/${encodeURIComponent(id)}`, { signal }),
  jobs: (signal?: AbortSignal) => request<{ items: Job[]; total: number }>("/discovery/jobs?limit=50", { signal }),
  candidates: (id: string, minCoverage: number, signal?: AbortSignal) => request<CandidatePage>(`/discovery/jobs/${encodeURIComponent(id)}/candidates?minimum_coverage=${minCoverage}&limit=500`, { signal }),
  comparison: (candidateId: string, signal?: AbortSignal) => request<Record<string, unknown>>(`/terrain/candidates/${encodeURIComponent(candidateId)}/comparison`, { signal }),
};
