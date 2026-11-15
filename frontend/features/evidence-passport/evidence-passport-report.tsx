"use client";

import { useEffect, useState } from "react";
import { evidenceExportUrl, fetchEvidencePassport } from "@/lib/evidence-api";
import type { EvidencePassport } from "@/types/evidence-passport";

const panel = "rounded-lg border border-slate-700 bg-slate-900/70 p-5";
const label = "text-xs uppercase tracking-wider text-slate-400";
const display = (value: number | null | undefined, digits = 6) => value == null ? "Unavailable" : value.toFixed(digits);

export function EvidencePassportReport({ candidateId }: { candidateId: string }) {
  const [passport, setPassport] = useState<EvidencePassport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const controller = new AbortController();
    fetchEvidencePassport(candidateId, controller.signal)
      .then(setPassport)
      .catch((reason: unknown) => {
        if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "Passport could not be loaded.");
      })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [candidateId]);

  if (loading) return <p role="status" className="text-sm text-slate-300">Loading the stored evidence passport…</p>;
  if (error) return <div role="alert" className="rounded border border-rose-800 bg-rose-950/50 p-4 text-rose-200">{error}</div>;
  if (!passport) return <p role="status" className="text-sm text-slate-300">No passport is available for this candidate.</p>;

  const [longitude, latitude] = passport.candidate.centroid_wgs84;
  const conclusionsByCategory = passport.assessment.conclusions.reduce<Record<string, typeof passport.assessment.conclusions>>((groups, finding) => {
    (groups[finding.category] ??= []).push(finding);
    return groups;
  }, {});
  return (
    <div className="space-y-6">
      <header className="space-y-3">
        <p className="font-mono text-xs uppercase tracking-[0.2em] text-cyan-300">Evidence Passport · schema {passport.passport_schema_version}</p>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-3xl font-semibold text-slate-50">Candidate evidence record</h1>
            <p className="mt-2 text-sm text-slate-300">Deterministic assessment for {passport.mission_profile.experiment_name}, profile v{passport.mission_profile.version}.</p>
          </div>
          <div className="flex gap-2">
            <a className="rounded border border-slate-600 px-3 py-2 text-sm hover:bg-slate-800" href={evidenceExportUrl(candidateId, "json")}>Export JSON</a>
            <a className="rounded bg-cyan-400 px-3 py-2 text-sm font-semibold text-slate-950 hover:bg-cyan-300" href={evidenceExportUrl(candidateId, "pdf")}>Export PDF</a>
          </div>
        </div>
      </header>

      <section className={`${panel} grid gap-5 md:grid-cols-3`} aria-label="Candidate summary">
        <div><p className={label}>Evidence state</p><p className="mt-1 font-medium text-amber-200">{passport.candidate.discovery_status === "eligible" ? "Eligible under configured evidence gates" : "Insufficient evidence · unranked"}</p><p className="mt-1 text-xs text-slate-400">Assessment: {passport.assessment.overall_evidence_status}</p></div>
        <div><p className={label}>Earth candidate centroid</p><p className="mt-1 font-mono text-sm text-slate-100">{latitude.toFixed(6)}° lat, {longitude.toFixed(6)}° lon</p><details className="mt-1 text-xs text-slate-400"><summary className="cursor-pointer">Candidate boundary · {passport.candidate.geographic_boundary_wgs84.length} WGS84 vertices</summary><ol className="mt-2 max-h-32 space-y-1 overflow-auto font-mono">{passport.candidate.geographic_boundary_wgs84.map(([lon, lat], index) => <li key={`${index}-${lon}-${lat}`}>{index + 1}: {lon.toFixed(7)}, {lat.toFixed(7)}</li>)}</ol></details></div>
        <div><p className={label}>Mars reference</p><p className="mt-1 text-sm text-slate-100">{passport.planetary_reference.product}</p><p className="mt-1 text-xs text-slate-400">{passport.planetary_reference.width_m.toLocaleString()} × {passport.planetary_reference.height_m.toLocaleString()} m · nominal/effective resolution {display(passport.planetary_reference.effective_resolution_m, 1)} m ({passport.planetary_reference.effective_resolution_status})</p></div>
        <div><p className={label}>Evidence coverage</p><p className="mt-1 font-mono text-lg text-slate-100">{(passport.evidence_coverage.overall * 100).toFixed(3)}%</p><p className="text-xs text-slate-400">Required { (passport.evidence_coverage.minimum_required_coverage * 100).toFixed(1)}% · {passport.evidence_coverage.minimum_required_samples_per_surface} samples per surface</p></div>
        <div><p className={label}>Weighted terrain distance</p><p className="mt-1 font-mono text-lg text-slate-100">{display(passport.weighted_distance.value)}</p><p className="text-xs text-slate-400">{passport.weighted_distance.interpretation}</p></div>
        <div><p className={label}>Terrain Twin validation</p><p className="mt-1 font-medium text-amber-200">{passport.terrain_twin_validation_status.toUpperCase()}</p><p className="text-xs text-slate-400">{passport.terrain_twin?.validation_reason ?? "No independent validation metrics are available."}</p>{passport.terrain_twin?.validation_metrics && <dl className="mt-2 space-y-1 text-xs text-slate-300">{Object.entries(passport.terrain_twin.validation_metrics).map(([name, value]) => <div key={name}><dt className="inline text-slate-500">{name.replaceAll("_", " ")}: </dt><dd className="inline font-mono">{typeof value === "number" ? value.toPrecision(5) : String(value)}</dd></div>)}</dl>}</div>
      </section>

      <section className={`${panel} space-y-3`}>
        <h2 className="text-lg font-semibold text-slate-100">Measured feature comparisons</h2>
        <p className="text-sm text-slate-400">Values below are copied from the discovery run. A distance is not interpreted as a supported match unless that feature passes its evidence gates.</p>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[850px] border-collapse text-left text-xs">
            <thead><tr className="border-b border-slate-700 text-slate-400"><th className="p-2">Feature</th><th className="p-2">Evidence</th><th className="p-2">Mars / Earth median</th><th className="p-2">Normalized distance ± SE</th><th className="p-2">Samples</th><th className="p-2">Coverage Mars / Earth</th></tr></thead>
            <tbody>{Object.entries(passport.feature_evidence).map(([feature, item]) => <tr key={feature} className="border-b border-slate-800 align-top"><th className="p-2 font-medium text-slate-200">{feature.replaceAll("_", " ")}<details className="mt-1 font-normal text-slate-400"><summary className="cursor-pointer">Distribution summaries</summary><pre className="mt-1 max-w-48 overflow-auto whitespace-pre-wrap font-mono text-[10px]">{JSON.stringify({ planetary: item.comparison.reference_summary, earth: item.comparison.candidate_summary }, null, 2)}</pre></details></th><td className="p-2 text-amber-200">{item.evidence_status.replaceAll("_", " ")}</td><td className="p-2 font-mono text-slate-300">{display(item.comparison.reference_median, 4)} / {display(item.comparison.candidate_median, 4)} {item.comparison.units}</td><td className="p-2 font-mono text-slate-300">{display(item.comparison.normalized_distance, 5)} ± {display(item.comparison.distance_standard_error, 5)}</td><td className="p-2 font-mono text-slate-300">{item.comparison.reference_sample_count} / {item.comparison.candidate_sample_count}</td><td className="p-2 font-mono text-slate-300">{(item.comparison.reference_coverage * 100).toFixed(3)}% / {(item.comparison.candidate_coverage * 100).toFixed(2)}%</td></tr>)}</tbody>
          </table>
        </div>
      </section>

      <section className="space-y-4" aria-labelledby="assessment-findings">
        <div><h2 id="assessment-findings" className="text-lg font-semibold text-slate-100">Interpretation and evidence scope</h2><p className="mt-1 text-sm text-slate-400">Deterministic profile rules; measurements and interpretations are shown separately.</p></div>
        {Object.entries(conclusionsByCategory).map(([category, findings]) => <div key={category} className={panel}><h3 className="mb-3 font-mono text-xs font-semibold tracking-wide text-cyan-200">{category.replaceAll("_", " ")}</h3><div className="space-y-4">{findings?.map((finding) => <article key={finding.conclusion_id} className="border-t border-slate-800 pt-3"><div className="flex flex-wrap justify-between gap-2"><h4 className="text-sm font-medium text-slate-100">{finding.conclusion}</h4><span className="font-mono text-[11px] text-amber-200">{finding.evidence_status}</span></div><p className="mt-2 text-sm leading-6 text-slate-300">{finding.evidence_interpretation}</p>{finding.evidence.map((source, index) => <p key={`${source.source_record_id}-${index}`} className="mt-2 break-all font-mono text-[11px] text-slate-500">Evidence source {source.source_type} · record {source.source_record_id} · dataset {source.source_dataset_id ?? "profile rule only"} · {source.comparison_method}</p>)}{finding.missing_information.length > 0 && <p className="mt-2 text-xs text-amber-200">Missing: {finding.missing_information.join("; ")}</p>}{finding.limitations.map((limitation) => <p key={limitation} className="mt-1 text-xs text-slate-400">Limitation: {limitation}</p>)}</article>)}</div></div>)}
      </section>

      <section className={`${panel} space-y-4`}>
        <h2 className="text-lg font-semibold text-slate-100">Source data and reproducibility</h2>
        <div className="grid gap-4 md:grid-cols-2">{passport.source_datasets.map((source) => <article key={source.dataset_id} className="rounded border border-slate-700 p-3"><p className={label}>{source.target_body} · {source.provider}</p><p className="mt-1 text-sm text-slate-100">{source.product} {source.version ?? ""}</p><p className="mt-2 text-xs text-slate-400">{source.dimensions.join(" × ")} pixels · {source.pixel_resolution.join(" × ")} {source.resolution_unit} · {source.vertical_units}, {source.vertical_reference}</p><p className="mt-2 break-all font-mono text-[10px] text-slate-500">Dataset {source.dataset_id} · raw SHA-256 {source.raw_checksum_sha256}</p></article>)}</div>
        <dl className="grid gap-3 text-xs md:grid-cols-2"><div><dt className={label}>Discovery run</dt><dd className="mt-1 break-all font-mono text-slate-300">{passport.candidate.discovery_run_id}</dd></div><div><dt className={label}>ScaleBridge run</dt><dd className="mt-1 break-all font-mono text-slate-300">{passport.processing.scale_bridge.run_id} · {passport.processing.scale_bridge.target_resolution_m} m · {passport.processing.scale_bridge.resampling}</dd></div><div><dt className={label}>Reproducibility SHA-256</dt><dd className="mt-1 break-all font-mono text-slate-300">{passport.reproducibility_sha256}</dd></div><div><dt className={label}>Uncertainty</dt><dd className="mt-1 text-slate-300">{passport.uncertainty.interpretation} DEM measurement uncertainty: {passport.uncertainty.instrument_or_dem_measurement_uncertainty}.</dd></div></dl>
        <div><h3 className={label}>Missing evidence</h3>{passport.missing_evidence.length ? <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-amber-100">{passport.missing_evidence.map((item) => <li key={item}>{item}</li>)}</ul> : <p className="mt-2 text-sm text-slate-300">No missing evidence is recorded.</p>}</div>
        <div><h3 className={label}>Limitations</h3><ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-300">{passport.limitations.map((item) => <li key={item}>{item}</li>)}</ul></div>
        <p className="border-t border-slate-700 pt-3 text-xs leading-5 text-slate-400">A terrain comparison cannot establish rover safety or performance. Geometry alone does not establish soil properties, traction, dust response, gravity, radiation, vacuum, or a complete planetary atmosphere.</p>
      </section>
    </div>
  );
}
