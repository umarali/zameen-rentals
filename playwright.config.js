// @ts-check
const { defineConfig } = require("@playwright/test");

// Override when 8000 is taken by a dev server: PLAYWRIGHT_PORT=8100 npx playwright test
const PORT = Number(process.env.PLAYWRIGHT_PORT || 8000);
const ORIGIN = `http://127.0.0.1:${PORT}`;

module.exports = defineConfig({
  testDir: "./tests",
  fullyParallel: false,
  workers: 1,
  retries: 1,
  timeout: 60_000,
  expect: { timeout: 15_000 },
  use: {
    headless: true,
    baseURL: ORIGIN,
    actionTimeout: 15_000,
    serviceWorkers: "block",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    // Pre-dismiss onboarding (welcome strip + guided tour) so neither blocks
    // test interactions. Production first-run users still get them.
    storageState: {
      cookies: [],
      origins: [{
        origin: ORIGIN,
        localStorage: [
          { name: "zr_welcomed", value: "1" },
          { name: "zr_tour_done", value: "1" },
        ],
      }],
    },
  },
  webServer: {
    command: "python3 tests/serve_playwright.py",
    port: PORT,
    timeout: 15_000,
    reuseExistingServer: false,
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
