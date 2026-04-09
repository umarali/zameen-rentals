// @ts-check
const { test, expect } = require("@playwright/test");

const MOBILE_VIEWPORTS = [
  { width: 375, height: 812 },
  { width: 320, height: 640 },
];

for (const viewport of MOBILE_VIEWPORTS) {
  test(`mobile layout stays within the viewport at ${viewport.width}px`, async ({
    page,
  }) => {
    await page.setViewportSize(viewport);
    await page.goto("/");
    await page.waitForSelector("#listingsGrid", { timeout: 30000 });
    await page.waitForTimeout(500);

    const metrics = await page.evaluate(() => {
      const selectors = [
        "html",
        "body",
        "header",
        "header .brand-link",
        "header > .flex-1",
        ".filter-bar-wrap",
        "#filterBar",
        "main",
        "#listingsPanel",
        "#listingsGrid",
        ".card-wrap",
        "#mapFab",
      ];

      const elements = selectors.map((selector) => {
        const el = document.querySelector(selector);
        if (!el) return { selector, missing: true };

        const rect = el.getBoundingClientRect();
        return {
          selector,
          left: Number(rect.left.toFixed(2)),
          right: Number(rect.right.toFixed(2)),
          width: Number(rect.width.toFixed(2)),
          scrollWidth: el.scrollWidth,
          clientWidth: el.clientWidth,
        };
      });

      return {
        viewportWidth: window.innerWidth,
        documentWidth: document.documentElement.scrollWidth,
        bodyWidth: document.body.scrollWidth,
        elements,
        overflowing: elements.filter(
          (el) => !el.missing && (el.left < -1 || el.right > window.innerWidth + 1)
        ),
      };
    });

    const details = JSON.stringify(metrics, null, 2);
    expect(metrics.documentWidth, details).toBeLessThanOrEqual(metrics.viewportWidth + 1);
    expect(metrics.bodyWidth, details).toBeLessThanOrEqual(metrics.viewportWidth + 1);
    expect(metrics.overflowing, details).toEqual([]);
  });
}

test("desktop header keeps vertical breathing room around the brand and search", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  await page.waitForSelector("header", { timeout: 30000 });

  const layout = await page.evaluate(() => {
    const header = document.querySelector("header");
    const brand = document.querySelector(".brand-link");
    const search = document.querySelector("header > .flex-1");
    const headerRect = header.getBoundingClientRect();
    const brandRect = brand.getBoundingClientRect();
    const searchRect = search.getBoundingClientRect();
    const styles = getComputedStyle(header);

    return {
      paddingTop: Number.parseFloat(styles.paddingTop),
      paddingBottom: Number.parseFloat(styles.paddingBottom),
      brandTopGap: Number((brandRect.top - headerRect.top).toFixed(2)),
      brandBottomGap: Number((headerRect.bottom - brandRect.bottom).toFixed(2)),
      searchTopGap: Number((searchRect.top - headerRect.top).toFixed(2)),
      searchBottomGap: Number((headerRect.bottom - searchRect.bottom).toFixed(2)),
    };
  });

  const details = JSON.stringify(layout, null, 2);
  expect(layout.paddingTop, details).toBeGreaterThanOrEqual(8);
  expect(layout.paddingBottom, details).toBeGreaterThanOrEqual(8);
  expect(layout.brandTopGap, details).toBeGreaterThan(0);
  expect(layout.brandBottomGap, details).toBeGreaterThan(0);
  expect(layout.searchTopGap, details).toBeGreaterThan(0);
  expect(layout.searchBottomGap, details).toBeGreaterThan(0);
});

