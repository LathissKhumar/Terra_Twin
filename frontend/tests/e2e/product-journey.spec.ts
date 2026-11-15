import { expect, test } from "@playwright/test";

test("workspace remains available and reports API unavailability", async ({ page }) => {
  await page.route("**/api/v1/**", (route) => route.abort());
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "TerraTwin scientific workspace" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Service status" }).getByRole("alert"))
    .toContainText("Backend unavailable");
  await expect(page.getByRole("navigation", { name: "Main navigation" }).getByRole("link", { name: "Mission Explorer", exact: true })).toBeVisible();
});

test("opens the saved validated Terrain Twin with real discovery evidence", async ({ page }) => {
  test.skip(process.env.LIVE_STACK !== "1", "Requires the persisted real DEM discovery and Terrain Twin artifacts");
  await page.goto("/terrain-twin");
  await expect(page.getByLabel("Select an actual Earth search candidate")).not.toHaveValue("");
  await expect(page.getByLabel("Discovery comparison evidence")).toContainText("Weighted distance");
  await expect(page.getByLabel("Select an independent Earth elevation reference")).not.toHaveValue("");
  await expect(page.getByText("VALIDATED", { exact: true })).toBeVisible({ timeout: 60_000 });
  await expect(page.getByLabel("Independent validation metrics")).toContainText("MAE");
  await expect(page.locator("[data-mesh-status=loaded]")).toBeVisible({ timeout: 60_000 });
  await expect(page.locator("canvas")).toHaveCount(1);
  const verticalScale = page.getByLabel("Vertical display exaggeration");
  await expect(verticalScale).toHaveValue("6");
  await expect(page.getByText(/display transform only; the exported mesh remains/)).toBeVisible();
  await verticalScale.focus();
  await page.keyboard.press("ArrowRight");
  await expect(verticalScale).toHaveValue("7");
  await expect(page.locator("[data-mesh-status=loaded]")).toHaveAttribute(
    "data-vertical-display-scale",
    "7",
  );
  await expect(page.getByRole("figure").filter({ hasText: "Cells included in independent DEM comparison" }))
    .toContainText("valid cells");
  await expect(page.getByText("The mask is not elevation or error data.")).toBeVisible();
});

test("shows genuine Mars and Earth feature maps and measured comparison values", async ({ page }) => {
  test.skip(process.env.LIVE_STACK !== "1", "Requires completed, checksum-verified planetary and Earth processing");
  await page.goto("/discovery");
  await expect(page.getByRole("heading", { name: "4 · Actual returned candidates" })).toBeVisible({ timeout: 60_000 });
  const first = page.locator("article").filter({ has: page.getByRole("link", { name: "Feature comparison" }) }).first();
  await expect(first).toContainText("Rank 1");
  await first.getByRole("link", { name: "Feature comparison" }).click();
  await expect(page.getByRole("heading", { name: "Terrain feature comparison" })).toBeVisible();
  await expect(page.getByText(/Mars: HiRISE stereo-derived Jezero DTM/)).toBeVisible();
  await expect(page.getByText(/Earth: USGS 1 Meter bare-earth DEM/)).toBeVisible();
  await expect(page.getByText(/Mars source CRS: EQUIRECTANGULAR MARS/)).toBeVisible();
  const features = page.locator("article");
  await expect(features).toHaveCount(7);
  for (const image of await page.locator("article img").all()) {
    await expect(image).toBeVisible();
    const dimensions = await image.evaluate((element: HTMLImageElement) => [element.naturalWidth, element.naturalHeight]);
    expect(dimensions[0]).toBeGreaterThan(0);
    expect(dimensions[1]).toBeGreaterThan(0);
  }
  await expect(page.locator("article").first()).toContainText("Median · Mars / Earth");
  await expect(page.locator("article").first()).toContainText("Normalized distribution distance");
  await expect(page.locator("article").first()).toContainText("Valid samples · Mars / Earth");
  await expect(page.locator("article").last()).toContainText("Relative low / neutral / high class fractions");
});

test("coarse MOLA selection receives resolution-aware search defaults", async ({ page }) => {
  test.skip(process.env.LIVE_STACK !== "1", "Requires the locally ingested MOLA reference raster");
  await page.goto("/discovery");
  await expect(page.getByRole("heading", { name: /Mission Explorer & Analogue Discovery/ })).toBeVisible();
  await page.getByLabel("Validated source dataset").first().selectOption("14022166079edafc99650f354e5a634e6eb2c2ea544b444c01cd8ee55437df36");
  await expect(page.getByLabel("Planetary reference width & height (m)")).toHaveValue("50000");
  await expect(page.getByLabel("Candidate window width & height (m)")).toHaveValue("5000");
  await expect(page.getByLabel("Candidate stride (m)")).toHaveValue("2500");
  await expect(page.getByText(/MOLA MEGDR is coarse and has sparse direct observations/)).toBeVisible();
});

