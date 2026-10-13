// @ts-check
// Paid alert extras (priority check, daily shortlist) in My rentals.
const { test, expect } = require("@playwright/test");

const SHORTLIST = "daily_shortlist_day";
const INSTANT = "instant_alerts_day";

async function freshClient(page) {
  await page.goto("/");
  await page.evaluate(() => {
    const keep = new Set(["zr_welcomed", "zr_tour_done"]);
    for (const k of Object.keys(localStorage)) {
      if (k.startsWith("zr_") && !keep.has(k)) localStorage.removeItem(k);
    }
  });
  await page.reload();
  await page.waitForLoadState("networkidle");
  const clientId = await page.evaluate(() => localStorage.getItem("zr_client_id"));
  expect(clientId).toBeTruthy();
  return clientId;
}

function api(request, clientId) {
  const headers = { "X-Client-Id": clientId, "Content-Type": "application/json" };
  return {
    createAlert: async (label, filters) => {
      const res = await request.post("/api/alerts", { headers, data: { label, filters } });
      expect(res.ok()).toBeTruthy();
      return (await res.json()).id;
    },
    setUpgrade: (alertId, upgrade, enabled) =>
      request.post(`/api/alerts/${alertId}/upgrades/${upgrade}`, { headers, data: { enabled } }),
    state: async () => (await request.get("/api/alerts/upgrades", { headers })).json(),
  };
}

async function openAlerts(page) {
  await page.click("#alertsBellBtn");
  await expect(page.locator("#personalizationPanel .personalization-drawer")).toBeVisible();
}

function alertCard(page, alertId) {
  return page.locator(`#personalizationBody li[data-alert-id="${alertId}"]`);
}

