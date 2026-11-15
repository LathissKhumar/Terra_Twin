import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./tests/e2e", workers: 1,
  use: { baseURL: process.env.PLAYWRIGHT_BASE_URL || "http://127.0.0.1:3000",
    launchOptions: {
      executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE,
      args: ["--enable-webgl", "--use-gl=angle", "--use-angle=swiftshader"],
    } },
  webServer: process.env.LIVE_STACK === "1" ? undefined : {
    command: "npm run start", url: "http://127.0.0.1:3000", reuseExistingServer: !process.env.CI },
});

