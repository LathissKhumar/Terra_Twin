import Link from "next/link";

export default function TerrainComparisonIndex() {
  return <section className="space-y-4"><p className="font-mono text-xs uppercase tracking-[.2em] text-cyan-300">Terrain comparison</p><h1 className="text-3xl font-semibold">Compare processed terrain evidence</h1><p className="max-w-2xl text-sm leading-6 text-slate-400">Feature maps and numerical distributions are attached to each actual candidate comparison. Select a completed discovery run, then open a candidate comparison from its result card.</p><Link href="/discovery" className="inline-flex rounded bg-cyan-400 px-4 py-2 text-sm font-semibold text-slate-950">Open discovery results</Link></section>;
}
