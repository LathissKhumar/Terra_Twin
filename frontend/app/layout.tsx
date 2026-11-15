import type { Metadata } from "next";
import "./globals.css";
import "maplibre-gl/dist/maplibre-gl.css";
import Link from "next/link";

export const metadata: Metadata = {
  title: "TerraTwin | Planetary terrain intelligence",
  description: "Planetary Analogue Discovery and Terrain Intelligence Platform",
};
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return <html lang="en" className="dark"><body>
    <a href="#main" className="sr-only focus:not-sr-only focus:p-4">Skip to content</a>
    <header className="border-b border-border px-6 py-4">
      <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4">
       <Link href="/" className="text-lg font-semibold tracking-wide">TerraTwin</Link>
       <nav aria-label="Main navigation" className="flex flex-wrap gap-2 text-sm text-slate-300">
        <Link className="rounded px-3 py-2 hover:bg-slate-800" href="/missions">Mission Explorer</Link>
        <Link className="rounded px-3 py-2 hover:bg-slate-800" href="/discovery">Analogue Discovery</Link>
        <Link className="rounded px-3 py-2 hover:bg-slate-800" href="/terrain-comparison">Terrain Comparison</Link>
        <Link className="rounded px-3 py-2 hover:bg-slate-800" href="/terrain-twin">Terrain Twin</Link>
       </nav>
      </div>
    </header>
    <main id="main" className="mx-auto max-w-7xl px-6 py-8">{children}</main>
  </body></html>;
}

