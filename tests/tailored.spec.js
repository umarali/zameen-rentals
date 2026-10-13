// @ts-check
// Paid AI features: tailored list and search report.
// The paid endpoints are mocked with page.route, so these tests never call
// Claude; /api/credits and the report eligibility check use the real backend.
const { test, expect } = require("@playwright/test");

const LISTING = (id, extra = {}) => ({
  zameen_id: String(id),
  url: `https://www.zameen.com/Property/test-${id}-1-1.html`,
  title: `Apartment ${id}`,
  price: 70000,
  bedrooms: 2,
  bathrooms: 2,
  area_size: "5 Marla",
  location: "Gulberg, Lahore",
  property_type: "Apartment / Flat",
  ...extra,
});

const TAILORED_OK = {
  results: [
    { ...LISTING(99000049), ai_reason: "PKR 70,000 for 2 bedrooms in Gulberg, within budget.", ai_trade_off: "Parking not mentioned." },
    { ...LISTING(99000050, { price: 75000 }), ai_reason: "Second floor flat with a lift.", ai_trade_off: "Quietness not stated." },
  ],
  understood: { city: "lahore", filters: { area: "Gulberg", bedrooms: 2, price_max: 80000 }, preferences: ["parking", "not ground floor"] },
  relaxed: ["Also included 3 bedroom homes."],
  candidates_considered: 14,
  source: "Zameen.com",
  charged: true,
  cached: false,
  cost: 1,
  balance: 9,
};

async function gotoApp(page) {
  await page.goto("/");
  await page.evaluate(() => {
    const keep = new Set(["zr_welcomed", "zr_tour_done"]);
    for (const k of Object.keys(localStorage)) if (k.startsWith("zr_") && !keep.has(k)) localStorage.removeItem(k);
  });
  await page.reload();
  await page.waitForLoadState("networkidle");
}

async function openTailored(page) {
  await page.locator("#nlInput").click();
  const entry = page.locator("#tailoredEntry");
  await expect(entry).toBeVisible();
  await entry.click();
  const dialog = page.locator('#tailoredModal [role="dialog"]');
  await expect(dialog).toBeVisible();
  return dialog;
}

test.describe("Tailored list", () => {
  test("shows the cost from the server before running", async ({ page }) => {
    await gotoApp(page);
    const dialog = await openTailored(page);
    await expect(dialog.locator("[data-tl-cost]")).toHaveText(/Uses 1 credit\. You have \d+\./);
    await expect(page.locator("#tailoredBrief")).toBeFocused();
    const box = await dialog.boundingBox();
    const viewport = page.viewportSize();
    expect(box && viewport && box.width <= viewport.width).toBeTruthy();
  });

  test("runs, shows ranked listings with reasons and opens one in the drawer", async ({ page }) => {
    await gotoApp(page);
    let sent = null;
    await page.route("**/api/ai/tailored", async route => {
      sent = { body: route.request().postDataJSON(), headers: route.request().headers() };
      await new Promise(r => setTimeout(r, 300));
      await route.fulfill({ json: TAILORED_OK });
    });
    const dialog = await openTailored(page);
    await page.locator("#tailoredBrief").fill("2 bed in Gulberg under 80k, parking, not ground floor");
    await dialog.locator("[data-tl-run]").click();
    await expect(dialog.locator("[data-tl-run]")).toBeDisabled();
    await expect(dialog.locator("[data-tl-results]")).toBeVisible();

    expect(sent.body).toMatchObject({ brief: "2 bed in Gulberg under 80k, parking, not ground floor", city: expect.any(String) });
    expect(sent.headers["idempotency-key"]).toMatch(/^[A-Za-z0-9_-]{8,64}$/);
    expect(sent.headers["x-client-id"]).toBeTruthy();

    const items = dialog.locator("[data-tl-item]");
    await expect(items).toHaveCount(2);
    await expect(items.first()).toContainText("Why it fits: PKR 70,000 for 2 bedrooms");
    await expect(items.first()).toContainText("Trade-off: Parking not mentioned.");
    await expect(dialog).toContainText("Also included 3 bedroom homes.");
    await expect(dialog).toContainText("not ground floor");
    await expect(dialog).toContainText("Listings from Zameen.com");
    await expect(dialog).toContainText("Used 1 credit.");

    await items.first().locator("[data-tl-open]").click();
    await expect(page.locator("#drawerOverlay")).toHaveClass(/overlay-open/);
  });

  test("insufficient credits shows an inline message and fires the top-up event", async ({ page }) => {
    await gotoApp(page);
    await page.evaluate(() => {
      window.__topups = [];
      window.addEventListener("zr:insufficient-credits", e => window.__topups.push(e.detail));
    });
    await page.route("**/api/ai/tailored", route => route.fulfill({
      status: 402,
      json: { detail: { code: "insufficient_credits", action: "tailored_list", balance: 0, cost: 1 } },
    }));
    const dialog = await openTailored(page);
    await page.locator("#tailoredBrief").fill("3 bed house in DHA under 1.5 lakh");
    await dialog.locator("[data-tl-run]").click();
    await expect(dialog.locator("[data-tl-error]")).toHaveText("You need 1 credit and have 0. Add credits to continue.");
    expect(await page.evaluate(() => window.__topups)).toEqual([
      { code: "insufficient_credits", action: "tailored_list", balance: 0, cost: 1 },
    ]);
    await expect(dialog.locator("[data-tl-run]")).toBeEnabled();
  });

  test("a retry of the same brief after an error reuses the idempotency key", async ({ page }) => {
    await gotoApp(page);
    const keys = [];
    let calls = 0;
    await page.route("**/api/ai/tailored", route => {
      keys.push(route.request().headers()["idempotency-key"]);
      calls += 1;
      return calls === 1
        ? route.fulfill({ status: 503, json: { detail: "The AI service is unavailable right now. Your credits were not used." } })
        : route.fulfill({ json: TAILORED_OK });
    });
    const dialog = await openTailored(page);
    await page.locator("#tailoredBrief").fill("2 bed flat Gulberg 80k tak, parking");
    await dialog.locator("[data-tl-run]").click();
    await expect(dialog.locator("[data-tl-error]")).toContainText("Your credits were not used.");
    await dialog.locator("[data-tl-run]").click();
    await expect(dialog.locator("[data-tl-results]")).toBeVisible();
    expect(keys).toHaveLength(2);
    expect(keys[0]).toBe(keys[1]);
  });

  test("short briefs are stopped before any request; Escape closes", async ({ page }) => {
    await gotoApp(page);
    let called = false;
    await page.route("**/api/ai/tailored", route => { called = true; return route.abort(); });
    const dialog = await openTailored(page);
    await page.locator("#tailoredBrief").fill("flat");
    await dialog.locator("[data-tl-run]").click();
    await expect(dialog.locator("[data-tl-error]")).toContainText("at least 10 characters");
    expect(called).toBe(false);
    await page.keyboard.press("Escape");
    await expect(page.locator("#tailoredModal")).toHaveClass(/(?:^|\s)hidden(?:\s|$)/);
  });
});

