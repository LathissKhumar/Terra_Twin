import { expect, it, vi } from "vitest";
import { api } from "@/lib/api-client";
import { healthy } from "./health-fixture";
it("accepts valid readiness response", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify(healthy))));
  expect(await api.getHealth()).toEqual(healthy);
});
it("accepts structured degraded status", async () => {
  const body = { ...healthy, status: "degraded", database: {
    ...healthy.database, connected: false, postgis_available: false } };
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status: 503 })));
  expect((await api.getHealth()).status).toBe("degraded");
});
it.each([{}, { ...healthy, status: "invented" }, { ...healthy, database: {} }])(
  "rejects malformed responses", async body => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify(body))));
    await expect(api.getHealth()).rejects.toThrow("Invalid health response");
  });
it("handles non-JSON server errors without reading the body twice", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("error", { status: 500 })));
  await expect(api.getHealth()).rejects.toMatchObject({ status: 500 });
});
it("handles offline backend", async () => {
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));
  await expect(api.getHealth()).rejects.toMatchObject({ status: 0 });
});

