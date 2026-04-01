// @ts-check
const { test, expect } = require("@playwright/test");

test.describe("City Tabs", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await page.waitForSelector(".card-wrap", { timeout: 30000 });
  });

  test("clicking Lahore tab switches city", async ({ page }) => {
    await page.locator('.city-tab[data-city="lahore"]').click();
    await expect(
      page.locator('.city-tab[data-city="lahore"]')
    ).toHaveClass(/active/);
    await expect(
      page.locator('.city-tab[data-city="karachi"]')
    ).not.toHaveClass(/active/);
    await expect(page.locator("#listingsTitle")).toContainText(
      "Rentals in Lahore",
      { timeout: 30000 }
    );
  });

  test("clicking Islamabad tab switches city", async ({ page }) => {
    await page.locator('.city-tab[data-city="islamabad"]').click();
    await expect(
      page.locator('.city-tab[data-city="islamabad"]')
    ).toHaveClass(/active/);
    await expect(page.locator("#listingsTitle")).toContainText(
      "Rentals in Islamabad",
      { timeout: 30000 }
    );
  });

  test("switching city clears filters", async ({ page }) => {
    // Set an area filter first
    await page.locator("#areaChip").click();
    await page.locator("#areaInput").fill("DHA");
    await page.waitForSelector(".area-opt", { timeout: 5000 });
    await page.locator(".area-opt").first().click();
    await expect(page.locator("#areaChip")).toHaveClass(/has-value/);

    // Switch to a different city (default is Lahore, switch to Karachi)
    await page.locator('.city-tab[data-city="karachi"]').click();
    // Area chip should be cleared
    await expect(page.locator("#areaChip")).not.toHaveClass(/has-value/);
  });

  test("switching city loads new results", async ({ page }) => {
    await page.locator('.city-tab[data-city="lahore"]').click();
    await page.waitForSelector(".card-wrap", { timeout: 30000 });
    const count = await page.locator(".card-wrap").count();
    expect(count).toBeGreaterThan(0);
  });

  test("city persists in localStorage", async ({ page }) => {
    await page.locator('.city-tab[data-city="islamabad"]').click();
    await page.waitForSelector(".card-wrap", { timeout: 30000 });
    const saved = await page.evaluate(() => {
      const d = JSON.parse(localStorage.getItem("rk_s") || "{}");
      return d.city;
    });
    expect(saved).toBe("islamabad");
  });

  test("switching back to Karachi works", async ({ page }) => {
    await page.locator('.city-tab[data-city="lahore"]').click();
    await page.waitForSelector(".card-wrap", { timeout: 30000 });
    await page.locator('.city-tab[data-city="karachi"]').click();
    await expect(
      page.locator('.city-tab[data-city="karachi"]')
    ).toHaveClass(/active/);
    await expect(page.locator("#listingsTitle")).toContainText(
      "Rentals in Karachi",
      { timeout: 30000 }
    );
  });
});
