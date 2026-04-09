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
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },
  webServer: {
    command: "uvicorn main:app --port 8000",
    port: 8000,
    reuseExistingServer: false,
    timeout: 15_000,
  },
  projects: [
    {
      name: "chromium",
      use: { browserName: "chromium", viewport: { width: 1440, height: 900 } },
    },
  ],
});
