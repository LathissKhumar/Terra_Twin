import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "TerraTwin | Project foundation",
  description: "Planetary Analogue Discovery and Terrain Intelligence Platform",
};
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return <html lang="en" className="dark"><body>
    <a href="#main" className="sr-only focus:not-sr-only focus:p-4">Skip to content</a>
    <header className="border-b border-border px-6 py-5">
      <span className="text-lg font-semibold tracking-wide">TerraTwin</span>
      <span className="ml-4 text-sm text-slate-400">Project foundation</span>
    </header>
    <main id="main" className="mx-auto max-w-4xl px-6 py-12">{children}</main>
  </body></html>;
}

