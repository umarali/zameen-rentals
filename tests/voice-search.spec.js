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
    const parseQuery = page.waitForRequest(r => r.url().includes("/api/parse-query?"));
    await mic.click();
    const req = await transcribe;
    expect(req.url()).toContain("city=karachi");
    expect(req.headers()["content-type"]).toMatch(/^audio\//);

    // Applying the area intentionally clears nlInput. Verify the transcript
    // sent to parsing, then the stable filters, rather than a transient value.
    expect(new URL((await parseQuery).url()).searchParams.get('q')).toBe('2 bed flat in Clifton under 50k');
    await expect(mic).toHaveAttribute("aria-pressed", "false");
    await expect(page.locator("#nlUnderstood")).toBeVisible();
    await expect(page.locator("#nlUnderstood")).toContainText("Clifton");
    await expect(page.locator("#bedsChip")).toContainText("2 Bed");
    await expect(page.locator("#priceChip")).toContainText("50K");
    await expect(page.locator("#nlInput")).toHaveValue("");
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


test.describe("Microphone recovery", () => {
  test("permission denial restores the button and reports the error", async ({ page }) => {
    await page.addInitScript(() => {
      navigator.mediaDevices.getUserMedia = async () => { throw new DOMException('denied', 'NotAllowedError'); };
    });
    await page.goto('/');
    const mic = page.locator('#nlMicBtn');
    await mic.click();
    await expect(page.locator('#nlParsed')).toContainText('Microphone access is blocked');
    await expect(mic).toBeEnabled();
    await expect(page.locator('#nlParsed')).toHaveAttribute('role', 'status');
    const statusBox = await page.locator('#nlParsed').boundingBox();
    const inputBox = await page.locator('#nlInput').boundingBox();
    expect(statusBox.x).toBeGreaterThanOrEqual(0);
    expect(statusBox.x + statusBox.width).toBeLessThanOrEqual(page.viewportSize().width);
    if (page.viewportSize().width < 768) {
      expect(statusBox.y).toBeGreaterThanOrEqual(inputBox.y + inputBox.height);
    }
  });

  test("pending permission cannot create multiple recording streams", async ({ page }) => {
    await page.addInitScript(() => {
      window.__micCalls = 0;
      navigator.mediaDevices.getUserMedia = () => {
        window.__micCalls++;
        return new Promise(() => {});
      };
    });
    await page.goto('/');
    const mic = page.locator('#nlMicBtn');
    await mic.click();
    await expect(mic).toBeDisabled();
    const box = await mic.boundingBox();
    await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
    expect(await page.evaluate(() => window.__micCalls)).toBe(1);
  });

  test("recorder construction failure releases the microphone", async ({ page }) => {
    await page.addInitScript(() => {
      window.__trackStops = 0;
      navigator.mediaDevices.getUserMedia = async () => ({ getTracks: () => [{ stop: () => window.__trackStops++ }] });
      window.MediaRecorder = class {
        static isTypeSupported() { return true; }
        constructor() { throw new Error('unsupported recorder'); }
      };
    });
    await page.goto('/');
    const mic = page.locator('#nlMicBtn');
    await mic.click();
    await expect(page.locator('#nlParsed')).toContainText('Could not start recording');
    await expect(mic).toBeEnabled();
    expect(await page.evaluate(() => window.__trackStops)).toBe(1);
  });
});
