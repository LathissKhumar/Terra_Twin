import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { EvidencePassportReport } from "@/features/evidence-passport/evidence-passport-report";

describe("Evidence Passport report", () => {
  it("shows backend loading and structured error states", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: false,
      status: 503,
      json: async () => ({ detail: "discovery report unavailable" }),
    }));
    render(<EvidencePassportReport candidateId="actual-candidate-id" />);
    expect(screen.getByRole("status")).toHaveTextContent("Loading the stored evidence passport");
    expect(await screen.findByRole("alert")).toHaveTextContent("discovery report unavailable");
  });
});
