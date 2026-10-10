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

  test("card shows when we first saw the listing, not Zameen's date", async ({ page }) => {
    const text = await page.locator(".card-wrap").first().textContent();
    expect(text).toMatch(/First seen by us \d{1,2} [A-Z][a-z]{2}/);
    expect(text).not.toMatch(/Added \d/);
  });

  test("drawer shows Zameen's date at the seeded age, with the caveat", async ({ page }) => {
    await page.locator(".card-wrap").first().click();
    await expect(page.locator("#drawer")).toHaveClass(/drawer-open/, { timeout: 5000 });
    const dates = await page.locator("#drawerDates").textContent();
    expect(dates).toMatch(/First seen by ZameenRentals: \d{1,2} [A-Z][a-z]{2}/);
    expect(dates).toMatch(/Zameen says added (1 hour|\d+ minutes) ago/);
    expect(dates).not.toMatch(/added [5-7] hours ago/);
    expect(dates).toContain("Availability has not been confirmed.");
  });
});
