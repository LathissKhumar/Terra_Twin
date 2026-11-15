import { HealthPanel } from "@/components/health-panel";
import Link from "next/link";

export default function Home() {
  return (
    <div className="space-y-8">
      <header className="max-w-3xl space-y-3"><p className="font-mono text-xs uppercase tracking-[.2em] text-cyan-300">Planetary analogue discovery & terrain intelligence</p><h1 className="text-4xl font-semibold tracking-tight">TerraTwin scientific workspace</h1><p className="text-sm leading-6 text-slate-400">Run a provenance-preserving comparison from genuine elevation products, inspect the actual candidate evidence, reconstruct a selected Earth window, and export its deterministic field-test assessment.</p></header>
      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">{[
        ["Mission Explorer", "Inspect available planetary and Earth sources and configure the study support.", "/missions"],
        ["Analogue Discovery", "Run and resume persisted ScaleBridge and terrain comparison jobs.", "/discovery"],
        ["Terrain Comparison", "Inspect actual feature rasters, distributions, coverage and limitations.", "/terrain-comparison"],
        ["Terrain Twin", "Generate a DEM-derived mesh and inspect its validation status.", "/terrain-twin"],
      ].map(([title, description, href]) => <Link href={href} key={href} className="rounded-lg border border-slate-700 bg-slate-900/70 p-5 transition hover:border-cyan-800"><h2 className="font-medium text-slate-100">{title}</h2><p className="mt-2 text-sm leading-5 text-slate-400">{description}</p><span className="mt-4 inline-block text-xs text-cyan-300">Open workspace →</span></Link>)}</section>
      <section className="rounded-lg border border-slate-700 bg-slate-900/60 p-5"><h2 className="font-medium">Scientific result integrity</h2><p className="mt-2 max-w-4xl text-sm leading-6 text-slate-400">The Earth search footprint is limited to local, checksum-verified source coverage. Candidates that do not meet the configured evidence gates remain unranked. A terrain mesh without an independent reference is marked UNVALIDATED. The UI never creates sample values or candidate markers.</p></section>
      <section aria-label="Backend connectivity" className="border-t border-slate-800 pt-5"><HealthPanel /></section>
    </div>
  );
}
