// @ts-check
const { defineConfig } = require("@playwright/test");

module.exports = defineConfig({
  testDir: "./tests",
  fullyParallel: false,
  workers: 1,
  retries: 1,
  timeout: 60_000,
  expect: { timeout: 15_000 },
  use: {
    baseURL: "http://127.0.0.1:8000",
    actionTimeout: 15_000,
    serviceWorkers: "block",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    // Pre-dismiss onboarding (welcome strip + guided tour) so neither blocks
    // test interactions. Production first-run users still get them.
    storageState: {
      cookies: [],
      origins: [{
        origin: "http://127.0.0.1:8000",
        localStorage: [
          { name: "zr_welcomed", value: "1" },
          { name: "zr_tour_done", value: "1" },
        ],
      }],
    },
  },
  webServer: {
    command: "ZAMEENRENTALS_PLAYWRIGHT=1 uvicorn main:app --port 8000",
    port: 8000,
    timeout: 15_000,
    reuseExistingServer: !process.env.CI,
  },
  projects: [
    {
      name: "chromium",
      use: { browserName: "chromium", viewport: { width: 1440, height: 900 } },
    },
    {
      name: "mobile-chromium",
      use: { browserName: "chromium", viewport: { width: 375, height: 812 } },
    },
  ],
});
