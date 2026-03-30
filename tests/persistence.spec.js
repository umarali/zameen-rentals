// @ts-check
const { test, expect } = require("@playwright/test");

test.describe("LocalStorage Persistence", () => {
  test("filters persist across page reload", async ({ page }) => {
    await page.goto("/");
    await page.waitForSelector(".card-wrap", { timeout: 30000 });

    // Set filters
    await page.locator("#typeChip").click();
    await page.locator('.chip[data-type="apartment"]').click();
    await page.locator("#bedsChip").click();
    await page.locator('#bedRow .chip[data-beds="2"]').click();
    await page.waitForTimeout(1000);

    // Verify saved in localStorage
    const saved = await page.evaluate(() =>
      JSON.parse(localStorage.getItem("rk_s") || "{}")
    );
    expect(saved.type).toBe("apartment");
    expect(saved.beds).toBe("2");

    // Reload
    await page.reload();
    await page.waitForSelector(".card-wrap", { timeout: 30000 });

    // Filters should be restored
    await expect(page.locator("#typeChip")).toHaveClass(/has-value/);
    await expect(page.locator("#bedsChip")).toHaveClass(/has-value/);
  });

  test("city persists across reload", async ({ page }) => {
    await page.goto("/");
    await page.waitForSelector(".card-wrap", { timeout: 30000 });

    await page.locator('.city-tab[data-city="islamabad"]').click();
    await page.waitForSelector(".card-wrap", { timeout: 30000 });

    await page.reload();
    await page.waitForSelector(".card-wrap", { timeout: 30000 });

    await expect(
      page.locator('.city-tab[data-city="islamabad"]')
    ).toHaveClass(/active/);
  });

  test("area persists across reload", async ({ page }) => {
    await page.goto("/");
    await page.waitForSelector(".card-wrap", { timeout: 30000 });

    await page.locator("#areaChip").click();
    await page.locator("#areaInput").fill("DHA");
    await page.waitForTimeout(400);
    await page.locator(".area-opt").first().click();
    await page.waitForTimeout(1000);

    await page.reload();
    await page.waitForSelector(".card-wrap", { timeout: 30000 });

    await expect(page.locator("#areaChip")).toHaveClass(/has-value/);
  });
});
