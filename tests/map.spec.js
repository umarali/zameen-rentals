// @ts-check
const { test, expect } = require("@playwright/test");

test.describe("Desktop Map", () => {
  test.beforeEach(async ({ page }) => {
    // Skip on mobile viewports — desktop map (#mapContainer) is hidden below 1024px
    if ((page.viewportSize()?.width ?? 1440) < 1024) {
      test.skip(true, "Desktop-only test, skipping on mobile viewport");
      return;
    }
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

  test("top-right controls align cleanly alongside the coverage badge", async ({ page }) => {
    await expect(page.locator("#mapCoverageBadge")).toBeVisible();
    const layerControl = page.locator("#mapContainer .map-layer-control").first();
    const gpsControl = page.locator("#mapContainer .map-gps-btn").first();
    const zoomControl = page.locator("#mapContainer .leaflet-control-zoom").first();

    await expect(layerControl).toBeVisible();
    await expect(gpsControl).toBeVisible();
    await expect(zoomControl).toBeVisible();

    const badgeBox = await page.locator("#mapCoverageBadge").boundingBox();
    const layerBox = await layerControl.boundingBox();
    const gpsBox = await gpsControl.boundingBox();
    const zoomBox = await zoomControl.boundingBox();

    expect(badgeBox).toBeTruthy();
    expect(layerBox).toBeTruthy();
    expect(gpsBox).toBeTruthy();
    expect(zoomBox).toBeTruthy();
    expect(gpsBox.x).toBeGreaterThan(badgeBox.x + badgeBox.width - 8);
    expect(Math.abs((layerBox.x + layerBox.width) - (gpsBox.x + gpsBox.width))).toBeLessThanOrEqual(2);
    expect(Math.abs((layerBox.x + layerBox.width) - (zoomBox.x + zoomBox.width))).toBeLessThanOrEqual(2);
    expect(gpsBox.y).toBeGreaterThan(layerBox.y + layerBox.height - 2);
    expect(zoomBox.y).toBeGreaterThan(gpsBox.y + gpsBox.height - 2);
  });

  test("map summary shows the count, the auto-search toggle and the map key", async ({ page }) => {
    const summary = page.locator("#mapCoverageBadge");
    await expect(summary).toBeVisible();
    await expect(summary.locator("[data-map-count]")).toHaveText(/^\d[\d,]*$/, { timeout: 15000 });
    await expect(summary.locator("[data-map-autosearch]")).toBeChecked();
    await summary.locator("[data-map-key-toggle]").click();
    await expect(summary.locator("[data-map-key]")).toBeVisible();
    await expect(summary).toContainText("Rent, at the listing's own pin");
    await expect(summary).toContainText("block or society pin (approximate)");
  });

  test("map layer toggle switches to satellite and persists after reload", async ({ page }) => {
    const satelliteBtn = page.locator('#mapContainer [data-map-layer="satellite"]').first();
    await satelliteBtn.click();
    await expect(satelliteBtn).toHaveClass(/active/);
    await expect(page.locator("#mapContainer .leaflet-tile").first()).toHaveAttribute(
      "src",
      /World_Imagery|ArcGIS\/rest\/services\/World_Imagery/
    );
    // Satellite carries road and place-name overlays.
    await expect(page.locator('#mapContainer .leaflet-tile[src*="Reference/World_Boundaries_and_Places"]').first()).toBeAttached();

    await page.reload();
    await page.waitForSelector("#mapContainer .leaflet-control-zoom", {
      timeout: 30000,
    });
    await expect(
      page.locator('#mapContainer [data-map-layer="satellite"]').first()
    ).toHaveClass(/active/);
  });

  test("every matching rental is a pin: a cluster splits into price pins on click", async ({ page }) => {
    await page.route("**/api/map-pins**", route => route.fulfill({
      json: {
        total: 3,
        types: ["Apartment / Flat"],
        stack_min: 2,
        stacks: [],
        pins: [
          ["7700001", 31.5200, 74.3500, 85000, 2, 0],
          ["7700002", 31.5203, 74.3504, 120000, 3, 0],
          ["7700003", 31.5206, 74.3497, 240000, 4, 0],
        ],
      },
    }));
    await page.reload();
    const cluster = page.locator("#mapContainer .map-cluster", { hasText: "3" });
    await expect(cluster).toBeVisible({ timeout: 15000 });
    await cluster.click();
    await expect(page.locator("#mapContainer .map-pin", { hasText: "85K" })).toBeVisible({ timeout: 10000 });
    await expect(page.locator("#mapContainer .map-pin", { hasText: "1.2L" })).toBeVisible();
    await expect(page.locator("#mapContainer .map-pin", { hasText: "2.4L" })).toBeVisible();
  });

  test("a pin opens a preview card and the preview opens the listing", async ({ page }) => {
    await page.route("**/api/map-pins**", route => route.fulfill({
      json: { total: 1, types: ["House"], stack_min: 2, stacks: [], pins: [["7700011", 31.5200, 74.3500, 85000, 2, 0]] },
    }));
    await page.route("**/api/listings/7700011", route => route.fulfill({
      json: {
        zameen_id: "7700011",
        title: "Pin preview house",
        url: "https://www.zameen.com/Property/test-7700011-1-1.html",
        price: 85000,
        bedrooms: 2,
        bathrooms: 2,
        area_size: "5 Marla",
        location: "Gulberg, Lahore",
        property_type: "House",
        latitude: 31.52,
        longitude: 74.35,
        has_exact_geography: true,
        is_active: true,
      },
    }));
    await page.reload();
    const pin = page.locator("#mapContainer .map-pin", { hasText: "85K" });
    await expect(pin).toBeVisible({ timeout: 15000 });
    await pin.click();
    const popup = page.locator("#mapContainer .pin-popup");
    await expect(popup).toContainText("Pin preview house");
    await expect(pin).toHaveClass(/is-selected/);
    await popup.locator("[data-preview-open]").click();
    await expect(page.locator("#drawer")).toHaveClass(/drawer-open/);
    await expect(page.locator("#drawerContent")).toContainText("Pin preview house");
  });

  test("a shared map point lists its rentals together", async ({ page }) => {
    await page.route("**/api/map-pins**", route => route.fulfill({
      json: {
        total: 12, types: [], stack_min: 2, pins: [],
        stacks: [[31.52, 74.35, 12, "Gulberg", 40000, 180000, 0]],
      },
    }));
    const stackSearches = [];
    page.on("request", req => {
      if (req.url().includes("/api/map-search")) {
        const url = new URL(req.url());
        if (Number(url.searchParams.get("north")) - Number(url.searchParams.get("south")) < 0.0001) stackSearches.push(url);
      }
    });
    await page.reload();
    const stack = page.locator("#mapContainer .map-stack", { hasText: "12" });
    await expect(stack).toBeVisible({ timeout: 15000 });
    await expect(stack).toHaveClass(/is-approx/);
    await stack.click();
    const popup = page.locator("#mapContainer .pin-popup");
    await expect(popup).toContainText("12 rentals at this point");
    await expect(popup).toContainText("block or society");
    await popup.locator("[data-stack-search]").click();
    await expect(page.locator("#listingsTitle")).toHaveText("Rentals on one map pin in Gulberg");
    expect(stackSearches.length).toBeGreaterThan(0);
    await expect(page.locator("#mapPanel .map-search-area")).toHaveText("Show all rentals in this view");
  });

  test("hovering a card highlights its pin", async ({ page }) => {
    await page.route("**/api/map-pins**", route => route.fulfill({
      json: { total: 1, types: ["House"], stack_min: 2, stacks: [], pins: [["7700021", 31.5200, 74.3500, 95000, 2, 0]] },
    }));
    await page.route("**/api/map-search**", route => route.fulfill({
      json: {
        total: 1, page: 1, per_page: 25, source: "local", mode: "viewport", scope: "exact_bounds",
        visible_areas: 1, area_totals: { Gulberg: 1 },
        results: [{
          zameen_id: "7700021",
          title: "Hover sync house",
          url: "https://www.zameen.com/Property/test-7700021-1-1.html",
          price: 95000, property_type: "House", location: "Gulberg, Lahore",
          latitude: 31.52, longitude: 74.35, has_exact_geography: true,
        }],
      },
    }));
    await page.reload();
    await expect(page.locator("#listingsGrid")).toContainText("Hover sync house");
    await page.locator('.card-wrap[data-zameen-id="7700021"]').hover();
    // Drawn as its own pin, or floated above the cluster that holds it.
    await expect(page.locator("#mapContainer .map-pin.is-hovered", { hasText: "95K" })).toBeVisible();
  });

  test("with auto-search off, moving the map offers Search this area", async ({ page }) => {
    await page.waitForLoadState("networkidle");
    const autosearch = page.locator("#mapCoverageBadge [data-map-autosearch]");
    await autosearch.uncheck();
    let mapSearches = 0;
    page.on("request", req => { if (req.url().includes("/api/map-search")) mapSearches += 1; });
    await page.locator("#mapContainer").focus();
    await page.keyboard.press("ArrowRight");
    const pill = page.locator("#mapPanel .map-search-area");
    await expect(pill).toBeVisible();
    await page.waitForTimeout(600);
    expect(mapSearches).toBe(0);
    await pill.click();
    await expect(pill).toBeHidden();
    await expect.poll(() => mapSearches).toBeGreaterThan(0);

    await page.reload();
    await expect(page.locator("#mapCoverageBadge [data-map-autosearch]")).not.toBeChecked();
  });

  test("an area search sends the area to the map pins", async ({ page }) => {
    await page.locator('.city-tab[data-city="karachi"]').click();
    const pinsRequest = page.waitForRequest(req => req.url().includes("/api/map-pins") && new URL(req.url()).searchParams.get("area") === "Clifton");
    await page.locator("#areaChip").click();
    await page.locator("#areaInput").fill("Clifton");
    await page.waitForTimeout(400);
    await page.locator(".area-opt", { hasText: "Clifton" }).first().click();
    await pinsRequest;
    await expect(page.locator("#listingsTitle")).toContainText("Clifton");
  });

  test("street zoom removes the active area label (marker removed at high zoom)", async ({ page }) => {
    await page.locator('.city-tab[data-city="karachi"]').click();
    // Select an area to make it active
    await page.locator("#areaChip").click();
    await page.locator("#areaInput").fill("DHA");
    await page.waitForTimeout(400);
    await page.locator(".area-opt").first().click();
    await page.waitForTimeout(2000);
    // At zoom >= 13, the active area label is removed so pins take over.
    await expect(page.locator("#mapContainer .area-label-active")).toHaveCount(0);
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

  test("cards in map view don't claim a distance from the map centre", async ({ page }) => {
    await page.locator('.city-tab[data-city="karachi"]').click();
    await expect(page.locator(".card-wrap").first()).toBeVisible();
    await expect(page.locator("#listingsTitle")).toContainText("map view");
    await expect(page.locator("#listingsGrid")).not.toContainText(/km away|m away/);
  });

  test("viewport mode explains shown vs available counts", async ({ page }) => {
    await page.locator('.city-tab[data-city="karachi"]').click();
    await page.waitForTimeout(2000);
    await expect(page.locator("#resultsCount")).toContainText(/Showing|shown/);
    await expect(page.locator("#resultsMeta")).toContainText(/exact-pin rentals currently visible|available in|available across|No local listings|Move the map/);
    await expect(page.locator("#dataSource")).toContainText(/Nearest first|Instant/);
  });

  test("nearby chip is available for all three cities", async ({ page }) => {
    // Nearby search was expanded from Karachi-only to all 3 cities
    for (const city of ["karachi", "lahore", "islamabad"]) {
      await page.locator(`.city-tab[data-city="${city}"]`).click();
      await page.waitForTimeout(500);
      // The chip should NOT be disabled for any supported city
      await expect(page.locator("#nearbyChip")).not.toHaveClass(/chip-disabled/);
    }
  });

  test("nearby mode shows exact distance labels and radius controls", async ({
    page,
  }) => {
    await page.context().grantPermissions(["geolocation"]);
    await page.context().setGeolocation({ latitude: 24.82, longitude: 67.03 });

    const nearbyRequests = [];
    await page.route("**/api/nearby-search**", async (route) => {
      nearbyRequests.push(route.request().url());
      await route.fulfill({
        json: {
          total: 1,
          page: 1,
          per_page: 25,
          results: [
            {
              title: "Nearby exact rental",
              url: "https://www.zameen.com/Property/test-nearby-1.html",
              price: 90000,
              bedrooms: 2,
              bathrooms: 2,
              area_size: "1000 sqft",
              location: "Clifton, Karachi",
              property_type: "Apartment",
              latitude: 24.821,
              longitude: 67.031,
              location_source: "listing_exact",
              has_exact_geography: true,
              distance_km: 1.2,
              distance_source: "listing_exact",
              is_distance_approximate: false,
            },
          ],
          source: "local",
          mode: "nearby",
          radius_km: 5,
          focus_center: { lat: 24.82, lng: 67.03 },
        },
      });
    });

    await page.locator('.city-tab[data-city="karachi"]').click();
    await page.locator("#nearbyChip").click();

    await expect(page.locator("#listingsTitle")).toHaveText("Rentals near you");
    await expect(page.locator("#resultsMeta")).toContainText(/within 5 km/i);
    await expect(page.locator("#listingsGrid")).toContainText("1.2 km away");
    await expect(page.locator("#radiusChip")).toBeVisible();
    await expect(page.locator("#mapContainer .user-location-marker")).toBeVisible();

    await page.locator("#radiusChip").click();
    await page.locator('#radiusOptions [data-radius-km="10"]').click();

    await expect.poll(() => nearbyRequests.length).toBeGreaterThan(1);
    expect(nearbyRequests.some((url) => url.includes("radius_km=10"))).toBeTruthy();
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

  test("mobile map controls align cleanly", async ({ page }) => {
    await page.goto("/");
    await page.waitForSelector("#mapFab", { timeout: 30000 });
    await page.locator("#mapFab").click();

    const keyBtn = page.locator("#mapOverlay [data-map-key-toggle]");
    const layerControl = page.locator("#mapOverlay .map-layer-control").first();
    const gpsControl = page.locator("#mapOverlay .map-gps-control").first();
    const zoomControl = page.locator("#mapOverlay .leaflet-control-zoom").first();
    const listBtn = page.locator("#mapOverlayClose");

    await expect(keyBtn).toBeVisible();
    await expect(layerControl).toBeVisible();
    await expect(gpsControl).toBeVisible();
    await expect(zoomControl).toBeVisible();
    await expect(listBtn).toBeVisible();

    const keyBox = await keyBtn.boundingBox();
    const layerBox = await layerControl.boundingBox();
    const gpsBox = await gpsControl.boundingBox();
    const zoomBox = await zoomControl.boundingBox();
    const listBox = await listBtn.boundingBox();

    expect(Math.abs(keyBox.y - layerBox.y)).toBeLessThanOrEqual(4);
    expect(Math.abs((layerBox.x + layerBox.width) - (gpsBox.x + gpsBox.width))).toBeLessThanOrEqual(2);
    expect(Math.abs((layerBox.x + layerBox.width) - (zoomBox.x + zoomBox.width))).toBeLessThanOrEqual(2);
    expect(gpsBox.y).toBeGreaterThan(layerBox.y + layerBox.height - 2);
    expect(zoomBox.y).toBeGreaterThan(gpsBox.y + gpsBox.height - 2);
    // The List button sits in the bottom bar, below the map controls.
    expect(listBox.y).toBeGreaterThan(zoomBox.y + zoomBox.height);
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
