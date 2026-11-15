import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { DiscoveryWorkspace } from "@/features/analogue-discovery/discovery-workspace";

vi.mock("@/features/analogue-discovery/candidate-map", () => ({ CandidateMap: () => null }));

const emptyMissions = {
  mission_profiles: [], supported_bodies: [], reference_regions: [], earth_search_defaults: [], unavailable_bodies: ["mars", "moon"],
};

describe("DiscoveryWorkspace API integration states", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/missions")) return Response.json(emptyMissions);
      if (url.endsWith("/datasets")) return Response.json({ adapters: {}, datasets: [], storage_limit_bytes: 1 });
      if (url.includes("/discovery/jobs")) return Response.json({ items: [], total: 0 });
      return Response.json({ error: { message: "unavailable" } }, { status: 503 });
    }));
  });

  it("shows a truthful no-source state without invented candidates", async () => {
    render(<DiscoveryWorkspace />);
    expect(await screen.findAllByText(/No checksum-verified .* source is available/i)).toHaveLength(2);
    expect(screen.getByText(/Planetary bodies without locally available sources/i)).toBeInTheDocument();
    expect(screen.queryByText(/Rank 1/)).not.toBeInTheDocument();
  });

  it("surfaces backend request errors instead of hiding them", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => Response.json({ error: { message: "database unavailable" } }, { status: 503 })));
    render(<DiscoveryWorkspace />);
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("database unavailable"));
  });
});
