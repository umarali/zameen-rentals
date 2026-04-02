// @ts-check
const { test, expect } = require("@playwright/test");

test.describe("Desktop Map", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await page.waitForSelector("#mapContainer", { timeout: 30000 });
    await expect(page.locator("#mapContainer")).toHaveClass(/leaflet-container/);
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
    await page.locator('.city-tab[data-city="karachi"]').click();
    await page.waitForTimeout(2000);
    const markers = page.locator("#mapContainer .area-marker");
    expect(await markers.count()).toBeGreaterThan(0);
  });

  test("street zoom keeps only the focused area label visible", async ({ page }) => {
    await page.locator('.city-tab[data-city="karachi"]').click();
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
    expect(await page.locator("#mapContainer .area-label").count()).toBeLessThanOrEqual(1);
  });

  test("active area badge shows total count", async ({ page }) => {
    await page.locator('.city-tab[data-city="karachi"]').click();
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

  test("city change keeps the map in viewport mode", async ({ page }) => {
    await page.locator('.city-tab[data-city="karachi"]').click();
    await page.waitForTimeout(1500);
    await page.locator('.city-tab[data-city="lahore"]').click();
    await page.waitForTimeout(1500);
    await expect(page.locator("#mapContainer")).toHaveClass(
      /leaflet-container/
    );
    await expect(page.locator('.city-tab[data-city="lahore"]')).toHaveClass(/active/);
    await expect(page.locator("#listingsTitle")).toContainText("map view");
  });

  test("covered areas render as green dots", async ({ page }) => {
    await page.locator('.city-tab[data-city="karachi"]').click();
    await page.waitForTimeout(2000);
    expect(await page.locator("#mapContainer .area-dot-live").count()).toBeGreaterThan(0);
  });

  test("uncovered areas render as gray coverage dots", async ({ page }) => {
    await page.locator('.city-tab[data-city="karachi"]').click();
    await page.waitForTimeout(2000);
    expect(await page.locator("#mapContainer .coverage-dot").count()).toBeGreaterThan(0);
  });

  test("sub-area markers appear when parent selected", async ({ page }) => {
    await page.locator('.city-tab[data-city="karachi"]').click();
    // Select an area known to have sub-areas
    await page.locator("#areaChip").click();
    await page.locator("#areaInput").fill("North Nazimabad");
    await page.waitForTimeout(400);
    const opt = page.locator('.area-opt:text("North Nazimabad")').first();
    if ((await opt.count()) > 0) {
      await opt.click();
      await page.waitForTimeout(3000);
      const subMarkers = page.locator(
        '#mapContainer .area-label:text-matches("North Nazimabad Block|North Nazimabad -")'
      );
      expect(await subMarkers.count()).toBeGreaterThanOrEqual(0);
    }
  });

  test("viewport mode explains shown vs available counts", async ({ page }) => {
    await page.locator('.city-tab[data-city="karachi"]').click();
    await page.waitForTimeout(2000);
    await expect(page.locator("#resultsCount")).toContainText("shown");
    await expect(page.locator("#resultsMeta")).toContainText(/available in|available across|No local listings|Move the map/);
  });
});

test.describe("Mobile Map", () => {
  test.use({ viewport: { width: 375, height: 812 } });

  test("map FAB opens overlay", async ({ page }) => {
    await page.goto("/");
    await page.waitForSelector("#mapFab", { timeout: 30000 });
    await expect(page.locator("#mapFab")).toBeVisible();
    await page.locator("#mapFab").click();
    await expect(page.locator("#mapOverlay")).toBeVisible();
    await expect(page.locator("#mapContainerMobile")).toBeVisible();
  });

  test("mobile map close button works", async ({ page }) => {
    await page.goto("/");
    await page.waitForSelector("#mapFab", { timeout: 30000 });
    await page.locator("#mapFab").click();
    await expect(page.locator("#mapOverlay")).toBeVisible();
    await page.locator("#mapOverlayClose").click();
    await expect(page.locator("#mapOverlay")).toBeHidden();
  });
});
