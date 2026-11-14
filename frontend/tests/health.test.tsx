import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { HealthPanel } from "@/components/health-panel";
import { api } from "@/lib/api-client";
import { healthy } from "./health-fixture";
import ErrorBoundary from "@/app/error";

describe("health panel", () => {
  it("renders pending and then real service status", async () => {
    vi.spyOn(api, "getHealth").mockResolvedValue(healthy);
    render(<HealthPanel />);
    expect(screen.getByRole("status")).toHaveTextContent("Checking");
    expect(await screen.findByText("Services ready")).toBeInTheDocument();
    expect(screen.getByText("Connected")).toBeInTheDocument();
  });
  it("handles failure and successful retry", async () => {
    vi.spyOn(api, "getHealth").mockRejectedValueOnce(new Error("offline")).mockResolvedValue(healthy);
    render(<HealthPanel />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Backend unavailable");
    fireEvent.click(screen.getByRole("button", { name: "Check again" }));
    expect(await screen.findByText("Services ready")).toBeInTheDocument();
  });
  it("discloses degraded dependencies", async () => {
    vi.spyOn(api, "getHealth").mockResolvedValue({
      ...healthy, status: "degraded", database: { ...healthy.database, postgis_available: false },
    });
    render(<HealthPanel />);
    expect(await screen.findByText("Services degraded")).toBeInTheDocument();
    expect(screen.getByText("Unavailable")).toBeInTheDocument();
  });
  it("offers error boundary recovery without exposing errors", () => {
    const reset = vi.fn();
    render(<ErrorBoundary error={new Error("secret")} reset={reset} />);
    expect(screen.queryByText("secret")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(reset).toHaveBeenCalledOnce();
  });
});

