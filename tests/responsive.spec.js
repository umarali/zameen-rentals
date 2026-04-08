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

test("standalone mode collapses map coverage into a side dock", async ({
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

  const badge = page.locator("#mapCoverageBadgeMobile");
  await expect(badge).toBeVisible();
  await expect(badge).toHaveClass(/coverage-badge-compact/);
  await expect(badge).toContainText("Coverage");

  await badge.locator(".coverage-toggle").click();
  await expect(badge).toHaveClass(/coverage-badge-expanded/);
  await expect(badge).toContainText("Map Coverage");
});
