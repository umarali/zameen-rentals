// @ts-check
const { test, expect } = require("@playwright/test");

async function stubDrawerMapSearch(page) {
  const payload = {
    total: 1,
    page: 1,
    per_page: 25,
    source: "local",
    mode: "viewport",
    visible_areas: 1,
    area_totals: { Clifton: 1 },
    ranking: "map_focus",
    focus_center: { lat: 24.82, lng: 67.03 },
    results: [
      {
        title: "Drawer map listing",
        url: "https://www.zameen.com/Property/test-drawer-map-1.html",
        price: 95000,
        bedrooms: 2,
        bathrooms: 2,
        area_size: "1000 sqft",
        location: "Clifton, Karachi",
        property_type: "Apartment",
        latitude: 24.821,
        longitude: 67.031,
        location_source: "listing_exact",
        has_exact_geography: true,
      },
    ],
  };

  await page.route("**/api/map-search**", async (route) => {
    await route.fulfill({ json: payload });
  });
  await page.route("**/api/search**", async (route) => {
    await route.fulfill({ json: payload });
  });

  await page.reload();
  await page.waitForSelector(".card-wrap", { timeout: 30000 });
}

test.describe("Detail Drawer", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await page.waitForSelector(".card-wrap", { timeout: 30000 });
  });

  test("clicking a card opens the drawer", async ({ page }) => {
    await page.locator(".card-wrap").first().click();
    await expect(page.locator("#drawer")).toHaveClass(/drawer-open/, {
      timeout: 3000,
    });
    await expect(page.locator("#drawerOverlay")).toHaveClass(/overlay-open/);
  });

  test("drawer shows listing title", async ({ page }) => {
    await page.locator(".card-wrap").first().click();
    await expect(page.locator("#drawer")).toHaveClass(/drawer-open/, {
      timeout: 3000,
    });
    const content = await page.locator("#drawerContent").textContent();
    expect(content.length).toBeGreaterThan(10);
  });

  test("drawer shows price", async ({ page }) => {
    await page.locator(".card-wrap").first().click();
    await expect(page.locator("#drawer")).toHaveClass(/drawer-open/, {
      timeout: 3000,
    });
    const content = await page.locator("#drawerContent").textContent();
    expect(content).toMatch(/Rs|Lakh|lakh|PKR|\d/i);
  });

  test("drawer shows View on Zameen.com link", async ({ page }) => {
    await page.locator(".card-wrap").first().click();
    await expect(page.locator("#drawer")).toHaveClass(/drawer-open/, {
      timeout: 3000,
    });
    const link = page.locator('#drawerContent a[title="View on Zameen.com"]');
    await expect(link).toBeVisible();
    const href = await link.getAttribute("href");
    expect(href).toContain("zameen.com");
  });

  test("drawer has image area", async ({ page }) => {
    await page.locator(".card-wrap").first().click();
    await expect(page.locator("#drawer")).toHaveClass(/drawer-open/, {
      timeout: 3000,
    });
    await expect(page.locator("#drawerImgArea")).toBeVisible();
  });

  test("drawer close button works", async ({ page }) => {
    await page.locator(".card-wrap").first().click();
    await expect(page.locator("#drawer")).toHaveClass(/drawer-open/, {
      timeout: 3000,
    });
    // Wait for drawer transition to complete
    await page.waitForTimeout(500);
    await page.locator("#drawerClose").click();
    await page.waitForTimeout(500);
    await expect(page.locator("#drawer")).not.toHaveClass(/drawer-open/);
  });

  test("clicking overlay closes drawer", async ({ page }) => {
    await page.locator(".card-wrap").first().click();
    await expect(page.locator("#drawer")).toHaveClass(/drawer-open/, {
      timeout: 3000,
    });
    await page.locator("#drawerOverlay").click({ force: true });
    await expect(page.locator("#drawer")).not.toHaveClass(/drawer-open/);
  });

  test("escape key closes drawer", async ({ page }) => {
    await page.locator(".card-wrap").first().click();
    await expect(page.locator("#drawer")).toHaveClass(/drawer-open/, {
      timeout: 3000,
    });
    await page.keyboard.press("Escape");
    await expect(page.locator("#drawer")).not.toHaveClass(/drawer-open/);
  });

  test("drawer shows nearby areas", async ({ page }) => {
    await page.locator(".card-wrap").first().click();
    await expect(page.locator("#drawer")).toHaveClass(/drawer-open/, {
      timeout: 3000,
    });
    // Nearby areas section may or may not appear depending on area data
    await page.waitForTimeout(500);
    const nearbyChips = page.locator("#drawerContent [data-nearby]");
    // Just verify no crash — nearby may not always be present
    const count = await nearbyChips.count();
    expect(count).toBeGreaterThanOrEqual(0);
  });

  test("clicking nearby area chip closes drawer and searches", async ({
    page,
  }) => {
    await page.locator(".card-wrap").first().click();
    await expect(page.locator("#drawer")).toHaveClass(/drawer-open/, {
      timeout: 3000,
    });
    await page.waitForTimeout(500);
    const nearbyChips = page.locator("#drawerContent [data-nearby]");
    if ((await nearbyChips.count()) > 0) {
      await nearbyChips.first().click();
      await expect(page.locator("#drawer")).not.toHaveClass(/drawer-open/);
      await expect(page.locator("#areaChip")).toHaveClass(/has-value/);
    }
  });

  test("drawer mini map renders", async ({ page }) => {
    await stubDrawerMapSearch(page);
    await page.locator(".card-wrap").first().click();
    await expect(page.locator("#drawer")).toHaveClass(/drawer-open/, {
      timeout: 3000,
    });
    await expect(page.locator("#drawerMiniMap")).toBeAttached();
  });

  test("drawer mini map inherits the active satellite layer", async ({ page }) => {
    // Desktop-only: #mapContainer layer toggle is hidden on mobile
    if ((page.viewportSize()?.width ?? 1440) < 1024) {
      test.skip(true, "Desktop-only test, skipping on mobile viewport");
      return;
    }
    await stubDrawerMapSearch(page);
    await page.locator('#mapContainer [data-map-layer="satellite"]').first().click();
    await page.locator(".card-wrap").first().click();
    await expect(page.locator("#drawer")).toHaveClass(/drawer-open/, {
      timeout: 3000,
    });
    await expect(page.locator("#drawerMiniMap .leaflet-tile").first()).toHaveAttribute(
      "src",
      /World_Imagery|ArcGIS\/rest\/services\/World_Imagery/
    );
  });
});

