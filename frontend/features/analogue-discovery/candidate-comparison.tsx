"use client";

/* Images are backend-generated visualization artifacts, not browser calculations. */
/* eslint-disable @next/next/no-img-element */
import Link from "next/link";
import { useEffect, useState } from "react";
import { productApi, resolveApiUrl } from "@/lib/product-api";

type Statistics = {
  mean?: number; median?: number; standard_deviation?: number;
  percentile_05?: number; percentile_25?: number; percentile_75?: number; percentile_95?: number;
};
type FeatureComparisonData = {
  units: string; normalized_distance: number | null; reference_median: number | null;
  candidate_median: number | null; reference_coverage: number; candidate_coverage: number;
  reference_sample_count: number; candidate_sample_count: number;
  reference_class_fractions: Record<string, number>; candidate_class_fractions: Record<string, number>;
  method: string; reference_summary: Statistics; candidate_summary: Statistics;
};
type Comparison = {
  candidate: {
    candidate_id: string; centroid_wgs84: [number, number]; status: string;
    ranking: number | null; weighted_distance: number | null; evidence_coverage: number;
    weighted_distance_standard_error: number | null;
    feature_comparisons: Record<string, FeatureComparisonData>;
  };
  discovery_run_id: string;
  planetary_reference: { body: string; product: string; dataset_id: string; effective_resolution_m: number | null };
  earth_source: { product: string; dataset_id: string; effective_resolution_m: number | null };
  comparison_support: {
    pixel_width_m: number; pixel_height_m: number; scale_bridge_run_id: string; warning: string;
    target_resolution_m: number; target_resolution_basis: string; resampling: string;
    information_loss: Record<string, string>; coverage: {
      planetary_fraction: number; earth_fraction: number; common_fraction: number | null;
    }; planetary_crs: string; earth_crs: string; planetary_source_crs: string;
    earth_source_crs: string; vertical_comparison: string;
  };
  source_resolution: {
    planetary_nominal_ground_spacing_m: [number, number]; planetary_effective_resolution_m: number | null;
    earth_nominal_ground_spacing_m: [number, number]; earth_effective_resolution_m: number | null;
  };
  feature_maps: Record<string, { mars_preview_url: string; earth_preview_url: string }>;
  coverage: { minimum_required_coverage: number };
  warnings: string[];
};

const number = (value: number | null | undefined) => value == null ? "Unavailable" : value.toPrecision(5);

