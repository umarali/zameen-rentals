// @ts-check
const { test, expect } = require("@playwright/test");

test.describe("Page Load & Layout", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await page.evaluate(() => localStorage.removeItem("rk_s"));
    await page.reload();
  });

  test("page title is correct", async ({ page }) => {
    await expect(page).toHaveTitle(/ZameenRentals/);
  });

  test("navbar renders with logo and search bar", async ({ page }) => {
    await expect(page.locator("header")).toBeVisible();
    await expect(page.locator("text=ZameenRentals")).toBeVisible();
    await expect(page.locator("#nlInput")).toBeVisible();
    await expect(page.locator("#nlSearchBtn")).toBeVisible();
  });

  test("city tabs render with Lahore active by default", async ({ page }) => {
    await expect(page.locator("#cityTabs")).toBeVisible();
    const lahoreTab = page.locator('.city-tab[data-city="lahore"]');
    await expect(lahoreTab).toHaveClass(/active/);
    await expect(
      page.locator('.city-tab[data-city="karachi"]')
    ).not.toHaveClass(/active/);
    await expect(
      page.locator('.city-tab[data-city="islamabad"]')
    ).not.toHaveClass(/active/);
  });

  test("filter chips render", async ({ page }) => {
    await expect(page.locator("#areaChip")).toBeVisible();
    await expect(page.locator("#typeChip")).toBeVisible();
    await expect(page.locator("#bedsChip")).toBeVisible();
    await expect(page.locator("#priceChip")).toBeVisible();
    await expect(page.locator("#moreChip")).toBeVisible();
  });

  test("listings panel renders with title and results count", async ({
    page,
  }) => {
    await expect(page.locator("#listingsTitle")).toBeVisible();
    await expect(page.locator("#listingsTitle")).toContainText(
      "Rentals in Lahore"
    );
    // Wait for search to complete
    await expect(page.locator("#resultsCount")).not.toHaveText("", {
      timeout: 30000,
    });
  });

  test("listings grid loads cards", async ({ page }) => {
    await page.waitForSelector(".card-wrap", { timeout: 30000 });
    const cards = page.locator(".card-wrap");
    expect(await cards.count()).toBeGreaterThan(0);
  });

  test("desktop map panel is visible on wide viewport", async ({ page }) => {
    await expect(page.locator("#mapPanel")).toBeVisible();
    await expect(page.locator("#mapContainer")).toBeVisible();
  });

  test("map FAB is hidden on desktop", async ({ page }) => {
    await expect(page.locator("#mapFab")).toBeHidden();
  });

  test("clear all button is hidden when no filters", async ({ page }) => {
    await expect(page.locator("#clearAllBtn")).toBeHidden();
  });

  test("report button appears after results load", async ({ page }) => {
    await page.waitForSelector(".card-wrap", { timeout: 30000 });
    await expect(page.locator("#reportBtn")).toBeVisible();
  });

  test("NL suggestions hidden by default", async ({ page }) => {
    await expect(page.locator("#nlSuggestions")).toBeHidden();
  });

  test("drawer is hidden by default", async ({ page }) => {
    const drawer = page.locator("#drawer");
    await expect(drawer).not.toHaveClass(/drawer-open/);
  });

  test("footer shows Zameen.com attribution", async ({ page }) => {
    await expect(page.locator("text=Powered by Zameen.com data")).toBeVisible();
  });
});

test.describe("Mobile Layout", () => {
  test.use({ viewport: { width: 375, height: 812 } });

  test("map panel is hidden on mobile", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator("#mapPanel")).toBeHidden();
  });

  test("map FAB is visible on mobile", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator("#mapFab")).toBeVisible();
  });
});
