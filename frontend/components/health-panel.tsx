"use client";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api-client";
import type { HealthResponse } from "@/types/api";

export function HealthPanel() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [error, setError] = useState(false);
  const [loading, setLoading] = useState(true);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    api.getHealth(controller.signal).then(data => {
      if (!controller.signal.aborted) setHealth(data);
    }).catch(() => {
      if (!controller.signal.aborted) setError(true);
    }).finally(() => {
      if (!controller.signal.aborted) setLoading(false);
    });
    return () => controller.abort();
  }, [attempt]);
  function refresh() {
    setLoading(true); setError(false); setHealth(null); setAttempt(value => value + 1);
  }
  return <section className="mt-8 rounded border border-border bg-card p-6" aria-labelledby="health-heading">
    <h2 id="health-heading" className="text-lg font-medium">Service status</h2>
    <div className="my-4" aria-live="polite">
      {loading && <p role="status">Checking backend connection…</p>}
      {!loading && error && <p role="alert" className="text-amber-300">Backend unavailable. The workspace is still accessible.</p>}
      {!loading && health && <>
        <p className={health.status === "healthy" ? "text-cyan-300" : "text-amber-300"}>
          {health.status === "healthy" ? "Services ready" : "Services degraded"}
        </p>
        <dl className="mt-3 grid grid-cols-2 gap-2 text-sm">
          <dt>Database</dt><dd>{health.database.connected ? "Connected" : "Unavailable"}</dd>
          <dt>PostGIS</dt><dd>{health.database.postgis_available ? "Available" : "Unavailable"}</dd>
          <dt>API version</dt><dd>{health.version}</dd>
        </dl>
      </>}
    </div>
    <Button variant="outline" onClick={refresh} disabled={loading}>Check again</Button>
  </section>;
}

