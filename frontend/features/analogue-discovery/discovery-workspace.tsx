"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { CandidateMap } from "@/features/analogue-discovery/candidate-map";
import { productApi } from "@/lib/product-api";
import type { Candidate, CandidatePage, DatasetEntry, Job, MissionCatalog } from "@/lib/product-api";

const fieldClass = "mt-1 w-full rounded border border-slate-600 bg-slate-950 px-3 py-2 text-sm text-slate-100";
const panel = "rounded-lg border border-slate-700 bg-slate-900/70 p-5";
const initialCenter = (value: [number, number] | null | undefined) => value ? { longitude: value[0], latitude: value[1] } : null;

export function DiscoveryWorkspace() {
  const [missions, setMissions] = useState<MissionCatalog | null>(null);
  const [datasets, setDatasets] = useState<DatasetEntry[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [job, setJob] = useState<Job | null>(null);
  const [result, setResult] = useState<CandidatePage | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [acquiring, setAcquiring] = useState<string | null>(null);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadTarget, setUploadTarget] = useState<"mars" | "moon" | "earth">("earth");
  const [uploadMetadata, setUploadMetadata] = useState({ vertical_units: "", vertical_reference: "", provider: "", product: "", attribution: "" });
  const [uploading, setUploading] = useState(false);
  const [minimumCoverage, setMinimumCoverage] = useState(0);
  const [marsId, setMarsId] = useState("");
  const [planetaryBody, setPlanetaryBody] = useState<"mars" | "moon">("mars");
  const [referenceRegionId, setReferenceRegionId] = useState("jezero_crater");
  const [earthId, setEarthId] = useState("");
  const [marsCenter, setMarsCenter] = useState<{ longitude: number; latitude: number } | null>(null);
  const [earthCenter, setEarthCenter] = useState<{ longitude: number; latitude: number } | null>(null);
  const [support, setSupport] = useState(10_000);
  const [planetarySupport, setPlanetarySupport] = useState(2_000);
  const [targetResolution, setTargetResolution] = useState(30);
  const [requiredEvidenceCoverage, setRequiredEvidenceCoverage] = useState(0.8);
  const [candidateSize, setCandidateSize] = useState(2_000);
  const [stride, setStride] = useState(2_000);
  const [maxCandidates, setMaxCandidates] = useState(1_000);
  const [bootstrapReplicates, setBootstrapReplicates] = useState(30);

  const refresh = useCallback(async () => {
    const [missionData, datasetData, jobData] = await Promise.all([productApi.missions(), productApi.datasets(), productApi.jobs()]);
    setMissions(missionData);
    setDatasets(datasetData.datasets);
    setJobs(jobData.items);
    const planetary = datasetData.datasets.find((item) => item.manifest.target_body === planetaryBody && item.available && item.manifest.product_metadata.product_id === "DTEEC_048842_1985_048908_1985_U01")
      ?? datasetData.datasets.find((item) => item.manifest.target_body === planetaryBody && item.available);
    const earth = datasetData.datasets.find((item) => item.manifest.target_body === "earth" && item.available && item.manifest.product_metadata.surface_type === "bare_earth_dtm")
      ?? datasetData.datasets.find((item) => item.manifest.target_body === "earth" && item.available);
    if (planetary) setMarsId((current) => current || planetary.manifest.id);
    if (earth) setEarthId((current) => current || earth.manifest.id);
    const regionCenter = missionData.reference_regions.find((region) => region.body === planetaryBody)?.last_processed_center_lon_lat;
    if (regionCenter) setMarsCenter((current) => current || initialCenter(regionCenter));
    const defaultRegion = missionData.reference_regions.find((region) => region.body === planetaryBody);
    if (defaultRegion) setReferenceRegionId((current) => current || defaultRegion.region_id);
    const earthDefault = missionData.earth_search_defaults?.find((item) => item.dataset_id === earth?.manifest.id)?.last_processed_center_lon_lat;
    if (earthDefault) setEarthCenter((current) => current || initialCenter(earthDefault));
  }, [planetaryBody]);

  useEffect(() => {
    let active = true;
    Promise.all([productApi.missions(), productApi.datasets(), productApi.jobs()]).then(async ([missionData, datasetData, jobData]) => {
      if (!active) return;
      setMissions(missionData); setDatasets(datasetData.datasets); setJobs(jobData.items);
      const mars = datasetData.datasets.find((item) => item.manifest.target_body === "mars" && item.available && item.manifest.product_metadata.product_id === "DTEEC_048842_1985_048908_1985_U01")
        ?? datasetData.datasets.find((item) => item.manifest.target_body === "mars" && item.available);
      const earth = datasetData.datasets.find((item) => item.manifest.target_body === "earth" && item.available && item.manifest.product_metadata.surface_type === "bare_earth_dtm")
        ?? datasetData.datasets.find((item) => item.manifest.target_body === "earth" && item.available);
      if (mars) { setMarsId(mars.manifest.id); configurePlanetaryDefaults(mars.manifest); }
      if (earth) setEarthId(earth.manifest.id);
      const marsCenterValue = missionData.reference_regions[0]?.last_processed_center_lon_lat;
      if (marsCenterValue) setMarsCenter(initialCenter(marsCenterValue));
      const defaultRegion = missionData.reference_regions.find((region) => region.body === "mars");
      if (defaultRegion) setReferenceRegionId(defaultRegion.region_id);
      const earthCenterValue = missionData.earth_search_defaults?.find((item) => item.dataset_id === earth?.manifest.id)?.last_processed_center_lon_lat;
      if (earthCenterValue) setEarthCenter(initialCenter(earthCenterValue));
      const activeJob = jobData.items.find((item) => item.status === "queued" || item.status === "running") ?? jobData.items[0];
      if (activeJob?.status === "queued" || activeJob?.status === "running") {
        setJob(activeJob);
      } else {
        let latestValidResult: { job: Job; candidates: CandidatePage } | null = null;
        // Older successful job rows may point to reports written under a prior
        // schema. Prefer the newest valid report with ranked evidence; retain
        // a valid unranked run only if no ranked result can be restored.
        for (const completedJob of jobData.items.filter((item) => item.status === "succeeded")) {
          try {
            const candidatePage = await productApi.candidates(completedJob.job_id, 0);
            if (!active) return;
            latestValidResult ??= { job: completedJob, candidates: candidatePage };
            if (candidatePage.ranked_candidate_count > 0) {
              latestValidResult = { job: completedJob, candidates: candidatePage };
              break;
            }
          } catch {
            // Keep scanning persisted successes; malformed historical reports
            // are not candidate data and must not suppress a valid prior run.
          }
        }
        if (active && latestValidResult) {
          setJob(latestValidResult.job);
          setResult(latestValidResult.candidates);
        }
      }
    }).catch((reason: unknown) => { if (active) setError(reason instanceof Error ? reason.message : "TerraTwin API request failed"); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  const activeJobId = job?.job_id;
  const activeJobStatus = job?.status;
  useEffect(() => {
    if (!activeJobId || !activeJobStatus || !["queued", "running"].includes(activeJobStatus)) return;
    let cancelled = false;
    const timer = window.setInterval(async () => {
      try {
        const updated = await productApi.job(activeJobId);
        if (cancelled) return;
        setJob(updated);
        if (updated.status === "succeeded") {
          const candidates = await productApi.candidates(updated.job_id, minimumCoverage);
          if (!cancelled) setResult(candidates);
          void refresh();
        } else if (["failed", "interrupted"].includes(updated.status)) void refresh();
      } catch (reason) {
        if (!cancelled) setError(reason instanceof Error ? reason.message : "Could not refresh discovery status.");
      }
    }, 1800);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, [activeJobId, activeJobStatus, minimumCoverage, refresh]);

  useEffect(() => {
    if (!activeJobId || activeJobStatus !== "succeeded") return;
    const controller = new AbortController();
    productApi.candidates(activeJobId, minimumCoverage, controller.signal).then(setResult).catch((reason: unknown) => {
      if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "Candidate results could not be loaded.");
    });
    return () => controller.abort();
  }, [activeJobId, activeJobStatus, minimumCoverage]);

  const availablePlanetary = useMemo(() => datasets.filter((d) => d.manifest.target_body === planetaryBody && d.available), [datasets, planetaryBody]);
  const availableEarth = useMemo(() => datasets.filter((d) => d.manifest.target_body === "earth" && d.available), [datasets]);
  const selectedPlanetary = availablePlanetary.find((d) => d.manifest.id === marsId);
  const referenceRegions = missions?.reference_regions.filter((region) => region.body === planetaryBody) ?? [];
  const selectedEarth = availableEarth.find((d) => d.manifest.id === earthId);

  function configurePlanetaryDefaults(manifest: DatasetEntry["manifest"]) {
    setTargetResolution(30);
    const linearUnit = manifest.resolution_unit.trim().toLowerCase();
    const nominalSpacingM = ["m", "meter", "meters", "metre", "metres"].includes(linearUnit)
      ? Math.max(manifest.pixel_resolution_x, manifest.pixel_resolution_y)
      : 0;
    if (nominalSpacingM >= 100) {
      // Coarse planetary grids need wider physical support to leave enough
      // interior cells for neighborhood terrain features and morphology.
      const supportForSamples = Math.ceil((nominalSpacingM * 10) / 1_000) * 1_000;
      const candidateWidth = Math.max(5_000, supportForSamples);
      const isSparseMolaMegdr = manifest.product_metadata.product_id === "MEGT44N000HB";
      setPlanetarySupport(isSparseMolaMegdr ? 50_000 : Math.max(10_000, supportForSamples));
      setCandidateSize(candidateWidth);
      setStride(Math.max(1_000, candidateWidth / 2));
    } else {
      setPlanetarySupport(2_000);
      setCandidateSize(2_000);
      setStride(2_000);
    }
  }

  async function acquire(kind: "planetary" | "earth") {
    setAcquiring(kind); setError(null);
    try {
        if (kind === "planetary" && planetaryBody === "mars") {
        const manifest = await productApi.acquireHiRISEJezero();
        setMarsId(manifest.id); configurePlanetaryDefaults(manifest);
      } else if (earthCenter) {
        const latitudeTile = Math.floor(earthCenter.latitude);
        const longitudeTile = Math.floor(earthCenter.longitude);
        const manifest = await productApi.acquireEarth(latitudeTile, longitudeTile); setEarthId(manifest.id);
      }
      await refresh();
    } catch (reason) { setError(reason instanceof Error ? reason.message : `${kind} dataset acquisition failed`); }
    finally { setAcquiring(null); }
  }

  async function uploadDataset() {
    if (!uploadFile || Object.values(uploadMetadata).some((value) => !value.trim())) {
      setError("Select a GeoTIFF and provide all required source and vertical metadata."); return;
    }
    setUploading(true); setError(null);
    try {
      const manifest = await productApi.uploadDataset(uploadFile, uploadTarget, uploadMetadata);
      if (uploadTarget === "earth") setEarthId(manifest.id); else { setMarsId(manifest.id); configurePlanetaryDefaults(manifest); }
      setUploadFile(null); await refresh();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Earth GeoTIFF ingestion failed"); }
    finally { setUploading(false); }
  }

  async function launch() {
    setError(null); setResult(null);
    if (!marsCenter || !earthCenter || !selectedPlanetary || !selectedEarth) {
      setError("Select validated planetary and Earth datasets and set explicit geographic centers."); return;
    }
    try {
      const submitted = await productApi.submit({
        planetary_dataset_id: marsId, earth_dataset_id: earthId,
        planetary_center: { longitude: marsCenter.longitude, latitude: marsCenter.latitude },
        earth_center: { longitude: earthCenter.longitude, latitude: earthCenter.latitude },
        support_width_m: support, support_height_m: support,
        planetary_reference_width_m: planetarySupport, planetary_reference_height_m: planetarySupport,
        target_resolution_m: targetResolution,
        candidate_width_m: candidateSize, candidate_height_m: candidateSize,
        candidate_stride_m: stride, maximum_candidate_count: maxCandidates,
        minimum_evidence_coverage: requiredEvidenceCoverage,
        bootstrap_replicates: bootstrapReplicates,
      });
      setJob(submitted); setJobs((current) => [submitted, ...current.filter((item) => item.job_id !== submitted.job_id)]);
      if (submitted.status === "succeeded") setResult(await productApi.candidates(submitted.job_id, minimumCoverage));
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Discovery job could not be submitted."); }
  }

  async function selectJob(id: string) {
    setError(null); setResult(null);
    try {
      const selected = await productApi.job(id); setJob(selected);
      if (selected.status === "succeeded") setResult(await productApi.candidates(id, minimumCoverage));
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Stored discovery job could not be loaded."); }
  }

  const entriesForSelected = (kind: "planetary" | "earth") => kind === "planetary" ? availablePlanetary : availableEarth;
  const currentCenter = (kind: "planetary" | "earth") => kind === "planetary" ? marsCenter : earthCenter;
  function selectPlanetaryDataset(datasetId: string) {
    setMarsId(datasetId);
    const dataset = datasets.find((item) => item.manifest.id === datasetId);
    if (dataset) configurePlanetaryDefaults(dataset.manifest);
  }
  function selectReferenceRegion(regionId: string) {
    setReferenceRegionId(regionId);
    const region = referenceRegions.find((item) => item.region_id === regionId);
    const datasetId = region?.source_dataset_ids[0] ?? "";
    if (datasetId) selectPlanetaryDataset(datasetId);
    setMarsCenter(initialCenter(region?.last_processed_center_lon_lat));
  }
  function selectPlanetaryBody(body: "mars" | "moon") {
    setPlanetaryBody(body);
    const region = missions?.reference_regions.find((item) => item.body === body);
    setReferenceRegionId(region?.region_id ?? "");
    const datasetId = region?.source_dataset_ids[0] ?? "";
    if (datasetId) selectPlanetaryDataset(datasetId);
    setMarsCenter(initialCenter(region?.last_processed_center_lon_lat));
  }
  const updateCenter = (kind: "planetary" | "earth", axis: "longitude" | "latitude", value: number) => {
    const setter = kind === "planetary" ? setMarsCenter : setEarthCenter;
    const center = kind === "planetary" ? marsCenter : earthCenter;
    setter({ longitude: center?.longitude ?? 0, latitude: center?.latitude ?? 0, [axis]: value });
  };

  if (loading) return <p role="status" className="py-12 text-slate-300">Loading actual mission, dataset and job records…</p>;
  return <div className="space-y-6">
    <header><p className="font-mono text-xs uppercase tracking-[.2em] text-cyan-300">Product integration · actual processing outputs</p><h1 className="mt-2 text-3xl font-semibold">Mission Explorer &amp; Analogue Discovery</h1><p className="mt-2 max-w-4xl text-sm leading-6 text-slate-400">Use the Jezero HiRISE stereo DTM for a high-resolution planetary reference and search a wider, checksummed Earth DEM support at the coarser shared comparison scale. The UI displays only persisted backend measurements and rankings.</p></header>

    <section className={`${panel} space-y-4`} aria-labelledby="data-selection">
      <div><h2 id="data-selection" className="text-lg font-semibold">1 · Reference and source data</h2><p className="mt-1 text-xs text-slate-400">Catalog availability includes a checksum check against the raw dataset.</p></div>
      <div className="grid gap-4 lg:grid-cols-2">
        {(["planetary", "earth"] as const).map((kind) => {
          const selected = kind === "planetary" ? selectedPlanetary : selectedEarth;
          const center = currentCenter(kind);
          const id = kind === "planetary" ? marsId : earthId;
          const setId = kind === "planetary" ? setMarsId : setEarthId;
          return <article className="rounded border border-slate-700 p-4" key={kind}>
            <div className="flex flex-wrap items-start justify-between gap-2"><div><h3 className="font-medium">{kind === "planetary" ? `${planetaryBody === "mars" ? "Mars" : "Moon"} · planetary reference` : "Earth · candidate search source"}</h3><p className="mt-1 text-xs text-slate-500">{entriesForSelected(kind).length} checksum-verified local source(s)</p></div>{kind === "earth" || planetaryBody === "mars" ? <button onClick={() => void acquire(kind)} disabled={acquiring !== null || (kind === "earth" && !earthCenter)} className="rounded border border-cyan-800 px-3 py-1.5 text-xs text-cyan-200 disabled:opacity-50">{acquiring === kind ? "Acquiring…" : kind === "planetary" ? "Acquire Jezero HiRISE DTM" : "Acquire Copernicus tile at center"}</button> : <span className="text-xs text-slate-500">No automatic LOLA downloader is configured</span>}</div>
            {kind === "planetary" && <div className="mt-3 grid gap-3 sm:grid-cols-2"><label className="text-xs text-slate-400">Planetary body<select className={fieldClass} value={planetaryBody} onChange={(event) => selectPlanetaryBody(event.target.value as "mars" | "moon")}><option value="mars">Mars</option><option value="moon">Moon</option></select></label><label className="text-xs text-slate-400">Reference region<select className={fieldClass} value={referenceRegionId} onChange={(event) => selectReferenceRegion(event.target.value)}><option value="">Select or define reference area</option>{referenceRegions.map((region) => <option key={region.region_id} value={region.region_id}>{region.label}</option>)}</select></label></div>}
            {entriesForSelected(kind).length === 0 && <p className="mt-2 text-xs text-amber-200">No checksum-verified {kind === "planetary" ? (planetaryBody === "mars" ? "Mars" : "Moon") : "Earth"} source is available in this installation yet.</p>}
            <label className="mt-4 block text-xs text-slate-400">Validated source dataset<select className={fieldClass} value={id} onChange={(event) => kind === "planetary" ? selectPlanetaryDataset(event.target.value) : setId(event.target.value)}><option value="">Select available data</option>{entriesForSelected(kind).map((entry) => <option key={entry.manifest.id} value={entry.manifest.id}>{entry.manifest.product} · {entry.manifest.id.slice(0, 12)}</option>)}</select></label>
            {selected && <p className="mt-2 text-xs leading-5 text-slate-400">{selected.manifest.provider} · {selected.manifest.width.toLocaleString()} × {selected.manifest.height.toLocaleString()} px · {selected.manifest.pixel_resolution_x} × {selected.manifest.pixel_resolution_y} {selected.manifest.resolution_unit} · vertical {selected.manifest.vertical_units} ({selected.manifest.vertical_reference}) · checksum verified.</p>}
            {selected && !center && <p className="mt-2 text-xs text-amber-200">No previously processed center is recorded. Enter the center for this run explicitly.</p>}
            <div className="mt-3 grid grid-cols-2 gap-3">{(["longitude", "latitude"] as const).map((axis) => <label key={axis} className="text-xs capitalize text-slate-400">Center {axis} (degrees)<input className={fieldClass} type="number" step="any" min={axis === "longitude" ? -180 : -90} max={axis === "longitude" ? 180 : 90} value={center?.[axis] ?? ""} onChange={(event) => updateCenter(kind, axis, Number(event.target.value))} /></label>)}</div>
          </article>;
        })}
      </div>
      {availableEarth.length === 1 && <p className="text-xs text-amber-200">Earth search is limited to the verified local Copernicus tile(s) listed here. TerraTwin does not claim global candidate coverage.</p>}
      {missions?.unavailable_bodies?.length ? <p className="text-xs text-slate-400">Planetary bodies without locally available sources: {missions.unavailable_bodies.join(", ")}.</p> : null}
      {selectedPlanetary?.manifest.product_metadata.product_id === "MEGT44N000HB" && <p role="status" className="rounded border border-amber-800 bg-amber-950/30 p-3 text-xs leading-5 text-amber-100">MOLA MEGDR is coarse and has sparse direct observations at this Jezero support. The requested 30 m target will be coarsened to native source support, and the reference window is widened to retain enough valid terrain samples. Candidates can still be marked insufficient evidence; use the HiRISE DTM for finer rover-mobility comparisons.</p>}
      <details className="rounded border border-slate-700 p-4">
        <summary className="cursor-pointer text-sm font-medium text-slate-200">Ingest a user-supplied GeoTIFF</summary>
        <p className="mt-2 text-xs text-slate-400">The backend streams the file into private staging and validates CRS, raster metadata, vertical units and checksum. Missing CRS is rejected. Source metadata is mandatory.</p>
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          <label className="text-xs text-slate-400">Target body<select className={fieldClass} value={uploadTarget} onChange={(event) => setUploadTarget(event.target.value as "mars" | "moon" | "earth")}><option value="earth">Earth</option><option value="mars">Mars</option><option value="moon">Moon</option></select></label>
          {(["provider", "product", "vertical_reference", "attribution", "vertical_units"] as const).map((key) => <label key={key} className="text-xs capitalize text-slate-400">{key.replaceAll("_", " ")}<input className={fieldClass} value={uploadMetadata[key]} onChange={(event) => setUploadMetadata((old) => ({ ...old, [key]: event.target.value }))} /></label>)}
          <label className="text-xs text-slate-400">GeoTIFF file<input className={`${fieldClass} file:mr-3 file:rounded file:border-0 file:bg-slate-700 file:px-3 file:py-1`} type="file" accept=".tif,.tiff,image/tiff" onChange={(event) => setUploadFile(event.target.files?.[0] ?? null)} /></label>
        </div>
        <button className="mt-3 rounded border border-cyan-800 px-3 py-2 text-xs text-cyan-200 disabled:opacity-50" disabled={uploading || !uploadFile} onClick={() => void uploadDataset()}>{uploading ? "Validating and registering…" : "Validate and ingest GeoTIFF"}</button>
      </details>
    </section>

    <section className={`${panel} space-y-4`} aria-labelledby="run-config">
      <div><h2 id="run-config" className="text-lg font-semibold">2 · Physical search configuration</h2><p className="mt-1 text-xs text-slate-400">Distances are metres; comparison coverage is a declared local support around each center. The actual grid is never finer than its coarsest input and reports any additional coarsening.</p></div>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">{[
        ["Comparison support width & height (m)", support, setSupport, 10000, 250000],
        ["Planetary reference width & height (m)", planetarySupport, setPlanetarySupport, 1000, 250000],
        ["Requested comparison pixel support (m)", targetResolution, setTargetResolution, 1, 10000],
        ["Candidate window width & height (m)", candidateSize, setCandidateSize, 1000, 100000],
        ["Candidate stride (m)", stride, setStride, 100, 100000],
        ["Maximum candidate windows", maxCandidates, setMaxCandidates, 1, 5000],
        ["Bootstrap replicates (0 disables estimate)", bootstrapReplicates, setBootstrapReplicates, 0, 500],
      ].map(([label, value, setter, min, max]) => <label key={String(label)} className="text-xs text-slate-400">{String(label)}<input className={fieldClass} type="number" min={Number(min)} max={Number(max)} value={Number(value)} onChange={(event) => (setter as (value: number) => void)(Number(event.target.value))} /></label>)}
        <label className="text-xs text-slate-400">Minimum evidence coverage for ranking<input className={fieldClass} type="number" step="0.05" min="0.2" max="1" value={requiredEvidenceCoverage} onChange={(event) => setRequiredEvidenceCoverage(Number(event.target.value))} /></label>
      </div>
      <details className="rounded border border-slate-700 p-3"><summary className="cursor-pointer text-xs text-slate-300">Inspect configured experiment feature weights</summary><div className="mt-2 grid gap-2 text-xs text-slate-400 sm:grid-cols-2">{(missions?.mission_profiles ?? []).flatMap((profile) => Object.entries((profile.feature_weights ?? {}) as Record<string, number>).map(([feature, weight]) => <p key={`${String(profile.profile_id)}-${feature}`}><span className="text-slate-200">{feature.replaceAll("_", " ")}</span> · {weight} · {String(((profile.justifications ?? {}) as Record<string, string>)[feature] ?? "No justification recorded")}</p>))}</div><p className="mt-2 text-xs text-amber-200">These are versioned researcher-configured priorities, not established scientific truths.</p></details>
      <div className="flex flex-wrap items-center gap-3"><button onClick={() => void launch()} disabled={!marsId || !earthId || !marsCenter || !earthCenter || Boolean(job && ["queued", "running"].includes(job.status))} className="rounded bg-cyan-400 px-4 py-2 text-sm font-semibold text-slate-950 disabled:cursor-not-allowed disabled:opacity-40">{job && ["queued", "running"].includes(job.status) ? "Discovery processing…" : "Run ScaleBridge + discovery"}</button><span className="text-xs text-slate-500">Profile: ROVER_MOBILITY_AND_TERRAIN_NAVIGATION · {missions?.mission_profiles.length ?? 0} configured profile(s).</span></div>
      {error && <p role="alert" className="rounded border border-rose-900 bg-rose-950/60 p-3 text-sm text-rose-200">{error}</p>}
    </section>

    {job && <section className={`${panel} space-y-3`} aria-live="polite"><div className="flex flex-wrap items-center justify-between gap-3"><div><h2 className="text-lg font-semibold">3 · Persisted discovery job</h2><p className="mt-1 font-mono text-xs text-slate-400">{job.job_id}</p></div><select aria-label="Resume a stored discovery job" className="rounded border border-slate-600 bg-slate-950 px-3 py-2 text-xs" value={job.job_id} onChange={(event) => void selectJob(event.target.value)}>{jobs.map((item) => <option key={item.job_id} value={item.job_id}>{item.created_at.slice(0, 19)} · {item.status} · {item.job_id.slice(0, 8)}</option>)}</select></div><div className="flex flex-wrap items-center gap-3 text-sm"><span className="rounded border border-slate-600 px-2 py-1 uppercase tracking-wide">{job.status}</span><span className="text-slate-300">Stage: {job.stage}</span><span className="text-slate-400">{job.progress_percent}%</span>{job.failure_message && <span role="alert" className="text-rose-300">{job.failure_code}: {job.failure_message}</span>}</div><div className="h-2 overflow-hidden rounded bg-slate-800"><div className="h-full bg-cyan-400 transition-all" style={{ width: `${job.progress_percent}%` }} /></div></section>}

    {result && <section className="space-y-4" aria-labelledby="results-title"><div className="flex flex-wrap items-end justify-between gap-3"><div><h2 id="results-title" className="text-xl font-semibold">4 · Actual returned candidates</h2><p className="mt-1 text-sm text-slate-400">{result.evaluated_window_count} windows evaluated · {result.ranked_candidate_count} evidence-eligible and ranked · {result.eligible_candidate_count} eligible under configured evidence gates.</p><p className="mt-1 font-mono text-xs text-slate-500">Searched WGS84 boundary: {result.searched_boundary_wgs84.join(", ")}</p></div><label className="text-xs text-slate-400">Coverage display threshold <select className="ml-2 rounded border border-slate-600 bg-slate-950 px-2 py-2" value={minimumCoverage} onChange={(event) => setMinimumCoverage(Number(event.target.value))}><option value={0}>Show all evidence states</option><option value={0.25}>≥25%</option><option value={0.5}>≥50%</option><option value={0.8}>≥80%</option></select></label></div>
      <CandidateMap candidates={result.items} />
      {result.warnings.map((warning) => <p key={warning} className="text-xs text-amber-200">{warning}</p>)}
      <div className="grid gap-3 lg:grid-cols-2">{result.items.map((candidate: Candidate) => <CandidateCard key={candidate.candidate_id} candidate={candidate} />)}</div>
      {!result.items.length && <p className="rounded border border-slate-700 bg-slate-900 p-5 text-sm text-slate-300">No candidate meets the selected display threshold. The full processing report remains available; this is not represented as a strong match.</p>}
    </section>}
  </div>;
}

function CandidateCard({ candidate }: { candidate: Candidate }) {
  const [longitude, latitude] = candidate.centroid_wgs84;
  return <article className="rounded-lg border border-slate-700 bg-slate-900/70 p-4"><div className="flex flex-wrap items-start justify-between gap-3"><div><p className="font-mono text-xs text-slate-500">{candidate.candidate_id}</p><h3 className="mt-1 font-medium">{candidate.status === "eligible" ? `Rank ${candidate.ranking ?? "—"} · eligible under this profile` : "Insufficient evidence · unranked"}</h3><p className="mt-1 font-mono text-xs text-slate-400">{latitude.toFixed(6)}° N, {longitude.toFixed(6)}° E</p></div><div className="text-right"><p className="font-mono text-sm text-slate-200">Coverage {(candidate.evidence_coverage * 100).toFixed(2)}%</p><p className="font-mono text-xs text-slate-400">Distance {candidate.weighted_distance?.toFixed(4) ?? "unavailable"}</p></div></div><div className="mt-3 overflow-x-auto"><table className="w-full text-left text-xs"><thead className="text-slate-500"><tr><th className="py-1">Feature</th><th>Reference / Earth median</th><th>Normalized distance</th></tr></thead><tbody>{Object.entries(candidate.feature_comparisons).map(([name, comparison]) => <tr className="border-t border-slate-800" key={name}><td className="py-1.5 text-slate-300">{name.replaceAll("_", " ")}</td><td className="font-mono text-slate-400">{comparison.reference_median?.toPrecision(4) ?? "—"} / {comparison.candidate_median?.toPrecision(4) ?? "—"} {comparison.units}</td><td className="font-mono text-slate-300">{comparison.normalized_distance?.toPrecision(4) ?? "Unavailable"}</td></tr>)}</tbody></table></div>{candidate.missing_features.length > 0 && <p className="mt-2 text-xs text-amber-200">Missing features: {candidate.missing_features.join(", ")}</p>}<div className="mt-3 flex gap-2"><Link className="rounded border border-cyan-800 px-3 py-2 text-xs text-cyan-200 hover:bg-cyan-950/30" href={`/candidates/${candidate.candidate_id}/comparison`}>Feature comparison</Link><Link className="rounded border border-slate-600 px-3 py-2 text-xs text-slate-200 hover:bg-slate-800" href={`/candidates/${candidate.candidate_id}/passport`}>Evidence Passport</Link></div></article>;
}