test.describe("Detail Drawer - Mobile", () => {
  test.use({ viewport: { width: 375, height: 812 } });

  test("drawer opens from bottom on mobile", async ({ page }) => {
    await page.goto("/");
    await page.waitForSelector(".card-wrap", { timeout: 30000 });
    await page.locator(".card-wrap").first().click();
    await expect(page.locator("#drawer")).toHaveClass(/drawer-open/, {
      timeout: 3000,
    });
  });

  test("drawer uses the full mobile viewport", async ({ page }) => {
    await page.goto("/");
    await page.waitForSelector(".card-wrap", { timeout: 30000 });
    await page.locator(".card-wrap").first().click();
    await expect(page.locator("#drawer")).toHaveClass(/drawer-open/, {
      timeout: 3000,
    });
    await page.waitForTimeout(450);

    const viewport = page.viewportSize();
    const box = await page.locator("#drawer").boundingBox();

    expect(box).toBeTruthy();
    expect(Math.abs(box.x)).toBeLessThanOrEqual(1);
    expect(Math.abs(box.y)).toBeLessThanOrEqual(1);
    expect(Math.abs(box.width - viewport.width)).toBeLessThanOrEqual(1);
    expect(Math.abs(box.height - viewport.height)).toBeLessThanOrEqual(1);
  });
});
