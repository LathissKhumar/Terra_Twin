import type { EvidencePassport } from "@/types/evidence-passport";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

export async function fetchEvidencePassport(candidateId: string, signal?: AbortSignal): Promise<EvidencePassport> {
  const response = await fetch(`${API_BASE_URL}/candidates/${encodeURIComponent(candidateId)}/evidence-passport`, {
    cache: "no-store",
    signal,
  });
  if (!response.ok) {
    const payload: unknown = await response.json().catch(() => null);
    const detail = typeof payload === "object" && payload !== null && "detail" in payload
      ? String(payload.detail)
      : `Request failed (${response.status})`;
    throw new Error(detail);
  }
  return response.json() as Promise<EvidencePassport>;
}

export function evidenceExportUrl(candidateId: string, format: "json" | "pdf"): string {
  return `${API_BASE_URL}/candidates/${encodeURIComponent(candidateId)}/evidence-passport/export?format=${format}`;
}
