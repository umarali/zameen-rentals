// @ts-check
const { test, expect } = require("@playwright/test");

// Furnishing has three states. "Unfurnished" must send furnished=false and
// "Any" must send no furnished param. Fixture titles start "Furnished",
// "Unfurnished", "Non Furnished" or "Brand new" (no evidence, so only under
// "Any"); see tests/serve_playwright.py.

const UNFURNISHED_TITLE = /^(Unfurnished|Non Furnished) /;

function isListingSearch(response, { area } = {}) {
  if (!response.ok()) return false;
  const url = new URL(response.url());
  if (!["/api/search", "/api/map-search"].includes(url.pathname)) return false;
  return area === undefined || url.searchParams.get("area") === area;
}

const furnishedParam = (response) => new URL(response.url()).searchParams.get("furnished");

// Every listing request the page sends, in order. Checking these, not just the
// response a test waits for, catches a request sent before saved filters apply.
function recordListingRequests(page) {
  const sent = [];
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (["/api/search", "/api/map-search"].includes(url.pathname)) sent.push(url.searchParams);
  });
  return sent;
}

async function resultTitles(response) {
  const titles = (await response.json()).results.map((r) => r.title);
  expect(titles.length).toBeGreaterThan(0);
  return titles;
}

async function nlSearch(page, query) {
  const searched = page.waitForResponse((r) => isListingSearch(r, { area: "Gulberg" }));
  await page.locator("#nlInput").fill(query);
  await page.locator("#nlInput").press("Enter");
  return searched;
}

