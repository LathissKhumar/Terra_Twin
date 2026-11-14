import { HealthPanel } from "@/components/health-panel";
export default function Home() {
  return <>
    <p className="font-mono text-sm uppercase tracking-widest text-cyan-400">Phase 1</p>
    <h1 className="mt-3 text-3xl font-semibold">Terrain intelligence starts with evidence.</h1>
    <p className="mt-4 max-w-2xl leading-relaxed text-slate-300">
      TerraTwin will compare planetary and terrestrial elevation data for field experiments.
      This foundation checks application connectivity. Dataset processing and terrain analysis
      are not available yet.
    </p>
    <HealthPanel />
    <section className="mt-8 rounded border border-border p-6" aria-labelledby="evidence-heading">
      <h2 id="evidence-heading" className="text-lg font-medium">Scientific evidence</h2>
      <p className="mt-2 text-slate-400">No datasets loaded. No candidates, measurements, or validation results exist.</p>
    </section>
  </>;
}

