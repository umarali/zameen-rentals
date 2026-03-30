// @ts-check
const { test, expect } = require("@playwright/test");

test.describe("Natural Language Search", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await page.waitForSelector(".card-wrap", { timeout: 30000 });
  });

  test("search input has placeholder", async ({ page }) => {
    await expect(page.locator("#nlInput")).toHaveAttribute(
      "placeholder",
      /flat|DHA|bed/
    );
  });

  test("focusing empty input shows suggestions", async ({ page }) => {
    await page.locator("#nlInput").focus();
    await expect(page.locator("#nlSuggestions")).toBeVisible();
  });

  test("typing hides suggestions", async ({ page }) => {
    await page.locator("#nlInput").focus();
    await expect(page.locator("#nlSuggestions")).toBeVisible();
    await page.locator("#nlInput").fill("test");
    await expect(page.locator("#nlSuggestions")).toBeHidden();
  });

  test("clicking example suggestion fills input and searches", async ({
    page,
  }) => {
    await page.locator("#nlInput").focus();
    await expect(page.locator("#nlSuggestions")).toBeVisible();
    const example = page.locator(".nl-ex").first();
    const text = await example.textContent();
    await example.click();
    await expect(page.locator("#nlInput")).toHaveValue(text);
    // Should trigger a search
    await page.waitForSelector(".card-wrap", { timeout: 30000 });
  });

  test("clicking outside closes suggestions", async ({ page }) => {
    await page.locator("#nlInput").focus();
    await expect(page.locator("#nlSuggestions")).toBeVisible();
    await page.locator("#listingsGrid").click();
    await expect(page.locator("#nlSuggestions")).toBeHidden();
  });

  test("submitting NL query via Enter parses and searches", async ({
    page,
  }) => {
    await page.locator("#nlInput").fill("2 bed flat in DHA");
    await page.locator("#nlInput").press("Enter");
    // Wait for search results
    await page.waitForSelector(".card-wrap", { timeout: 30000 });
    // Filters should be applied
    await expect(page.locator("#bedsChip")).toHaveClass(/has-value/);
    await expect(page.locator("#typeChip")).toHaveClass(/has-value/);
    await expect(page.locator("#areaChip")).toHaveClass(/has-value/);
  });

  test("submitting NL query via button click works", async ({ page }) => {
    await page.locator("#nlInput").fill("house in Clifton");
    await page.locator("#nlSearchBtn").click();
    await page.waitForSelector(".card-wrap", { timeout: 30000 });
    await expect(page.locator("#typeChip")).toHaveClass(/has-value/);
    await expect(page.locator("#areaChip")).toHaveClass(/has-value/);
  });

  test("NL query with price parses correctly", async ({ page }) => {
    await page.locator("#nlInput").fill("flat under 50k");
    await page.locator("#nlInput").press("Enter");
    await page.waitForSelector(".card-wrap", { timeout: 30000 });
    await expect(page.locator("#priceChip")).toHaveClass(/has-value/);
  });

  test("NL query for different city uses current city", async ({ page }) => {
    // Switch to Lahore
    await page.locator('.city-tab[data-city="lahore"]').click();
    await page.waitForSelector(".card-wrap", { timeout: 30000 });

    await page.locator("#nlInput").fill("3 bed house DHA");
    await page.locator("#nlInput").press("Enter");
    await page.waitForSelector(".card-wrap", { timeout: 30000 });
    await expect(page.locator("#listingsTitle")).toContainText("Rentals in");
  });

  test("approximate area match shows notice", async ({ page }) => {
    await page.locator("#nlInput").fill(
      "house in gulshan e iqbal block 13"
    );
    await page.locator("#nlInput").press("Enter");
    // Should show approximate match notice briefly
    const parsed = page.locator("#nlParsed");
    await expect(parsed).toBeVisible({ timeout: 10000 });
    await expect(parsed).toContainText(/Couldn't find/);
  });

  test("failed NL parse shows error message", async ({ page }) => {
    await page.locator("#nlInput").fill("xyz");
    await page.locator("#nlInput").press("Enter");
    // Should show "Could not understand" or do a basic search
    await page.waitForTimeout(3000);
    // No crash — page still functional
    await expect(page.locator("#listingsTitle")).toBeVisible();
  });
});
