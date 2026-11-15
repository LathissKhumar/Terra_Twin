"use client";

/* Images are dynamic API artifacts; Next's optimizer cannot access the local API origin at build time. */
/* eslint-disable @next/next/no-img-element */

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { TerrainMeshViewer } from "@/features/terrain-twin/terrain-mesh-viewer";
import { terrainTwinApi } from "@/lib/terrain-twin-api";
import type { EarthReferenceDataset, TerrainTwinCandidate, TerrainTwinMetadata } from "@/types/terrain-twin";

function formatCoordinate(value: number, suffix: string): string {
  return `${Math.abs(value).toFixed(5)}°${value < 0 ? (suffix === "N" ? "S" : "W") : suffix}`;
}

export function TerrainTwinWorkbench() {
  const [candidates, setCandidates] = useState<TerrainTwinCandidate[]>([]);
  const [candidateId, setCandidateId] = useState("");
  const [referenceDatasets, setReferenceDatasets] = useState<EarthReferenceDataset[]>([]);
  const [referenceDatasetId, setReferenceDatasetId] = useState("");
  const [metadata, setMetadata] = useState<TerrainTwinMetadata | null>(null);
  const [loadingCandidates, setLoadingCandidates] = useState(true);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [viewerError, setViewerError] = useState<string | null>(null);
  const [colorMode, setColorMode] = useState<"elevation" | "slope">("elevation");
  const [wireframe, setWireframe] = useState(false);
  const [displayVerticalExaggeration, setDisplayVerticalExaggeration] = useState(6);
  const [resetToken, setResetToken] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    Promise.all([terrainTwinApi.listCandidates(controller.signal), terrainTwinApi.listEarthReferences(controller.signal)])
      .then(([items, references]) => {
        setCandidates(items);
        setReferenceDatasets(references.filter((item) => item.available && item.checksum_verified));
        const firstCandidate = items.find((item) => item.discovery_status === "eligible") ?? items[0];
        if (firstCandidate) setCandidateId(firstCandidate.candidate_id);
        const source = references.find((item) => item.id === firstCandidate?.source_dataset_id);
        const independent = references.find((item) => item.available && item.checksum_verified
          && item.id !== source?.id && item.surface_type === "bare_earth_dtm"
          && item.vertical_units === source?.vertical_units
          && item.vertical_reference === source?.vertical_reference
          && !item.source_lineage_ids.some((lineage) => source?.source_lineage_ids.includes(lineage)));
        if (independent) setReferenceDatasetId(independent.id);
      })
      .catch(() => {
        if (!controller.signal.aborted) setError("Candidate records could not be loaded from the backend.");
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoadingCandidates(false);
      });
    return () => controller.abort();
  }, []);

  const selectedCandidate = useMemo(
    () => candidates.find((candidate) => candidate.candidate_id === candidateId) ?? null,
    [candidates, candidateId],
  );
  const sourceDataset = referenceDatasets.find((dataset) => dataset.id === selectedCandidate?.source_dataset_id);
  const compatibleReferences = referenceDatasets.filter((dataset) => dataset.id !== sourceDataset?.id
    && dataset.surface_type === "bare_earth_dtm"
    && dataset.vertical_units === sourceDataset?.vertical_units
    && dataset.vertical_reference === sourceDataset?.vertical_reference
    && !dataset.source_lineage_ids.some((lineage) => sourceDataset?.source_lineage_ids.includes(lineage)));

  useEffect(() => {
    if (!selectedCandidate || !referenceDatasetId) return;
    const controller = new AbortController();
    terrainTwinApi.getExisting(selectedCandidate.candidate_id, referenceDatasetId, controller.signal)
      .then((existing) => { if (existing) setMetadata(existing); })
      .catch((reason) => {
        if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "Stored terrain twin lookup failed.");
      });
    return () => controller.abort();
  }, [selectedCandidate, referenceDatasetId]);

  async function buildTerrainTwin() {
    if (!selectedCandidate) return;
    setCreating(true);
    setError(null);
    setViewerError(null);
    setMetadata(null);
    try {
      const result = await terrainTwinApi.create(selectedCandidate.candidate_id, referenceDatasetId || null);
      setMetadata(result);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Terrain mesh generation failed.");
    } finally {
      setCreating(false);
    }
  }

  const onLoaded = useCallback(() => setViewerError(null), []);
  const onViewerError = useCallback((message: string) => setViewerError(message), []);

  return (
    <section className="space-y-6" aria-labelledby="terrain-twin-title">
      <header>
        <p className="font-mono text-xs uppercase tracking-[0.2em] text-cyan-300">Phase 6 · DEM reconstruction</p>
        <h1 id="terrain-twin-title" className="mt-2 text-3xl font-semibold text-slate-50">Terrain Twin</h1>
        <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-300">
          Reconstruct a selected Earth search window from its checksummed source DEM and optionally compare the exported mesh with a separately acquired reference DEM.
          Candidate evidence status remains attached to the mesh; visualization does not upgrade an
          insufficient-evidence window into an analogue finding.
        </p>
      </header>

      <div className="grid gap-4 rounded-lg border border-slate-700 bg-slate-900/70 p-4 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto] md:items-end">
        <label className="block text-sm text-slate-200">
          <span className="mb-2 block font-medium">Ranked candidate with complete DEM support</span>
          <select
            className="w-full rounded-md border border-slate-600 bg-slate-950 px-3 py-2 text-sm text-slate-100"
            value={candidateId}
            onChange={(event) => { setCandidateId(event.target.value); setMetadata(null); setError(null); }}
            disabled={loadingCandidates || candidates.length === 0}
            aria-label="Select an actual Earth search candidate"
          >
            {loadingCandidates && <option value="">Loading candidate records…</option>}
            {!loadingCandidates && candidates.length === 0 && <option value="">No candidate records</option>}
            {candidates.map((candidate) => (
              <option key={candidate.candidate_id} value={candidate.candidate_id}>
                {candidate.candidate_id} · {candidate.discovery_status === "eligible" ? `rank #${candidate.ranking ?? "—"} · distance ${candidate.weighted_distance?.toFixed(3) ?? "—"}` : "insufficient evidence · unranked"}
              </option>
            ))}
          </select>
          {selectedCandidate && (
            <span className="mt-2 block text-xs text-slate-400">
              {selectedCandidate.source_product} · {formatCoordinate(selectedCandidate.centroid_wgs84[0], "E")} · {formatCoordinate(selectedCandidate.centroid_wgs84[1], "N")} · run {selectedCandidate.discovery_run_id}
            </span>
          )}
        </label>
        <label className="block text-sm text-slate-200">
          <span className="mb-2 block font-medium">Independent validation reference</span>
          <select
            className="w-full rounded-md border border-slate-600 bg-slate-950 px-3 py-2 text-sm text-slate-100"
            value={referenceDatasetId}
            onChange={(event) => { setReferenceDatasetId(event.target.value); setMetadata(null); }}
            aria-label="Select an independent Earth elevation reference"
          >
            <option value="">Visualization only · no independent reference</option>
            {compatibleReferences.map((dataset) => (
              <option key={dataset.id} value={dataset.id}>{dataset.product} · {dataset.version ?? "version unavailable"} · {dataset.vertical_reference}</option>
            ))}
          </select>
          <span className="mt-2 block text-xs text-slate-400">Only distinct bare-earth DEMs with matching vertical units and reference are selectable. The backend also checks lineage and spatial support.</span>
        </label>
        <button
          className="rounded-md bg-cyan-400 px-4 py-2 text-sm font-semibold text-slate-950 transition hover:bg-cyan-300 disabled:cursor-not-allowed disabled:opacity-50"
          onClick={buildTerrainTwin}
          disabled={!selectedCandidate || creating}
        >
          {creating ? "Reconstructing DEM…" : metadata ? "Rebuild terrain mesh" : "Build terrain mesh"}
        </button>
      </div>

      {selectedCandidate && (
        <section className="rounded-lg border border-cyan-900/70 bg-slate-900/70 p-4" aria-label="Discovery comparison evidence">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="font-medium text-slate-100">Discovery comparison · {selectedCandidate.discovery_status === "eligible" ? `rank #${selectedCandidate.ranking}` : "insufficient evidence"}</h2>
            <span className="font-mono text-sm text-cyan-200">Weighted distance {selectedCandidate.weighted_distance?.toFixed(4) ?? "unavailable"}</span>
          </div>
          <p className="mt-1 text-xs text-slate-400">Lower distance means closer feature distributions under this versioned experiment profile and bounded search. It is not a percent similarity or a validated claim of mission suitability. Evidence coverage: {selectedCandidate.evidence_coverage == null ? "unavailable" : `${(selectedCandidate.evidence_coverage * 100).toFixed(2)}%`} · spatial block-bootstrap SE: {selectedCandidate.weighted_distance_standard_error?.toFixed(4) ?? "unavailable"}</p>
          <div className="mt-3 flex flex-wrap gap-2">
            {Object.entries(selectedCandidate.feature_distances).map(([feature, distance]) => (
              <span key={feature} className="rounded border border-slate-700 px-2 py-1 text-xs text-slate-300">{feature.replaceAll("_", " ")}: {distance.toFixed(3)}</span>
            ))}
          </div>
        </section>
      )}

      {loadingCandidates && <p role="status" className="text-sm text-slate-400">Loading actual candidate records…</p>}
      {!loadingCandidates && candidates.length === 0 && !error && (
        <div className="rounded border border-slate-700 bg-slate-900 p-5 text-sm text-slate-300">
          No discovery candidate records are available. Run a discovery job with real DEM sources first.
        </div>
      )}
      {error && <p role="alert" className="rounded border border-rose-900 bg-rose-950/60 p-3 text-sm text-rose-200">{error}</p>}

      {metadata && (
        <div className="space-y-5">
          <Link href={`/candidates/${encodeURIComponent(metadata.candidate_id)}/passport`} className="inline-flex rounded border border-cyan-800 px-3 py-2 text-sm text-cyan-200 hover:bg-cyan-950/40">
            Open candidate Evidence Passport
          </Link>
          <div className="flex flex-wrap items-center gap-3 rounded-md border border-amber-700/70 bg-amber-950/30 p-4">
            <span className="rounded bg-amber-400 px-2 py-1 font-mono text-xs font-bold text-amber-950">
              {metadata.validation_status.toUpperCase()}
            </span>
            <div>
              <p className="font-medium text-amber-100">Independent elevation validation</p>
              <p className="mt-1 text-sm text-amber-200/80">{metadata.validation_reason ?? "Independent comparison metrics are available below."}</p>
            </div>
            {metadata.discovery_status === "insufficient_evidence" && (
              <span className="ml-auto rounded border border-slate-600 px-2 py-1 text-xs text-slate-300">
                Candidate is unranked · insufficient discovery evidence
              </span>
            )}
          </div>

          <div className="grid gap-4 lg:grid-cols-[minmax(0,1.5fr)_minmax(300px,0.8fr)]">
            <div className="space-y-3">
              <div className="flex flex-wrap items-center gap-2">
                <label className="text-xs text-slate-400" htmlFor="terrain-color-mode">Color</label>
                <select id="terrain-color-mode" className="rounded border border-slate-600 bg-slate-900 px-2 py-1 text-xs" value={colorMode} onChange={(event) => setColorMode(event.target.value as "elevation" | "slope")}>
                  <option value="elevation">Elevation</option>
                  <option value="slope">Slope</option>
                </select>
                <label className="flex items-center gap-2 px-2 text-xs text-slate-300">
                  <input type="checkbox" checked={wireframe} onChange={(event) => setWireframe(event.target.checked)} />
                  Wireframe
                </label>
                <label className="flex min-w-56 items-center gap-2 text-xs text-slate-300">
                  <span>Vertical display scale</span>
                  <input
                    aria-label="Vertical display exaggeration"
                    className="min-w-20 accent-cyan-400"
                    type="range"
                    min={1}
                    max={10}
                    step={1}
                    value={displayVerticalExaggeration}
                    onChange={(event) => setDisplayVerticalExaggeration(Number(event.target.value))}
                  />
                  <output className="w-8 font-mono text-cyan-200">{displayVerticalExaggeration}×</output>
                </label>
                <button className="ml-auto rounded border border-slate-600 px-3 py-1 text-xs text-slate-200 hover:bg-slate-800" onClick={() => setResetToken((value) => value + 1)}>
                  Reset camera
                </button>
              </div>
              <TerrainMeshViewer
                meshUrl={terrainTwinApi.artifactUrl(metadata.artifacts.mesh)}
                colorMode={colorMode}
                wireframe={wireframe}
                verticalExaggeration={displayVerticalExaggeration}
                resetToken={resetToken}
                onLoaded={onLoaded}
                onError={onViewerError}
              />
              {viewerError && <p role="alert" className="text-sm text-rose-300">{viewerError}</p>}
              <p className="text-xs text-slate-400">
                Viewer relief is shown at {displayVerticalExaggeration}× vertical scale to make subtle elevation changes visible. This is a display transform only; the exported mesh remains at {metadata.vertical_exaggeration}× and its source elevations are unchanged.
              </p>
            </div>

            <aside className="space-y-3 rounded-md border border-slate-700 bg-slate-900 p-4">
              <h2 className="font-medium text-slate-100">Reconstruction metadata</h2>
              <dl className="space-y-2 text-xs">
                <div><dt className="text-slate-500">Source</dt><dd className="break-words text-slate-200">{metadata.source_product}</dd></div>
                <div><dt className="text-slate-500">Source checksum</dt><dd className="break-all font-mono text-slate-300">{metadata.source_sha256}</dd></div>
                <div><dt className="text-slate-500">Mesh CRS</dt><dd className="text-slate-200">{metadata.mesh_crs}</dd></div>
                <div><dt className="text-slate-500">Source vertical reference</dt><dd className="text-slate-200">{metadata.source_vertical_reference} · {metadata.source_vertical_units}</dd></div>
                <div><dt className="text-slate-500">Source / mesh dimensions</dt><dd className="text-slate-200">{metadata.candidate_crop_dimensions.join(" × ")} / {metadata.mesh_dimensions.join(" × ")} cells</dd></div>
                <div><dt className="text-slate-500">Mesh posting / exaggeration</dt><dd className="text-slate-200">{metadata.mesh_resolution_m.map((value) => value.toFixed(2)).join(" × ")} m / {metadata.vertical_exaggeration}×</dd></div>
                <div><dt className="text-slate-500">Simplification / chunks</dt><dd className="text-slate-200">stride {metadata.simplification_stride} · {metadata.actual_vertex_count.toLocaleString()} vertices · {metadata.chunk_count} chunks</dd></div>
                <div><dt className="text-slate-500">Elevation range</dt><dd className="text-slate-200">{metadata.elevation_range_m[0].toFixed(2)}–{metadata.elevation_range_m[1].toFixed(2)} m</dd></div>
                <div><dt className="text-slate-500">NoData / candidate exterior</dt><dd className="text-slate-200">{metadata.source_nodata_cell_count.toLocaleString()} source NoData cells · {metadata.source_candidate_exterior_cell_count.toLocaleString()} crop cells outside polygon · {metadata.mesh_nodata_cell_count.toLocaleString()} invalid projected cells</dd></div>
                <div><dt className="text-slate-500">Candidate bounds (WGS84)</dt><dd className="text-slate-200">{metadata.geographic_bounds_wgs84.map((value) => value.toFixed(5)).join(", ")}</dd></div>
              </dl>
              <div className="space-y-2 border-t border-slate-700 pt-3">
                <h3 className="text-xs font-medium uppercase tracking-wider text-slate-400">Elevation & slope maps</h3>
                <div className="grid grid-cols-2 gap-2">
                  <figure><img className="aspect-square w-full rounded border border-slate-700 object-cover" src={terrainTwinApi.artifactUrl(metadata.artifacts.elevation_map)} alt="Elevation-colored map of the selected candidate DEM" /><figcaption className="mt-1 text-center text-xs text-slate-500">Elevation</figcaption></figure>
                  <figure><img className="aspect-square w-full rounded border border-slate-700 object-cover" src={terrainTwinApi.artifactUrl(metadata.artifacts.slope_map)} alt="Slope-colored map derived from the projected DEM" /><figcaption className="mt-1 text-center text-xs text-slate-500">Slope</figcaption></figure>
                </div>
              </div>
            </aside>
          </div>

          {metadata.validation_metrics && (
            <section className="grid gap-3 rounded border border-emerald-800 bg-emerald-950/30 p-4 sm:grid-cols-2 lg:grid-cols-4" aria-label="Independent validation metrics">
              <p className="text-sm text-emerald-100 sm:col-span-2 lg:col-span-4">Independent mesh comparison · {referenceDatasets.find((dataset) => dataset.id === metadata.reference_dataset_id)?.product ?? "selected reference DEM"} · {metadata.validation_metrics.resampling} · support {metadata.validation_metrics.comparison_support_m?.toFixed(2) ?? "not reported"} m</p>
              <p>MAE <strong>{metadata.validation_metrics.mean_absolute_error_m.toFixed(3)} m</strong></p>
              <p>RMSE <strong>{metadata.validation_metrics.root_mean_square_error_m.toFixed(3)} m</strong></p>
              <p>Median absolute error <strong>{metadata.validation_metrics.median_absolute_error_m.toFixed(3)} m</strong></p>
              <p>Bias <strong>{metadata.validation_metrics.mean_bias_m.toFixed(3)} m</strong></p>
              <p>Valid samples <strong>{metadata.validation_metrics.valid_sample_count.toLocaleString()}</strong></p>
              <p>Valid area <strong>{(metadata.validation_metrics.valid_comparison_area_m2 / 1e6).toFixed(3)} km²</strong></p>
              <p>Comparison coverage <strong>{(metadata.validation_metrics.valid_coverage * 100).toFixed(2)}%</strong></p>
            </section>
          )}
          {metadata.validation_status === "unvalidated" && (
            <p className="rounded border border-amber-800 bg-amber-950/30 p-3 text-sm text-amber-100">Visualization-only mesh. {metadata.validation_reason ?? "Independent elevation comparison was not completed."}</p>
          )}

          <div className="grid gap-3 md:grid-cols-2">
            <figure className="rounded border border-slate-700 bg-slate-900 p-2">
              <figcaption className="mb-2 text-xs font-medium text-slate-300">Mesh elevation minus independent DEM</figcaption>
              <img className="max-h-[360px] w-full rounded bg-slate-950 object-contain" src={terrainTwinApi.artifactUrl(metadata.artifacts.error_map)} alt={metadata.validation_status === "validated" ? "Elevation error map from independent DEM comparison" : "Error map unavailable because independent validation was not performed"} />
              {metadata.validation_metrics && (
                <div className="mt-2 space-y-1 text-xs text-slate-400">
                  <div className="h-2 rounded bg-gradient-to-r from-blue-600 via-slate-400 to-red-600" aria-hidden="true" />
                  <div className="flex justify-between"><span>Mesh lower</span><span>0 m</span><span>Mesh higher</span></div>
                </div>
              )}
            </figure>
            <figure className="rounded border border-slate-700 bg-slate-900 p-2">
              <figcaption className="mb-2 text-xs font-medium text-slate-300">Cells included in independent DEM comparison</figcaption>
              <img className="max-h-[360px] w-full rounded border border-slate-800 bg-slate-950 object-contain" src={terrainTwinApi.artifactUrl(metadata.artifacts.valid_comparison_mask)} alt={metadata.validation_status === "validated" ? "Map mask showing valid independent DEM comparison cells" : "Comparison mask unavailable because there is no independent reference"} />
              {metadata.validation_metrics ? (
                <div className="mt-3 space-y-2 text-xs text-slate-300">
                  <div className="flex flex-wrap gap-x-5 gap-y-2">
                    <span className="inline-flex items-center gap-2"><i className="h-3 w-3 rounded-sm bg-green-500" aria-hidden="true" /> Included in comparison</span>
                    <span className="inline-flex items-center gap-2"><i className="h-3 w-3 rounded-sm bg-slate-700" aria-hidden="true" /> Outside common valid support</span>
                  </div>
                  <p>{metadata.validation_metrics.valid_sample_count.toLocaleString()} valid cells · {(metadata.validation_metrics.valid_coverage * 100).toFixed(2)}% coverage · {metadata.validation_metrics.comparison_support_m?.toFixed(2) ?? "—"} m comparison support</p>
                  <p className="text-slate-500">Only green cells contributed to the reported validation metrics. The mask is not elevation or error data.</p>
                </div>
              ) : (
                <p className="mt-3 text-xs text-amber-200">No independent comparison cells are asserted because validation is unavailable.</p>
              )}
            </figure>
          </div>
          {metadata.warnings.map((warning) => <p key={warning} className="text-xs text-amber-200/80">{warning}</p>)}
        </div>
      )}
    </section>
  );
}