test("desktop Karachi falls back to live city search when local viewport coverage is empty", async ({
  page,
}) => {
  await page.route("**/api/crawl-status**", async (route) => {
    await route.fulfill({
      json: {
        total_listings: 0,
        detail_coverage: 0,
        areas_crawled: 0,
        areas_total: 0,
        last_crawl_at: null,
      },
    });
  });

  let mapSearchCalls = 0;
  await page.route("**/api/map-search**", async (route) => {
    mapSearchCalls += 1;
    await route.fulfill({
      json: {
        total: 0,
        page: 1,
        per_page: 25,
        source: "local",
        mode: "viewport",
        visible_areas: 0,
        area_totals: {},
        ranking: "default",
        scope: "area_coverage",
        results: [],
      },
    });
  });

  await page.route("**/api/search?**", async (route) => {
    const url = new URL(route.request().url());
    const city = url.searchParams.get("city");
    await route.fulfill({
      json: {
        total: city === "karachi" ? 1 : 0,
        page: 1,
        per_page: 25,
        source: city === "karachi" ? "live" : "unavailable",
        results: city === "karachi" ? [
          {
            title: "2 bed flat in Karachi",
            url: "https://www.zameen.com/Property/karachi-test-1.html",
            price: 50000,
            property_type: "Apartment",
            location: "Clifton, Karachi",
            bedrooms: 2,
            bathrooms: 2,
            area_size: "950 sqft",
            image_url: "",
            has_exact_geography: false,
          },
        ] : [],
      },
    });
  });

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/?city=karachi");
  await page.waitForSelector("#listingsGrid .card-wrap", { timeout: 30000 });

  await expect(page.locator("#listingsTitle")).toHaveText("Rentals in Karachi");
  await expect(page.locator("#dataSource")).toHaveText("Live");
  await expect(page.locator("#listingsGrid")).toContainText("2 bed flat in Karachi");
  expect(mapSearchCalls).toBe(0);
});

test("standalone mode stacks the brand row above the search bar", async ({
  page,
}) => {
  await page.addInitScript(() => {
    const originalMatchMedia = window.matchMedia.bind(window);
    window.matchMedia = (query) => {
      if (query === '(display-mode: standalone)') {
        return {
          matches: true,
          media: query,
          onchange: null,
          addListener() {},
          removeListener() {},
          addEventListener() {},
          removeEventListener() {},
          dispatchEvent() { return false; },
        };
      }
      if (query.startsWith('(display-mode:')) {
        return {
          matches: false,
          media: query,
          onchange: null,
          addListener() {},
          removeListener() {},
          addEventListener() {},
          removeEventListener() {},
          dispatchEvent() { return false; },
        };
      }
      return originalMatchMedia(query);
    };
  });

  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto("/");
  await page.waitForSelector("header", { timeout: 30000 });

  const layout = await page.evaluate(() => {
    const root = document.documentElement;
    const brand = document.querySelector('.brand-link');
    const search = document.querySelector('header > .flex-1');
    const clearButton = document.getElementById('clearAllBtn');
    const brandRect = brand.getBoundingClientRect();
    const searchRect = search.getBoundingClientRect();
    const clearRect = clearButton.getBoundingClientRect();

    return {
      standaloneClass: root.classList.contains('app-standalone'),
      brandBottom: Number(brandRect.bottom.toFixed(2)),
      searchTop: Number(searchRect.top.toFixed(2)),
      searchWidth: Number(searchRect.width.toFixed(2)),
      clearTop: Number(clearRect.top.toFixed(2)),
    };
  });

  const details = JSON.stringify(layout, null, 2);
  expect(layout.standaloneClass, details).toBeTruthy();
  expect(layout.searchTop, details).toBeGreaterThan(layout.brandBottom);
  expect(layout.searchWidth, details).toBeGreaterThanOrEqual(340);
});

test("desktop standalone keeps the header on one row", async ({
  page,
}) => {
  await page.addInitScript(() => {
    const originalMatchMedia = window.matchMedia.bind(window);
    window.matchMedia = (query) => {
      if (query === '(display-mode: standalone)') {
        return {
          matches: true,
          media: query,
          onchange: null,
          addListener() {},
          removeListener() {},
          addEventListener() {},
          removeEventListener() {},
          dispatchEvent() { return false; },
        };
      }
      if (query.startsWith('(display-mode:')) {
        return {
          matches: false,
          media: query,
          onchange: null,
          addListener() {},
          removeListener() {},
          addEventListener() {},
          removeEventListener() {},
          dispatchEvent() { return false; },
        };
      }
      return originalMatchMedia(query);
    };
  });

  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto("/");
  await page.waitForSelector("header", { timeout: 30000 });

  const layout = await page.evaluate(() => {
    const root = document.documentElement;
    const brand = document.querySelector('.brand-link');
    const search = document.querySelector('header > .flex-1');
    const brandRect = brand.getBoundingClientRect();
    const searchRect = search.getBoundingClientRect();

    return {
      standaloneClass: root.classList.contains('app-standalone'),
      brandTop: Number(brandRect.top.toFixed(2)),
      brandBottom: Number(brandRect.bottom.toFixed(2)),
      searchTop: Number(searchRect.top.toFixed(2)),
      searchBottom: Number(searchRect.bottom.toFixed(2)),
    };
  });

  const details = JSON.stringify(layout, null, 2);
  expect(layout.standaloneClass, details).toBeTruthy();
  expect(Math.abs(layout.searchTop - layout.brandTop), details).toBeLessThanOrEqual(4);
  expect(layout.searchBottom, details).toBeGreaterThan(layout.brandBottom - 4);
  expect(layout.searchTop, details).toBeLessThan(layout.brandBottom);
});