test.describe("Paid alert extras", () => {
  test("offers only the daily shortlist, switched off by default", async ({ page, request }) => {
    const clientId = await freshClient(page);
    const alertId = await api(request, clientId).createAlert("Gulberg flats", { city: "lahore", area: "Gulberg" });
    await openAlerts(page);

    const card = alertCard(page, alertId);
    const priority = card.getByRole("switch", { name: "Priority check" });
    const shortlist = card.getByRole("switch", { name: "Daily shortlist" });
    await expect(priority).toHaveCount(0);
    await expect(shortlist).toHaveAttribute("aria-checked", "false");
    await expect(card).toContainText("1 credit per day with new matches, for this search");
    await expect(card).toContainText("Days with no new matches are free.");
    await expect(page.locator("#alertUpgradesSummary")).toContainText("Your balance: 10 credits");
    // Copy stays honest: no "instant" promise.
    await expect(card).not.toContainText(/instant/i);
  });

  test("enabling then stopping a shortlist does not spend credits before delivery", async ({ page, request }) => {
    const clientId = await freshClient(page);
    const client = api(request, clientId);
    const alertId = await client.createAlert("DHA houses", { city: "lahore", area: "DHA Defence" });
    await openAlerts(page);

    const card = alertCard(page, alertId);
    const shortlist = card.getByRole("switch", { name: "Daily shortlist" });
    await shortlist.click();
    await expect(shortlist).toHaveAttribute("aria-checked", "true");
    await expect(card).toContainText("On · 1 credit per day with new matches, for this search. Stop at any time.");
    await expect(page.locator("#alertUpgradesSummary")).toHaveText(
      "Daily shortlists use up to 1 credit a day across your enabled searches. Your balance: 10 credits."
    );
    expect((await client.state()).balance).toBe(10);

    // Keyboard works too: Space on the focused switch turns it off.
    await shortlist.focus();
    await page.keyboard.press("Space");
    await expect(shortlist).toHaveAttribute("aria-checked", "false");
    const after = await client.state();
    expect(after.balance).toBe(10); // switching off doesn't charge or refund today
    expect(after.alerts[String(alertId)][SHORTLIST].enabled).toBe(false);

    // Back on before delivery: still no charge, no second charge.
    await shortlist.click();
    await expect(shortlist).toHaveAttribute("aria-checked", "true");
    expect((await client.state()).balance).toBe(10);
  });

  test("not enough credits: inline message and the top-up event", async ({ page, request }) => {
    const clientId = await freshClient(page);
    const client = api(request, clientId);
    const target = await client.createAlert("Target alert", { city: "karachi", area: "Clifton" });
    // Exercise the 402 UI without running paid AI calls or the daily worker.
    await page.route(`**/api/alerts/${target}/upgrades/${SHORTLIST}`, route => route.fulfill({
      status: 402, json: { detail: { code: 'insufficient_credits', action: SHORTLIST, balance: 0, cost: 1 } },
    }));
    await page.evaluate(() => {
      window.__topups = [];
      window.addEventListener("zr:insufficient-credits", e => window.__topups.push(e.detail));
    });
    await openAlerts(page);
    const card = alertCard(page, target);
    await card.getByRole("switch", { name: "Daily shortlist" }).click();
    await expect(card.locator(".upg-msg")).toHaveText("Not enough credits. Daily shortlist needs 1 credit today; you have 0.");
    await expect(card.getByRole("switch", { name: "Daily shortlist" })).toHaveAttribute("aria-checked", "false");
    const topups = await page.evaluate(() => window.__topups);
    expect(topups).toEqual([{ code: "insufficient_credits", action: SHORTLIST, balance: 0, cost: 1 }]);
  });

  test("shortlist view lists picks with reasons", async ({ page, request }) => {
    const clientId = await freshClient(page);
    const client = api(request, clientId);
    const alertId = await client.createAlert("Clifton flats", { city: "karachi", area: "Clifton" });
    await client.setUpgrade(alertId, SHORTLIST, true);

    // Shortlists are built by the crawler's daily job; serve one here.
    await page.route("**/api/alerts/upgrades", async route => {
      const res = await route.fetch();
      const body = await res.json();
      body.alerts[String(alertId)].latest_shortlist = { day: body.today, match_count: 7, count: 2, seen: false };
      await route.fulfill({ response: res, json: body });
    });
    await page.route(`**/api/alerts/${alertId}/shortlists*`, route => route.fulfill({
      json: { shortlists: [{
        day: "2026-10-12", status: "delivered", match_count: 7, ranked_by: "fallback",
        items: [
          { zameen_id: "1", title: "Sea-facing flat", price: 85000, price_text: null,
            url: "https://www.zameen.com/Property/x-1-1-1.html", image_url: null,
            reason: "PKR 85,000 a month, PKR 15,000 under your budget.", trade_off: null },
          { zameen_id: "2", title: "Flat near Boat Basin", price: 95000, price_text: null,
            url: "https://www.zameen.com/Property/x-2-1-1.html", image_url: null,
            reason: "The newest match for this alert.", trade_off: "Third floor, no lift" },
        ],
      }] },
    }));

    await openAlerts(page);
    const card = alertCard(page, alertId);
    const button = card.getByRole("button", { name: /Today's shortlist \(2\)/ });
    await expect(button).toBeVisible();
    await expect(button).toContainText("New");
    await button.click();
    await expect(button).toHaveAttribute("aria-expanded", "true");
    const list = card.locator(".upg-shortlist");
    await expect(list).toContainText("2 of 7 new matches from the last 24 hours. Ordered by newest, then price fit.");
    await expect(list.locator("ol > li")).toHaveCount(2);
    await expect(list).toContainText("PKR 15,000 under your budget.");
    await expect(list).toContainText("Trade-off: Third floor, no lift");
    await expect(list.getByRole("link", { name: "Open on Zameen.com" }).first()).toHaveAttribute("target", "_blank");
    await button.click();
    await expect(button).toHaveAttribute("aria-expanded", "false");
    await expect(list).toBeHidden();
  });

  test("a paused alert can't be switched on", async ({ page, request }) => {
    const clientId = await freshClient(page);
    const client = api(request, clientId);
    const alertId = await client.createAlert("Paused one", { city: "lahore", area: "Gulberg" });
    await request.patch(`/api/alerts/${alertId}`, {
      headers: { "X-Client-Id": clientId, "Content-Type": "application/json" },
      data: { paused: true },
    });
    await openAlerts(page);
    const card = alertCard(page, alertId);
    await expect(card).toContainText("Resume this alert to use paid extras.");
    await expect(card.getByRole("switch", { name: "Daily shortlist" })).toBeDisabled();
  });

  test("fits the panel without sideways scrolling; switches are easy to tap", async ({ page, request }) => {
    const clientId = await freshClient(page);
    await api(request, clientId).createAlert("A long alert name for a narrow phone screen", {
      city: "islamabad", area: "F 10", bedrooms: 3, price_max: 150000,
    });
    await openAlerts(page);
    const body = page.locator("#personalizationBody");
    await expect(body.getByRole("switch", { name: "Daily shortlist" })).toBeVisible();
    const overflow = await body.evaluate(el => el.scrollWidth - el.clientWidth);
    expect(overflow).toBeLessThanOrEqual(0);
    for (const sw of await body.getByRole("switch").all()) {
      const box = await sw.boundingBox();
      expect(box?.width).toBeGreaterThanOrEqual(44);
      expect(box?.height).toBeGreaterThanOrEqual(44);
    }
  });
});