test.describe("Search report", () => {
  async function openReport(page) {
    await page.click("#alertsBellBtn");
    const btn = page.locator("#searchReportBtn");
    await expect(btn).toBeVisible();
    await btn.click();
    const dialog = page.locator('#searchReportModal [role="dialog"]');
    await expect(dialog).toBeVisible();
    return dialog;
  }

  test("with no activity it explains why and offers no paid action", async ({ page }) => {
    await gotoApp(page);
    const dialog = await openReport(page);
    await expect(dialog.locator("[data-report-ineligible]")).toContainText("Get alerts");
    await expect(dialog.locator("[data-report-ineligible]")).toContainText("No credits were used.");
    await expect(dialog.locator("[data-report-run]")).toHaveCount(0);
    // Escape closes the report but leaves My rentals open underneath.
    await page.keyboard.press("Escape");
    await expect(page.locator("#searchReportModal")).toHaveClass(/(?:^|\s)hidden(?:\s|$)/);
    await expect(page.locator("#personalizationPanel")).not.toHaveClass(/(?:^|\s)hidden(?:\s|$)/);
  });

  test("runs and shows the SQL figures with the write-up", async ({ page }) => {
    await gotoApp(page);
    await page.route("**/api/ai/report/eligibility", route => route.fulfill({
      json: { eligible: true, reason: "", activity: { alerts: 1, favorites: 3, recent_views: 4, hidden: 0 }, cost: 1, balance: 10 },
    }));
    await page.route("**/api/ai/report", route => route.fulfill({
      json: {
        report: {
          headline: "Median rent is PKR 70,000",
          summary: "There are 12 homes matching your alert.",
          suggestions: [{ title: "Raise your budget a little", detail: "With PKR 92,000 you would have 24 homes." }],
        },
        sections: [{
          label: "Your alert: 2 bed in Gulberg under 80K", source: "alert", criteria: { city: "lahore", area: "Gulberg" },
          criteria_text: "2 bed in Gulberg up to PKR 80,000",
          stats: {
            matching: 12, rent: { min: 50000, p25: 60000, median: 70000, p75: 78000, max: 80000 },
            rent_per_marla_median: 14000, first_seen_last_7_days: 3, size_marla_median: 5,
            budget_steps: [{ pct: 10, budget: 88000, matching: 18 }],
            nearby_areas: [{ area: "Model Town", km: 2.1, count: 9, median: 65000 }],
          },
          facts: [],
        }],
        activity: { alerts: 1, favorites: 3, recent_views: 4, hidden: 0 },
        generated_at: "2026-10-11T10:00:00+00:00", source: "Zameen.com",
        charged: true, cached: false, cost: 1, balance: 9,
      },
    }));
    const dialog = await openReport(page);
    await expect(dialog).toContainText("1 alert, 3 saved homes, 4 opened homes");
    await expect(dialog.locator("[data-report-cost]")).toHaveText(/Uses 1 credit\./);
    await dialog.locator("[data-report-run]").click();
    const result = dialog.locator("[data-report-result]");
    await expect(result).toContainText("Median rent is PKR 70,000");
    await expect(result).toContainText("Raise your budget a little.");
    await expect(result).toContainText("PKR 60,000 to PKR 78,000");
    await expect(result).toContainText("+10% (PKR 88,000): 18 homes");
    await expect(result).toContainText("Model Town (2.1 km): 9 homes");
    await expect(result).toContainText("sourced from Zameen.com");
    await expect(result).toContainText("Used 1 credit.");
  });
});
