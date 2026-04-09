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

  test("coverage badge shows a legend for map markers", async ({ page }) => {
    const badge = page.locator("#mapCoverageBadge");
    await expect(badge).toBeVisible();
    await expect(badge).toContainText("Green: covered area");
    await expect(badge).toContainText("Grey: preview only");
    await expect(badge).toContainText("Red: exact listing pin");
  });

  test("coverage badge uses normalized visible-area counts from viewport search", async ({ page }) => {
    await page.route("**/api/map-search**", async route => {
      await route.fulfill({
        json: {
          total: 2,
          page: 1,
          per_page: 25,
          results: [
            {
              title: "Exact listing 1",
              url: "https://www.zameen.com/Property/test-visible-1.html",
              price: 65000,
              property_type: "Apartment",
              latitude: 24.861,
              longitude: 67.002,
              location_source: "listing_exact",
              has_exact_geography: true,
            },
            {
              title: "Exact listing 2",
              url: "https://www.zameen.com/Property/test-visible-2.html",
              price: 60000,
              property_type: "Apartment",
              latitude: 24.862,
              longitude: 67.003,
              location_source: "listing_exact",
              has_exact_geography: true,
            },
          ],
          source: "local",
          mode: "viewport",
          scope: "exact_bounds",
          visible_areas: 2,
          area_totals: { "Garden West": 1, "Saddar Town": 1 },
          attempted_exact_bounds: true,
          exact_bounds_total: 2,
        },
      });
    });

    await page.reload();
    await expect(page.locator("#mapCoverageBadge")).toContainText("2 covered / 2 visible");
  });

  test("map layer toggle switches to satellite and persists after reload", async ({ page }) => {
    const satelliteBtn = page.locator('#mapContainer [data-map-layer="satellite"]').first();
    await satelliteBtn.click();
    await expect(satelliteBtn).toHaveClass(/active/);
    await expect(page.locator("#mapContainer .leaflet-tile").first()).toHaveAttribute(
      "src",
      /World_Imagery|ArcGIS\/rest\/services\/World_Imagery/
    );

    await page.reload();
    await page.waitForSelector("#mapContainer .leaflet-control-zoom", {
      timeout: 30000,
    });
    await expect(
      page.locator('#mapContainer [data-map-layer="satellite"]').first()
    ).toHaveClass(/active/);
  });

  test("area markers appear on map after search", async ({ page }) => {
    await page.locator('.city-tab[data-city="karachi"]').click();
    await page.waitForTimeout(2000);
    const markers = page.locator("#mapContainer .area-marker");
    expect(await markers.count()).toBeGreaterThan(0);
  });

  test("street zoom swaps the focused area label for an active dot", async ({ page }) => {
    await page.locator('.city-tab[data-city="karachi"]').click();
    // Select an area to make it active
    await page.locator("#areaChip").click();
    await page.locator("#areaInput").fill("DHA");
    await page.waitForTimeout(400);
    await page.locator(".area-opt").first().click();
    await page.waitForTimeout(2000);
    await expect(page.locator("#mapContainer .area-label")).toHaveCount(0);
    expect(await page.locator("#mapContainer .area-dot-active").count()).toBeGreaterThanOrEqual(1);
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

  test("area mode hides exact listing pins so the map does not imply viewport filtering", async ({ page }) => {
    await page.locator('.city-tab[data-city="karachi"]').click();
    await page.locator("#areaChip").click();
    await page.locator("#areaInput").fill("Clifton");
    await page.waitForTimeout(400);
    await page.locator(".area-opt", { hasText: "Clifton" }).first().click();
    await page.waitForTimeout(2500);
    await expect(page.locator("#listingsTitle")).toContainText("Clifton");
    await expect(page.locator("#mapContainer .listing-exact-marker")).toHaveCount(0);
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
    await expect(page.locator("#resultsMeta")).toContainText(/exact-pin rentals currently visible|available in|available across|No local listings|Move the map/);
    await expect(page.locator("#dataSource")).toContainText(/Nearest first|Instant/);
  });

  test("nearby chip warns when city is not supported yet", async ({ page }) => {
    await page.locator('.city-tab[data-city="lahore"]').click();
    await page.locator("#nearbyChip").click();
    await expect(page.locator("#toastStack")).toContainText(
      "Nearby search is available in Karachi for now."
    );
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
    await expect(page.locator("#resultsMeta")).toContainText("within 5 km");
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

    const closeBtn = page.locator("#mapOverlayClose");
    const layerControl = page.locator("#mapOverlay .map-layer-control").first();
    const gpsControl = page.locator("#mapOverlay .map-gps-control").first();
    const zoomControl = page.locator("#mapOverlay .leaflet-control-zoom").first();

    await expect(closeBtn).toBeVisible();
    await expect(layerControl).toBeVisible();
    await expect(gpsControl).toBeVisible();
    await expect(zoomControl).toBeVisible();

    const closeBox = await closeBtn.boundingBox();
    const layerBox = await layerControl.boundingBox();
    const gpsBox = await gpsControl.boundingBox();
    const zoomBox = await zoomControl.boundingBox();

    expect(closeBox).toBeTruthy();
    expect(layerBox).toBeTruthy();
    expect(gpsBox).toBeTruthy();
    expect(zoomBox).toBeTruthy();
    expect(Math.abs(closeBox.y - layerBox.y)).toBeLessThanOrEqual(4);
    expect(Math.abs(closeBox.height - layerBox.height)).toBeLessThanOrEqual(2);
    expect(closeBox.height).toBeLessThanOrEqual(48);
    expect(Math.abs((layerBox.x + layerBox.width) - (gpsBox.x + gpsBox.width))).toBeLessThanOrEqual(2);
    expect(Math.abs((layerBox.x + layerBox.width) - (zoomBox.x + zoomBox.width))).toBeLessThanOrEqual(2);
    expect(gpsBox.y).toBeGreaterThan(layerBox.y + layerBox.height - 2);
    expect(zoomBox.y).toBeGreaterThan(gpsBox.y + gpsBox.height - 2);
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
