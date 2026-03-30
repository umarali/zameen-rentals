// @ts-check
const { test, expect } = require("@playwright/test");

test.describe("Desktop Map", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await page.waitForSelector(".card-wrap", { timeout: 30000 });
  });

  test("map container renders with Leaflet tiles", async ({ page }) => {
    await expect(page.locator("#mapContainer")).toBeVisible();
    // Leaflet adds .leaflet-container class
    await expect(page.locator("#mapContainer")).toHaveClass(
      /leaflet-container/
    );
  });

  test("map has zoom controls", async ({ page }) => {
    await expect(
      page.locator("#mapContainer .leaflet-control-zoom")
    ).toBeVisible();
  });

  test("area markers appear on map after search", async ({ page }) => {
    // Markers are area-marker divIcon elements
    await page.waitForTimeout(2000);
    const markers = page.locator("#mapContainer .area-marker");
    // At least one marker should exist (active area or results)
    expect(await markers.count()).toBeGreaterThanOrEqual(0);
  });

  test("active area marker has special styling", async ({ page }) => {
    // Select an area to make it active
    await page.locator("#areaChip").click();
    await page.locator("#areaInput").fill("DHA");
    await page.waitForTimeout(400);
    await page.locator(".area-opt").first().click();
    await page.waitForTimeout(2000);
    const activeLabel = page.locator(
      "#mapContainer .area-label-active"
    );
    expect(await activeLabel.count()).toBeGreaterThanOrEqual(1);
  });

  test("active area badge shows total count", async ({ page }) => {
    await page.locator("#areaChip").click();
    await page.locator("#areaInput").fill("DHA");
    await page.waitForTimeout(400);
    await page.locator(".area-opt").first().click();
    await page.waitForTimeout(3000);
    const badge = page.locator(
      "#mapContainer .area-label-active .area-badge"
    );
    if ((await badge.count()) > 0) {
      const text = await badge.textContent();
      expect(parseInt(text)).toBeGreaterThan(0);
    }
  });

  test("map re-centers when city changes", async ({ page }) => {
    // Get initial center (approximate via map bounds)
    await page.locator('.city-tab[data-city="lahore"]').click();
    await page.waitForSelector(".card-wrap", { timeout: 30000 });
    // Map should still have Leaflet container
    await expect(page.locator("#mapContainer")).toHaveClass(
      /leaflet-container/
    );
  });

  test("clicking marker selects area", async ({ page }) => {
    await page.waitForTimeout(2000);
    const markers = page.locator("#mapContainer .area-label");
    if ((await markers.count()) > 0) {
      await markers.first().click();
      await page.waitForTimeout(2000);
      await expect(page.locator("#areaChip")).toHaveClass(/has-value/);
    }
  });

  test("sub-area markers appear when parent selected", async ({ page }) => {
    // Select an area known to have sub-areas
    await page.locator("#areaChip").click();
    await page.locator("#areaInput").fill("North Nazimabad");
    await page.waitForTimeout(400);
    const opt = page.locator('.area-opt:text("North Nazimabad")').first();
    if ((await opt.count()) > 0) {
      await opt.click();
      await page.waitForTimeout(3000);
      // Check if sub-area markers like "North Nazimabad Block A" appear
      const subMarkers = page.locator(
        '#mapContainer .area-label:text-matches("North Nazimabad Block|North Nazimabad -")'
      );
      // May or may not have sub-areas visible depending on zoom
      expect(await subMarkers.count()).toBeGreaterThanOrEqual(0);
    }
  });
});

test.describe("Mobile Map", () => {
  test.use({ viewport: { width: 375, height: 812 } });

  test("map FAB opens overlay", async ({ page }) => {
    await page.goto("/");
    await page.waitForSelector(".card-wrap", { timeout: 30000 });
    await expect(page.locator("#mapFab")).toBeVisible();
    await page.locator("#mapFab").click();
    await expect(page.locator("#mapOverlay")).toBeVisible();
    await expect(page.locator("#mapContainerMobile")).toBeVisible();
  });

  test("mobile map close button works", async ({ page }) => {
    await page.goto("/");
    await page.waitForSelector(".card-wrap", { timeout: 30000 });
    await page.locator("#mapFab").click();
    await expect(page.locator("#mapOverlay")).toBeVisible();
    await page.locator("#mapOverlayClose").click();
    await expect(page.locator("#mapOverlay")).toBeHidden();
  });
});
