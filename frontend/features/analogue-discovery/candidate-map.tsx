"use client";

import { useEffect, useRef, useState } from "react";
import {
  LngLatBounds,
  Map as MapLibreMap,
  NavigationControl,
  ScaleControl,
  setWorkerUrl,
  type GeoJSONSource,
} from "maplibre-gl";
import { useRouter } from "next/navigation";
import type { Candidate } from "@/lib/product-api";

export function CandidateMap({ candidates }: { candidates: Candidate[] }) {
  const router = useRouter();
  const node = useRef<HTMLDivElement>(null);
  const map = useRef<MapLibreMap | null>(null);
  const [mapReady, setMapReady] = useState(false);
  const [mapError, setMapError] = useState<string | null>(null);
  useEffect(() => {
    if (!node.current) return;
    // MapLibre GL JS v6 requires an explicit worker URL when bundled by webpack.
    // Next.js emits this module as a same-origin static asset.
    setWorkerUrl(new URL("maplibre-gl/dist/maplibre-gl-worker.mjs", import.meta.url).toString());
    const instance = new MapLibreMap({
      container: node.current,
      // OpenFreeMap's public Liberty style is a real worldwide basemap and
      // carries its own required OpenMapTiles/OpenStreetMap attribution.
      // Deployments can replace the URL without a provider API key.
      style: process.env.NEXT_PUBLIC_MAP_STYLE_URL || "https://tiles.openfreemap.org/styles/liberty",
      center: [0, 0], zoom: 1, attributionControl: { compact: true },
    });
    instance.addControl(new NavigationControl({ showCompass: true }), "top-right");
    instance.addControl(new ScaleControl({ unit: "metric" }), "bottom-left");
    instance.once("load", () => setMapReady(true));
    instance.on("error", (event) => {
      if (event.error) setMapError("The basemap could not be fully loaded. Candidate boundaries remain tied to the returned TerraTwin results.");
    });
    map.current = instance;
    const resizeObserver = new ResizeObserver(() => instance.resize());
    resizeObserver.observe(node.current);
    return () => { resizeObserver.disconnect(); instance.remove(); map.current = null; };
  }, []);
  useEffect(() => {
    const instance = map.current;
    if (!instance) return;
    const update = () => {
      const collection = {
        type: "FeatureCollection" as const,
        features: candidates.flatMap((candidate) => {
          const polygon = [...candidate.geographic_boundary_wgs84];
          if (polygon.length < 3) return [];
          const first = polygon[0];
          const last = polygon[polygon.length - 1];
          if (first[0] !== last[0] || first[1] !== last[1]) polygon.push(first);
          return [{
            type: "Feature" as const,
            properties: { id: candidate.candidate_id, ranking: candidate.ranking, status: candidate.status },
            geometry: { type: "Polygon" as const, coordinates: [polygon] },
          }];
        }),
      };
      const existing = instance.getSource("candidates") as GeoJSONSource | undefined;
      if (existing) existing.setData(collection);
      else {
        instance.addSource("candidates", { type: "geojson", data: collection });
        instance.addLayer({ id: "candidate-fill", type: "fill", source: "candidates", paint: { "fill-color": ["case", ["==", ["get", "status"], "eligible"], "#22d3ee", "#f59e0b"], "fill-opacity": 0.32 } });
        instance.addLayer({ id: "candidate-outline", type: "line", source: "candidates", paint: { "line-color": ["case", ["==", ["get", "status"], "eligible"], "#67e8f9", "#fbbf24"], "line-width": 2 } });
        instance.on("click", "candidate-fill", (event) => {
          const feature = event.features?.[0];
          const id = feature?.properties?.id;
          if (typeof id === "string") router.push(`/candidates/${encodeURIComponent(id)}/comparison`);
        });
        instance.on("mouseenter", "candidate-fill", () => { instance.getCanvas().style.cursor = "pointer"; });
        instance.on("mouseleave", "candidate-fill", () => { instance.getCanvas().style.cursor = ""; });
      }
      if (collection.features.length) {
        const coordinates = collection.features.flatMap((feature) => feature.geometry.coordinates[0]);
        const first = coordinates[0] as [number, number];
        const bounds = coordinates.reduce(
          (acc, coordinate) => acc.extend(coordinate as [number, number]),
          new LngLatBounds(first, first),
        );
        instance.fitBounds(bounds, { padding: 56, maxZoom: 14, duration: 0 });
      }
    };
    if (instance.isStyleLoaded()) update(); else instance.once("load", update);
    return () => { instance.off("load", update); };
  }, [candidates, router]);
  return (
    <div className="space-y-2">
      <div className="relative h-[360px] overflow-hidden rounded border border-slate-700 bg-[#07111c]" role="region" aria-label="Map showing returned candidate boundaries">
        <div ref={node} className="absolute inset-0" />
        {mapReady && <div className="pointer-events-none absolute left-3 top-3 flex flex-wrap gap-3 rounded border border-slate-600 bg-slate-950/90 px-3 py-2 text-[11px] text-slate-200 shadow">
          <span className="flex items-center gap-1.5"><i className="h-2.5 w-2.5 rounded-sm border border-cyan-300 bg-cyan-400/60" />Eligible candidate</span>
          <span className="flex items-center gap-1.5"><i className="h-2.5 w-2.5 rounded-sm border border-amber-300 bg-amber-400/60" />Insufficient evidence</span>
        </div>}
        {!mapReady && !mapError && <p role="status" className="absolute inset-x-0 bottom-3 mx-auto w-fit rounded bg-slate-950/90 px-3 py-2 text-xs text-slate-200">Loading interactive candidate map…</p>}
        {mapError && <p role="alert" className="absolute bottom-3 left-3 rounded border border-rose-800 bg-slate-950/95 px-3 py-2 text-xs text-rose-200">{mapError}</p>}
        {mapReady && candidates.length === 0 && <p className="absolute inset-0 grid place-items-center bg-slate-950/40 text-sm text-slate-200">No candidate footprints for this result set.</p>}
      </div>
      <p className="text-xs text-slate-500">{candidates.length} actual candidate footprints · basemap is for geographic context only · click a footprint to inspect its comparison.</p>
    </div>
  );
}

