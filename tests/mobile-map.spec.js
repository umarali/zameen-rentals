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

  test("map overlay fills the screen below the search and filters", async ({ page }) => {
    await page.locator("#mapFab").click();
    await expect(page.locator("#mapOverlay")).toBeVisible();
    await page.waitForTimeout(300);

    const box = await page.locator("#mapOverlay").boundingBox();
    const filters = await page.locator("#filtersShell").boundingBox();
    const viewport = page.viewportSize();
    expect(box).toBeTruthy();
    expect(Math.abs(box.width - viewport.width)).toBeLessThanOrEqual(1);
    expect(Math.abs(box.y - (filters.y + filters.height))).toBeLessThanOrEqual(2);
    expect(Math.abs(box.y + box.height - viewport.height)).toBeLessThanOrEqual(1);
  });

  test("filters work while the map is open", async ({ page }) => {
    await page.locator("#mapFab").click();
    await expect(page.locator("#mapOverlay")).toBeVisible();
    await page.locator("#bedsChip").click();
    await page.locator('#bedRow .chip[data-beds="2"]').click();
    await expect(page.locator("#bedsChip")).toHaveClass(/has-value/);
    await expect(page.locator("#mapOverlay")).toBeVisible();
  });

  test("Back closes the map instead of leaving the page", async ({ page }) => {
    await page.locator("#mapFab").click();
    await expect(page.locator("#mapOverlay")).toBeVisible();
    await page.goBack();
    await expect(page.locator("#mapOverlay")).toBeHidden();
    await expect(page.locator(".card-wrap").first()).toBeVisible();
  });

  test("a listing card opens over the map and Back returns to the map", async ({ page }) => {
    await page.locator("#mapFab").click();
    const card = page.locator("#mapCarousel .map-card[data-mobile-card-id]").first();
    await expect(card).toBeVisible({ timeout: 15000 });
    await card.click();
    await expect(page.locator("#drawer")).toHaveClass(/drawer-open/);
    await page.goBack();
    await expect(page.locator("#drawer")).not.toHaveClass(/drawer-open/);
    await expect(page.locator("#mapOverlay")).toBeVisible();
  });

  test("tapping a pin selects its card in the rail", async ({ page }) => {
    await page.route("**/api/map-pins**", route => route.fulfill({
      json: { total: 1, types: ["House"], stack_min: 2, stacks: [], pins: [["7700031", 31.5200, 74.3500, 65000, 2, 0]] },
    }));
    await page.route("**/api/listings/7700031", route => route.fulfill({
      json: {
        zameen_id: "7700031", title: "Tapped pin house", price: 65000,
        url: "https://www.zameen.com/Property/test-7700031-1-1.html",
        latitude: 31.52, longitude: 74.35, has_exact_geography: true, is_active: true,
      },
    }));
    await page.reload();
    await page.locator("#mapFab").click();
    const pin = page.locator("#mapOverlay .map-pin", { hasText: "65K" });
    await expect(pin).toBeVisible({ timeout: 15000 });
    await pin.click();
    const selected = page.locator('#mapCarousel .map-card.is-selected[data-mobile-card-id="7700031"]');
    await expect(selected).toBeVisible();
    await expect(selected).toContainText("Tapped pin house");
  });

  test("the cards rail can be hidden to see more map", async ({ page }) => {
    await page.locator("#mapFab").click();
    await expect(page.locator("#mapCarousel")).toBeVisible({ timeout: 15000 });
    await page.locator("#mapCardsToggle").click();
    await expect(page.locator("#mapCarousel")).toBeHidden();
    await page.locator("#mapCardsToggle").click();
    await expect(page.locator("#mapCarousel")).toBeVisible();
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
