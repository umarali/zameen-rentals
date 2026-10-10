// @ts-check
const { test, expect } = require("@playwright/test");

// The backend stores UTC without an offset. A browser in Pakistan (UTC+5) used
// to read those times as local, so a listing seeded "Added: 1 hour ago"
// showed "Added 6 hours ago".
test.describe("Listing dates in a Pakistan browser", () => {
  test.use({ timezoneId: "Asia/Karachi" });

  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await page.waitForSelector(".card-wrap", { timeout: 30000 });
  });

  test("card shows Zameen's date at the seeded age", async ({ page }) => {
    const date = page.locator(".card-wrap").first().locator(".listing-date");
    await expect(date).toContainText(/(Added|Updated) (1 hour|\d+ minutes) ago/);
    await expect(date).not.toContainText(/[5-7] hours ago/);
  });

  test("tapping ⓘ explains the date without opening the drawer", async ({ page }) => {
    const card = page.locator(".card-wrap").first();
    const info = card.locator(".date-info");
    const tip = card.locator(".date-tip");
    await expect(tip).toBeHidden();
    await info.click();
    await expect(info).toHaveAttribute("aria-expanded", "true");
    await expect(tip).toBeVisible();
    await expect(tip).toContainText("Agents can refresh Zameen dates, so the ad may be older.");
    await expect(tip).toContainText(/On ZameenRentals since \d{1,2} [A-Z][a-z]{2}/);
    await expect(tip).toContainText("Availability not confirmed");
    await expect(page.locator("#drawer")).not.toHaveClass(/drawer-open/);
    await page.keyboard.press("Escape");
    await page.mouse.move(0, 0); // desktop also shows it on hover
    await expect(tip).toBeHidden();
  });

  test("shows both Zameen dates only when they differ", async ({ page }) => {
    // Naive UTC, like the backend writes.
    const ago = ms => new Date(Date.now() - ms).toISOString().slice(0, 19);
    const listing = (id, posted, updated) => ({
      zameen_id: id, title: `Flat ${id}`, url: `https://www.zameen.com/Property/x-${id}-1-1.html`,
      price: 90000, location: "Clifton, Karachi", property_type: "Apartment",
      posted_at: posted, updated_at: updated, first_seen_at: ago(3 * 864e5),
    });
    const payload = { total: 2, page: 1, per_page: 25, source: "local", results: [
      listing("1", ago(14 * 864e5), ago(3 * 36e5)),
      listing("2", ago(3 * 36e5), ago(3 * 36e5)),
    ] };
    await page.route("**/api/search**", route => route.fulfill({ json: payload }));
    await page.route("**/api/map-search**", route => route.fulfill({ json: payload }));
    await page.reload();
    await page.waitForSelector(".card-wrap", { timeout: 30000 });
    const dates = page.locator(".card-wrap .listing-date");
    await expect(dates.nth(0)).toContainText("Added 2 weeks ago · Updated 3 hours ago");
    await expect(dates.nth(1)).toHaveText(/^\s*Added 3 hours ago\s*Agents/);
  });

  test("drawer shows the same date line", async ({ page }) => {
    await page.locator(".card-wrap").first().locator("h3, .line-clamp-1").first().click();
    await expect(page.locator("#drawer")).toHaveClass(/drawer-open/, { timeout: 5000 });
    await expect(page.locator("#drawerDates")).toContainText(/(Added|Updated) (1 hour|\d+ minutes) ago/);
  });
});
