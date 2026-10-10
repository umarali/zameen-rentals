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
    await expect(tip).toContainText("This date comes from Zameen");
    await expect(tip).toContainText(/ZameenRentals first saw it on \d{1,2} [A-Z][a-z]{2}/);
    await expect(tip).toContainText("Availability isn’t confirmed");
    await expect(page.locator("#drawer")).not.toHaveClass(/drawer-open/);
    await page.keyboard.press("Escape");
    await page.mouse.move(0, 0); // desktop also shows it on hover
    await expect(tip).toBeHidden();
  });

  test("drawer shows the same date line", async ({ page }) => {
    await page.locator(".card-wrap").first().locator("h3, .line-clamp-1").first().click();
    await expect(page.locator("#drawer")).toHaveClass(/drawer-open/, { timeout: 5000 });
    await expect(page.locator("#drawerDates")).toContainText(/(Added|Updated) (1 hour|\d+ minutes) ago/);
  });
});