test("standalone mode keeps mobile coverage hidden", async ({
  page,
}) => {
  await page.addInitScript(() => {
    const originalMatchMedia = window.matchMedia.bind(window);
    window.matchMedia = (query) => {
      if (query === '(display-mode: standalone)') {
        return {
          matches: true,
          media: query,
          onchange: null,
          addListener() {},
          removeListener() {},
          addEventListener() {},
          removeEventListener() {},
          dispatchEvent() { return false; },
        };
      }
      if (query.startsWith('(display-mode:')) {
        return {
          matches: false,
          media: query,
          onchange: null,
          addListener() {},
          removeListener() {},
          addEventListener() {},
          removeEventListener() {},
          dispatchEvent() { return false; },
        };
      }
      return originalMatchMedia(query);
    };
  });

  await page.route("**/api/crawl-status**", async (route) => {
    await route.fulfill({
      json: {
        total_listings: 24,
        detail_coverage: 100,
        areas_crawled: 3,
        areas_total: 3,
        last_crawl_at: "2026-04-09T19:00:00",
      },
    });
  });

  await page.route("**/api/map-search**", async (route) => {
    await route.fulfill({
      json: {
        total: 2,
        page: 1,
        per_page: 25,
        source: "local",
        mode: "viewport",
        visible_areas: 3,
        area_totals: { Clifton: 1, Saddar: 1 },
        ranking: "map_focus",
        scope: "area_coverage",
        results: [
          {
            title: "Coverage test listing",
            url: "https://www.zameen.com/Property/coverage-test-1.html",
            price: 90000,
            property_type: "Apartment",
            location: "Clifton, Karachi",
            latitude: 24.821,
            longitude: 67.031,
            has_exact_geography: true,
          },
        ],
      },
    });
  });

  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto("/");
  await page.waitForSelector("#mapFab", { timeout: 30000 });
  await page.locator("#mapFab").click();

  await expect(page.locator("#mapCoverageBadgeMobile")).toBeHidden();
});

test("standalone tablet-width overlay still shows coverage", async ({
  page,
}) => {
  await page.addInitScript(() => {
    const originalMatchMedia = window.matchMedia.bind(window);
    window.matchMedia = (query) => {
      if (query === '(display-mode: standalone)') {
        return {
          matches: true,
          media: query,
          onchange: null,
          addListener() {},
          removeListener() {},
          addEventListener() {},
          removeEventListener() {},
          dispatchEvent() { return false; },
        };
      }
      if (query.startsWith('(display-mode:')) {
        return {
          matches: false,
          media: query,
          onchange: null,
          addListener() {},
          removeListener() {},
          addEventListener() {},
          removeEventListener() {},
          dispatchEvent() { return false; },
        };
      }
      return originalMatchMedia(query);
    };
  });

  await page.route("**/api/crawl-status**", async (route) => {
    await route.fulfill({
      json: {
        total_listings: 24,
        detail_coverage: 100,
        areas_crawled: 3,
        areas_total: 3,
        last_crawl_at: "2026-04-09T19:00:00",
      },
    });
  });

  await page.route("**/api/map-search**", async (route) => {
    await route.fulfill({
      json: {
        total: 2,
        page: 1,
        per_page: 25,
        source: "local",
        mode: "viewport",
        visible_areas: 3,
        area_totals: { Clifton: 1, Saddar: 1 },
        ranking: "map_focus",
        scope: "area_coverage",
        results: [
          {
            title: "Coverage test listing",
            url: "https://www.zameen.com/Property/coverage-test-1.html",
            price: 90000,
            property_type: "Apartment",
            location: "Clifton, Karachi",
            latitude: 24.821,
            longitude: 67.031,
            has_exact_geography: true,
          },
        ],
      },
    });
  });

  await page.setViewportSize({ width: 900, height: 900 });
  await page.goto("/");
  await page.waitForSelector("#mapFab", { timeout: 30000 });
  await page.locator("#mapFab").click();

  const badge = page.locator("#mapCoverageBadgeMobile");
  await expect(badge).toBeVisible();
  await expect(badge).not.toHaveClass(/coverage-badge-compact/);
  await expect(badge).toContainText("Map Coverage");
});
