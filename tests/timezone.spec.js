// @ts-check
const { test, expect } = require("@playwright/test");

// The backend stores UTC without an offset. A browser in Pakistan (UTC+5) used
// to read those times as local, so a listing seeded "Added: 1 hour ago"
// showed "Added 6 hours ago".
test.describe("Server times in a Pakistan browser", () => {
  test.use({ timezoneId: "Asia/Karachi" });

  test("card age matches the seeded age", async ({ page }) => {
    await page.goto("/");
    await page.waitForSelector(".card-wrap", { timeout: 30000 });
    const text = await page.locator(".card-wrap").first().textContent();
    expect(text).toMatch(/Added (1 hour|\d+ minutes) ago/);
    expect(text).not.toMatch(/Added [5-7] hours ago/);
  });
});