export function CandidateComparison({ candidateId }: { candidateId: string }) {
  const [data, setData] = useState<Comparison | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    const controller = new AbortController();
    productApi.comparison(candidateId, controller.signal)
      .then((value) => setData(value as Comparison))
      .catch((reason: unknown) => {
        if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "Comparison unavailable");
      })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [candidateId]);
  if (loading) return <p role="status" className="text-slate-300">Loading stored feature rasters and measurements…</p>;
  if (error) return <section className="space-y-3 rounded border border-amber-800 bg-amber-950/40 p-5" role="alert">
    <h1 className="text-lg font-semibold text-amber-100">This saved comparison is unavailable</h1>
    <p className="text-sm text-amber-100/90">{error}</p>
    <p className="text-sm text-slate-300">This comparison could not be loaded. Some older runs also lack enough valid Mars terrain samples for feature statistics. Return to the current discovery results and open a candidate with sufficient evidence.</p>
    <Link className="inline-flex rounded border border-cyan-800 px-3 py-2 text-sm text-cyan-200 hover:bg-cyan-950/40" href="/discovery">Open the usable discovery results</Link>
  </section>;
  if (!data) return null;

  const { candidate, comparison_support: support, source_resolution: resolution } = data;
  const noPlanetaryFeatureSamples = Object.values(candidate.feature_comparisons).length > 0
    && Object.values(candidate.feature_comparisons).every((item) => item.reference_sample_count === 0);
  const mapUrl = (path: string) => resolveApiUrl(path, productApi.url);
  return <div className="space-y-6">
    <header>
      <p className="font-mono text-xs uppercase tracking-[.2em] text-cyan-300">Discovery run {data.discovery_run_id}</p>
      <h1 className="mt-2 text-3xl font-semibold">Terrain feature comparison</h1>
      <p className="mt-2 text-sm text-slate-400">{candidate.status === "eligible" ? `Rank ${candidate.ranking ?? "—"} under the selected profile` : "Insufficient evidence · unranked"} · candidate {candidateId}</p>
      <p className="mt-1 font-mono text-xs text-slate-400">WGS84 centroid {candidate.centroid_wgs84[0].toFixed(6)}, {candidate.centroid_wgs84[1].toFixed(6)} · evidence coverage {(candidate.evidence_coverage * 100).toFixed(3)}% · weighted terrain distance {number(candidate.weighted_distance)} · block-bootstrap SE {number(candidate.weighted_distance_standard_error)}</p>
    </header>

    {noPlanetaryFeatureSamples && <section className="space-y-2 rounded border border-amber-800 bg-amber-950/40 p-4" role="status">
      <h2 className="font-medium text-amber-100">Mars measurements unavailable for this run</h2>
      <p className="text-sm text-slate-300">This Mars reference has zero valid terrain-feature samples, so its feature distances and statistics cannot be calculated. Open the completed discovery run with valid Mars and Earth support to see measured comparisons.</p>
      <Link className="inline-flex rounded border border-cyan-800 px-3 py-2 text-sm text-cyan-200 hover:bg-cyan-950/40" href="/discovery">Open current discovery results</Link>
    </section>}

    <section className="grid gap-3 rounded border border-slate-700 bg-slate-900/70 p-4 text-xs md:grid-cols-2">
      <p>Mars: {data.planetary_reference.product} · nominal ground spacing {resolution.planetary_nominal_ground_spacing_m.join(" × ")} m · effective resolution {resolution.planetary_effective_resolution_m ?? "not documented"} m</p>
      <p>Earth: {data.earth_source.product} · nominal ground spacing {resolution.earth_nominal_ground_spacing_m.join(" × ")} m · effective resolution {resolution.earth_effective_resolution_m ?? "not documented"} m</p>
      <p>ScaleBridge target: {support.target_resolution_m} m · {support.target_resolution_basis} · {support.resampling}</p>
      <p>Mars source CRS: {support.planetary_source_crs} · comparison CRS: {support.planetary_crs}</p>
      <p>Earth source CRS: {support.earth_source_crs} · comparison CRS: {support.earth_crs}</p>
      <p>Map cell support: {support.pixel_width_m} × {support.pixel_height_m} m · ScaleBridge run {support.scale_bridge_run_id}</p>
      <p>Valid coverage: Mars {(support.coverage.planetary_fraction * 100).toFixed(3)}% · Earth {(support.coverage.earth_fraction * 100).toFixed(2)}% · paired {support.coverage.common_fraction === null ? "not defined for unequal supports" : `${(support.coverage.common_fraction * 100).toFixed(3)}%`}</p>
      <p>{support.vertical_comparison}</p><p>{support.warning}</p>
      {Object.entries(support.information_loss).map(([body, note]) => <p key={body}>{body}: {note}</p>)}
    </section>
    {data.warnings.map((warning) => <p key={warning} className="text-xs text-amber-200">{warning}</p>)}

    <section className="space-y-4">
      {Object.entries(data.feature_maps).map(([feature, maps]) => {
        const item = candidate.feature_comparisons[feature];
        return <article key={feature} className="rounded-lg border border-slate-700 bg-slate-900/70 p-4">
          <h2 className="font-medium capitalize">{feature.replaceAll("_", " ")}</h2>
          <p className="mt-1 text-xs text-slate-400">{item?.method ?? "Feature comparison unavailable"}</p>
          <div className="mt-3 grid gap-3 md:grid-cols-2">
            {([["Mars reference", maps.mars_preview_url], ["Earth candidate region", maps.earth_preview_url]] as const).map(([label, path]) => <figure key={label}>
              <figcaption className="mb-1 text-xs text-slate-400">{label}</figcaption>
              <img className="aspect-square h-64 w-full rounded border border-slate-700 bg-slate-950 object-contain md:h-72" src={mapUrl(path)} alt={`${feature.replaceAll("_", " ")} map for ${label}`} />
            </figure>)}
          </div>
          <dl className="mt-3 grid gap-2 text-xs sm:grid-cols-4">
            {feature === "landform_morphology" ? <div className="sm:col-span-2"><dt className="text-slate-500">Relative low / neutral / high class fractions · Mars / Earth</dt><dd className="font-mono">{([-1, 0, 1] as const).map((code) => `${code}: ${item?.reference_class_fractions[String(code)] == null ? "—" : `${(item.reference_class_fractions[String(code)] * 100).toFixed(1)}%`} / ${item?.candidate_class_fractions[String(code)] == null ? "—" : `${(item.candidate_class_fractions[String(code)] * 100).toFixed(1)}%`}`).join(" · ")}</dd></div> : <div><dt className="text-slate-500">Median · Mars / Earth</dt><dd className="font-mono">{number(item?.reference_median)} / {number(item?.candidate_median)} {item?.units}</dd></div>}
            <div><dt className="text-slate-500">Normalized distribution distance</dt><dd className="font-mono">{number(item?.normalized_distance)}</dd></div>
            <div><dt className="text-slate-500">Valid samples · Mars / Earth</dt><dd className="font-mono">{item ? `${item.reference_sample_count.toLocaleString()} / ${item.candidate_sample_count.toLocaleString()}` : "Unavailable"}</dd></div>
            <div><dt className="text-slate-500">Profile evidence gate</dt><dd className="font-mono">{(data.coverage.minimum_required_coverage * 100).toFixed(1)}%</dd></div>
          </dl>
          <details className="mt-3 rounded border border-slate-700 p-3">
            <summary className="cursor-pointer text-xs text-slate-300">Measured distribution statistics</summary>
            <div className="mt-2 grid gap-3 sm:grid-cols-2">
              {([["Mars reference", item?.reference_summary], ["Earth candidate", item?.candidate_summary]] as const).map(([label, summary]) => <div key={label}>
                <h3 className="text-xs text-slate-400">{label} · {item?.units}</h3>
                {summary && Object.keys(summary).length ? <dl className="mt-1 grid grid-cols-2 gap-x-4 gap-y-1 font-mono text-[11px]">
                  {Object.entries(summary).map(([name, value]) => <div key={name}><dt className="inline text-slate-500">{name.replaceAll("_", " ")}: </dt><dd className="inline">{value?.toPrecision(5)}</dd></div>)}
                </dl> : <p className="mt-1 text-xs text-amber-200">Unavailable: insufficient valid feature samples.</p>}
              </div>)}
            </div>
          </details>
        </article>;
      })}
    </section>
    <nav className="flex flex-wrap gap-2">
      <Link className="rounded border border-slate-600 px-3 py-2 text-sm" href="/discovery">Back to discovery</Link>
      <Link className="rounded border border-cyan-800 px-3 py-2 text-sm text-cyan-200" href={`/candidates/${candidateId}/passport`}>Open Evidence Passport</Link>
      <Link className="rounded border border-slate-600 px-3 py-2 text-sm" href="/terrain-twin">Open Terrain Twin</Link>
    </nav>
  </div>;
}