test.describe("Furnishing filter", () => {
  test("furnished then unfurnished searches request each state; Any clears it", async ({ page }) => {
    await page.goto("/?city=lahore");
    await expect(page.locator(".card-wrap").first()).toBeVisible();

    const furnished = await nlSearch(page, "furnished apartment in Gulberg Lahore");
    expect(furnishedParam(furnished)).toBe("true");
    for (const title of await resultTitles(furnished)) expect(title).toMatch(/^Furnished /);
    await expect(page.locator('#nlUnderstood [data-chip-field="furnishing"]')).toHaveText(/^Furnished/);

    const unfurnished = await nlSearch(page, "unfurnished apartment in Gulberg Lahore");
    expect(furnishedParam(unfurnished)).toBe("false");
    for (const title of await resultTitles(unfurnished)) expect(title).toMatch(UNFURNISHED_TITLE);
    await expect(page.locator('#nlUnderstood [data-chip-field="furnishing"]')).toHaveText(/^Unfurnished/);
    await expect(page.locator(".card-wrap").first()).toContainText(/Unfurnished|Non Furnished/);
    await expect(page.locator("#moreChip")).toHaveClass(/has-value/);
    await expect.poll(() => new URL(page.url()).searchParams.get("furnished")).toBe("0");
    await expect.poll(() => page.evaluate(() => JSON.parse(localStorage.getItem("rk_s") || "{}").furnishing))
      .toBe("unfurnished");

    await page.locator("#moreChip").click();
    await expect(page.locator('#furnishingRow [data-furnishing="unfurnished"]')).toHaveClass(/active/);
    await expect(page.locator('#furnishingRow [data-furnishing="furnished"]')).not.toHaveClass(/active/);

    const anySearch = page.waitForResponse((r) => isListingSearch(r, { area: "Gulberg" }));
    await page.locator('#furnishingRow [data-furnishing=""]').click();
    const any = await anySearch;
    expect(furnishedParam(any)).toBeNull();
    // Listings that say nothing about furniture are back under "Any".
    expect(await resultTitles(any)).toContainEqual(expect.stringMatching(/^Brand new /));
    await expect(page.locator('#nlUnderstood [data-chip-field="furnishing"]')).toHaveCount(0);
    await expect.poll(() => new URL(page.url()).searchParams.get("furnished")).toBeNull();
  });

  test("Understood chip × removes unfurnished without touching sort", async ({ page }) => {
    await page.goto("/?city=lahore");
    await expect(page.locator(".card-wrap").first()).toBeVisible();
    const unfurnished = await nlSearch(page, "sasta unfurnished apartment in Gulberg Lahore");
    expect(furnishedParam(unfurnished)).toBe("false");
    expect(new URL(unfurnished.url()).searchParams.get("sort")).toBe("price_low");

    const cleared = page.waitForResponse((r) => isListingSearch(r, { area: "Gulberg" }));
    await page.locator('#nlUnderstood [data-chip-remove="furnishing"]').click();
    const response = await cleared;
    expect(furnishedParam(response)).toBeNull();
    expect(new URL(response.url()).searchParams.get("sort")).toBe("price_low");
  });

  test("unfurnished in the URL survives a reload", async ({ page }) => {
    const sent = recordListingRequests(page);
    let searched = page.waitForResponse((r) => isListingSearch(r, { area: "Gulberg" }));
    await page.goto("/?city=lahore&area=Gulberg&furnished=0");
    expect(furnishedParam(await searched)).toBe("false");
    await expect(page.locator(".card-wrap").first()).toBeVisible();
    expect(sent.length).toBeGreaterThan(0);
    for (const params of sent) {
      expect(params.get("area")).toBe("Gulberg");
      expect(params.get("furnished")).toBe("false");
    }

    sent.length = 0;
    searched = page.waitForResponse((r) => isListingSearch(r, { area: "Gulberg" }));
    await page.reload();
    const response = await searched;
    expect(furnishedParam(response)).toBe("false");
    await expect(page.locator(".card-wrap").first()).toBeVisible();
    for (const params of sent) expect(params.get("furnished")).toBe("false");
    for (const title of await resultTitles(response)) expect(title).toMatch(UNFURNISHED_TITLE);
    await page.locator("#moreChip").click();
    await expect(page.locator('#furnishingRow [data-furnishing="unfurnished"]')).toHaveClass(/active/);
  });

  for (const [stored, expected] of [[false, null], [true, "true"]]) {
    test(`a search saved before three states with furnished=${stored} loads as ${expected ?? "no preference"}`, async ({ page }) => {
      await page.addInitScript((furnished) => {
        localStorage.setItem("rk_s", JSON.stringify({ city: "lahore", area: "Gulberg", furnished, sort: "" }));
      }, stored);
      const sent = recordListingRequests(page);
      const searched = page.waitForResponse((r) => isListingSearch(r, { area: "Gulberg" }));
      await page.goto("/");
      expect(furnishedParam(await searched)).toBe(expected);
      await expect(page.locator(".card-wrap").first()).toBeVisible();
      expect(sent.length).toBeGreaterThan(0);
      for (const params of sent) {
        expect(params.get("area")).toBe("Gulberg");
        expect(params.get("furnished")).toBe(expected);
      }
      if (expected === null) await expect(page.locator("#moreChip")).not.toHaveClass(/has-value/);
      else await expect(page.locator("#moreChip")).toHaveClass(/has-value/);
    });
  }

  test("map browsing and Near Me both send unfurnished", async ({ page, context }) => {
    await page.route("**/api/listing-detail?**", (route) => route.fulfill({ json: {} }));
    await context.grantPermissions(["geolocation"]);
    await context.setGeolocation({ latitude: 31.522361, longitude: 74.347172 });

    const sent = recordListingRequests(page);
    const browse = page.waitForResponse((r) => isListingSearch(r) &&
      new URL(r.url()).searchParams.get("city") === "lahore");
    await page.goto("/?city=lahore&furnished=0");
    const browsed = await browse;
    expect(furnishedParam(browsed)).toBe("false");
    for (const params of sent) expect(params.get("furnished")).toBe("false");
    for (const title of await resultTitles(browsed)) expect(title).toMatch(UNFURNISHED_TITLE);

    const nearby = page.waitForResponse((r) => r.ok() && new URL(r.url()).pathname === "/api/nearby-search");
    await page.locator("#nearbyChip").click();
    const response = await nearby;
    expect(furnishedParam(response)).toBe("false");
    for (const title of await resultTitles(response)) expect(title).toMatch(UNFURNISHED_TITLE);
  });
});
