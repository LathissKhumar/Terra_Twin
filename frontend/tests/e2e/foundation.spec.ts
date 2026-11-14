import { expect, test } from "@playwright/test";
test("workspace connects to the real backend", {
  annotation: { type: "integration", description: "Requires LIVE_STACK=1 and Compose" },
}, async ({ page }) => {
  test.skip(process.env.LIVE_STACK !== "1", "Run against Compose with LIVE_STACK=1");
  await page.goto("/");
  await expect(page.getByText("Services ready")).toBeVisible();
  await expect(page.getByText("Connected", { exact: true })).toBeVisible();
  await expect(page.getByText("Available", { exact: true })).toBeVisible();
});
test("workspace starts when backend is offline", async ({ page }) => {
  await page.route("**/api/v1/health", route => route.abort());
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await expect(page.getByRole("region", { name: "Service status" }).getByRole("alert"))
    .toContainText("Backend unavailable");
  await expect(page.getByText("No datasets loaded.", { exact: false })).toBeVisible();
});