test("runs and inspects an actual Mars-to-Earth workflow", async ({ page }) => {
  test.skip(process.env.LIVE_STACK !== "1", "Requires real local DEMs and a healthy Compose stack");
  await page.goto("/missions");
  await expect(page.getByText(/checksum-verified local source/).first())
    .toHaveText(/[1-9]\d* checksum-verified local source\(s\)/);
  await expect(page.getByLabel("Planetary body")).toHaveValue("mars");
  await expect(page.getByLabel("Reference region")).toHaveValue("jezero_crater");
  await expect(page.getByLabel("Validated source dataset").first().locator("option:checked"))
    .toContainText("HiRISE stereo-derived Jezero DTM");
  await expect(page.getByRole("button", { name: "Run ScaleBridge + discovery" })).toBeEnabled();
  await page.getByLabel("Comparison support width & height (m)").fill("10000");
  const submissionResponse = page.waitForResponse((response) =>
    response.request().method() === "POST" && response.url().endsWith("/discovery/jobs"),
  );
  await page.getByRole("button", { name: "Run ScaleBridge + discovery" }).click();
  const response = await submissionResponse;
  expect(response.status()).toBe(202);
  const submittedJob = await response.json();
  expect(submittedJob.reused_existing_job).toBe(false);

  await expect(page.getByRole("heading", { name: "3 · Persisted discovery job" })).toBeVisible();
  const jobId = submittedJob.job_id as string;
  await expect(page.locator("section[aria-live='polite'] p.font-mono")).toHaveText(jobId);
  await page.reload();
  await expect(page.getByRole("heading", { name: "3 · Persisted discovery job" })).toBeVisible();
  await expect(page.locator("section[aria-live='polite'] p.font-mono")).toHaveText(jobId);
  await expect(page.getByText("succeeded", { exact: true }).first()).toBeVisible({ timeout: 60_000 });
  const reportResponse = await page.request.get(`http://localhost:8000/api/v1/discovery/jobs/${jobId}/report`);
  expect(reportResponse.status()).toBe(200);
  const report = await reportResponse.json();
  expect(report.planetary_source_product).toContain("HiRISE");
  expect(report.generated_window_count).toBeGreaterThan(0);
  expect(report.ranked_candidate_count).toBeGreaterThan(0);
  await expect(page.getByRole("heading", { name: "4 · Actual returned candidates" })).toBeVisible();
  await expect(page.getByText(/Searched WGS84 boundary:/)).toBeVisible();
  const candidateMap = page.getByRole("region", { name: "Map showing returned candidate boundaries" });
  await expect(candidateMap).toBeVisible();
  await expect(candidateMap.locator(".maplibregl-ctrl-attrib")).toContainText("OpenStreetMap", { timeout: 20_000 });
  const mapCanvas = candidateMap.locator("canvas.maplibregl-canvas");
  await expect(mapCanvas).toBeVisible();
  await expect(page.getByText(/actual candidate footprints/)).toBeVisible();
  await mapCanvas.scrollIntoViewIfNeeded();
  const canvasBounds = await mapCanvas.boundingBox();
  expect(canvasBounds?.width).toBeGreaterThan(0);
  expect(canvasBounds?.height).toBeGreaterThan(0);
  await mapCanvas.click({ position: { x: canvasBounds!.width / 2, y: canvasBounds!.height / 2 } });
  await expect(page).toHaveURL(/\/candidates\/[0-9a-f]{24}\/comparison$/);
  await page.goto("/discovery");

  const firstCandidate = page.locator("article").filter({ has: page.getByRole("link", { name: "Feature comparison" }) }).first();
  const comparisonLink = firstCandidate.getByRole("link", { name: "Feature comparison" });
  const href = await comparisonLink.getAttribute("href");
  expect(href).toMatch(/^\/candidates\/[0-9a-f]{24}\/comparison$/);
  await comparisonLink.click();
  await expect(page.getByRole("heading", { name: "Terrain feature comparison" })).toBeVisible();
  await expect(page.getByRole("img", { name: /slope map for Mars reference/i })).toBeVisible();
  await expect(page.getByText(/Feature coverage · Mars \/ Earth/).first()).toBeVisible();

  const candidateId = href!.split("/")[2];
  await page.goto(`/candidates/${candidateId}/passport`);
  await expect(page.getByRole("heading", { name: "Candidate evidence record" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Measured feature comparisons" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Export JSON" })).toHaveAttribute("href", /format=json/);
  await expect(page.getByRole("link", { name: "Export PDF" })).toHaveAttribute("href", /format=pdf/);

  await page.goto("/terrain-twin");
  await expect(page.getByLabel("Select an actual Earth search candidate")).not.toHaveValue("");
  await expect(page.getByLabel("Discovery comparison evidence")).toContainText("Weighted distance");
  await expect(page.getByLabel("Select an independent Earth elevation reference")).not.toHaveValue("");
  await page.getByRole("button", { name: "Build terrain mesh" }).click();
  await expect(page.getByRole("heading", { name: "Reconstruction metadata" })).toBeVisible({ timeout: 60_000 });
  await expect(page.getByText("VALIDATED", { exact: true })).toBeVisible();
  await expect(page.getByLabel("Independent validation metrics")).toContainText("MAE");
  await expect(page.locator("[data-mesh-status=loaded]")).toBeVisible({ timeout: 60_000 });
  await expect(page.locator("canvas")).toHaveCount(1);
});
