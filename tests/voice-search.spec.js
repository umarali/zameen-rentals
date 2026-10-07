// @ts-check
const { test, expect } = require("@playwright/test");

// Chromium's fake mic plays a tone, so the recording never goes silent; the
// test stops it by tapping the button. The Playwright server returns a fixed
// transcript ("2 bed flat in Clifton under 50k") instead of running Whisper.
test.use({
  permissions: ["microphone"],
  launchOptions: {
    args: ["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream"],
  },
});

test.describe("Voice search", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await page.waitForSelector(".card-wrap", { timeout: 30000 });
    await page.locator('.city-tab[data-city="karachi"]').click();
    await page.waitForSelector(".card-wrap", { timeout: 30000 });
  });

  test("mic button appears next to search", async ({ page }) => {
    const mic = page.locator("#nlMicBtn");
    await expect(mic).toBeVisible();
    await expect(mic).toHaveAttribute("aria-label", "Search by voice");
  });

  test("recording, transcript and filters", async ({ page }) => {
    const mic = page.locator("#nlMicBtn");
    await mic.click();
    await expect(mic).toHaveAttribute("aria-pressed", "true");
    await expect(page.locator("#nlParsed")).toContainText("0:0");
    await page.waitForTimeout(1200);

    const transcribe = page.waitForRequest(r => r.url().includes("/api/voice/transcribe") && r.method() === "POST");
    await mic.click();
    const req = await transcribe;
    expect(req.url()).toContain("city=karachi");
    expect(req.headers()["content-type"]).toMatch(/^audio\//);

    await expect(page.locator("#nlInput")).toHaveValue("2 bed flat in Clifton under 50k");
    await expect(mic).toHaveAttribute("aria-pressed", "false");
    await expect(page.locator("#nlUnderstood")).toBeVisible();
    await expect(page.locator("#nlUnderstood")).toContainText("Clifton");
  });

  test("server error is shown inline", async ({ page }) => {
    await page.route("**/api/voice/transcribe**", route =>
      route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ detail: "Voice search is busy. Please try again." }) }));
    const mic = page.locator("#nlMicBtn");
    await mic.click();
    await page.waitForTimeout(800);
    await mic.click();
    await expect(page.locator("#nlParsed")).toContainText("busy");
    await expect(mic).toBeEnabled();
  });
});

test.describe("Voice search disabled", () => {
  test("no mic when the server has voice off", async ({ page }) => {
    await page.route("**/api/voice/status", route =>
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ enabled: false }) }));
    await page.goto("/");
    await page.waitForSelector(".card-wrap", { timeout: 30000 });
    await expect(page.locator("#nlMicBtn")).toHaveCount(0);
  });
});
