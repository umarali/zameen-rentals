// @ts-check
const { test, expect } = require("@playwright/test");

test.describe("Mobile Map Overlay", () => {
  test.use({ viewport: { width: 375, height: 812 } });

  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await page.waitForSelector(".card-wrap", { timeout: 30000 });
  });

  test("map FAB is visible on mobile", async ({ page }) => {
    await expect(page.locator("#mapFab")).toBeVisible();
  });

  test("clicking FAB opens map overlay", async ({ page }) => {
    await page.locator("#mapFab").click();
    await expect(page.locator("#mapOverlay")).toBeVisible();
  });

  test("map overlay has close button", async ({ page }) => {
    await page.locator("#mapFab").click();
    await expect(page.locator("#mapOverlay")).toBeVisible();
    await expect(page.locator("#mapOverlayClose")).toBeVisible();
  });

  test("close button dismisses map overlay", async ({ page }) => {
    await page.locator("#mapFab").click();
    await expect(page.locator("#mapOverlay")).toBeVisible();
    await page.locator("#mapOverlayClose").click();
    await expect(page.locator("#mapOverlay")).toBeHidden();
  });

  test("map tiles render inside overlay", async ({ page }) => {
    await page.locator("#mapFab").click();
    await expect(page.locator("#mapOverlay")).toBeVisible();
    // Wait for Leaflet tiles to load
    await expect(
      page.locator("#mapOverlay .leaflet-tile").first()
    ).toBeAttached({ timeout: 10000 });
  });

  test("map overlay covers full viewport", async ({ page }) => {
    await page.locator("#mapFab").click();
    await expect(page.locator("#mapOverlay")).toBeVisible();
    await page.waitForTimeout(300);

    const box = await page.locator("#mapOverlay").boundingBox();
    const viewport = page.viewportSize();
    expect(box).toBeTruthy();
    expect(Math.abs(box.width - viewport.width)).toBeLessThanOrEqual(1);
    expect(Math.abs(box.height - viewport.height)).toBeLessThanOrEqual(1);
  });
});

test.describe("Map FAB Desktop Behavior", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("map FAB is hidden on desktop", async ({ page }) => {
    await page.goto("/");
    await page.waitForSelector(".card-wrap", { timeout: 30000 });
    await expect(page.locator("#mapFab")).toBeHidden();
  });

  test("desktop map panel is visible", async ({ page }) => {
    await page.goto("/");
    await page.waitForSelector(".card-wrap", { timeout: 30000 });
    await expect(page.locator("#mapPanel")).toBeVisible();
  });
});
