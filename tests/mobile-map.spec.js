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
  test("tapping an exact pin opens the photo preview above the cards", async ({ page }) => {
    await page.route("**/api/map-search**", route => route.fulfill({
      json: {
        total: 1, page: 1, per_page: 25, source: "local", mode: "viewport", scope: "exact_bounds",
        visible_areas: 1, area_totals: { Gulberg: 1 }, attempted_exact_bounds: true, exact_bounds_total: 1,
        results: [{
          zameen_id: "7700031", title: "Tapped pin house", price: 65000, bedrooms: 2,
          url: "https://www.zameen.com/Property/test-7700031-1-1.html",
          image_url: "/static/favicon-512.png", location: "Gulberg, Lahore",
          latitude: 31.5204, longitude: 74.3587, location_source: "listing_exact", has_exact_geography: true,
        }],
      },
    }));
    await page.route("**/api/listing-detail**", route => route.fulfill({
      json: { images: ["/static/favicon-512.png?1", "/static/favicon-512.png?2"], has_exact_geography: true, source: "local" },
    }));
    await page.locator("#mapFab").click();
    await expect(page.locator("#mapOverlay")).toBeVisible();
    const pin = page.locator("#mapContainerMobile .listing-exact-marker");
    for (let i = 0; i < 4 && !(await pin.count()); i++) {
      await page.locator("#mapContainerMobile .leaflet-control-zoom-in").click();
      await page.waitForTimeout(700);
    }
    await pin.first().click({ force: true });
    const popup = page.locator("#mapOverlay .pin-popup");
    await expect(popup).toContainText("Tapped pin house");
    await expect(popup.locator("[data-gallery-count]")).toHaveText("1 / 2");
    const cardBox = await popup.locator(".pin-preview").boundingBox();
    const carouselBox = await page.locator("#mapCarousel").boundingBox();
    expect(cardBox.y + cardBox.height).toBeLessThanOrEqual(carouselBox.y + 2);
    await popup.locator("[data-preview-open]").click();
    await expect(page.locator("#drawer")).toHaveClass(/drawer-open/);
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
