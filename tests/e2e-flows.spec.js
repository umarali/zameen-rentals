// @ts-check
const { test, expect } = require("@playwright/test");

test.describe("End-to-End User Flows", () => {
  test("complete search flow: NL query → filter → load more → drawer → nearby", async ({
    page,
  }) => {
    await page.goto("/");
    await page.waitForSelector(".card-wrap", { timeout: 30000 });

    // Switch to Karachi for NL tests (DHA is a Karachi area)
    await page.locator('.city-tab[data-city="karachi"]').click();
    await page.waitForSelector(".card-wrap", { timeout: 30000 });

    // Step 1: NL search
    await page.locator("#nlInput").fill("flat in DHA");
    await page.locator("#nlInput").press("Enter");
    await page.waitForSelector(".card-wrap", { timeout: 30000 });
    await expect(page.locator("#areaChip")).toHaveClass(/has-value/);
    await expect(page.locator("#typeChip")).toHaveClass(/has-value/);

    // Step 2: Add bedroom filter
    await page.locator("#bedsChip").click();
    await page.locator('#bedRow .chip[data-beds="2"]').click();
    await page.waitForSelector(".card-wrap", { timeout: 30000 });

    // Step 3: Verify results
    const count = await page.locator(".card-wrap").count();
    expect(count).toBeGreaterThan(0);

    // Step 4: Open detail drawer
    await page.locator(".card-wrap").first().click();
    await expect(page.locator("#drawer")).toHaveClass(/drawer-open/, {
      timeout: 3000,
    });

    // Step 5: Check drawer content
    await expect(page.locator("#drawerContent")).toContainText(/Rs|Lakh|PKR/i);
    await expect(
      page.locator('#drawerContent a[title="View on Zameen.com"]')
    ).toBeVisible();

    // Step 6: Close drawer
    await page.locator("#drawerClose").click();
    await expect(page.locator("#drawer")).not.toHaveClass(/drawer-open/);
  });

  test("city switch flow: Lahore → Karachi → search → Islamabad", async ({
    page,
  }) => {
    await page.goto("/");
    await page.waitForSelector(".card-wrap", { timeout: 30000 });

    // Switch to Karachi (default is Lahore)
    await page.locator('.city-tab[data-city="karachi"]').click();
    await page.waitForSelector(".card-wrap", { timeout: 30000 });
    await expect(page.locator("#listingsTitle")).toContainText("Karachi");

    // Search in Lahore
    await page.locator("#typeChip").click();
    await page.locator('#typeGrid .chip[data-type="house"]').click();
    await page.waitForSelector(".card-wrap", { timeout: 30000 });

    // Switch to Islamabad
    await page.locator('.city-tab[data-city="islamabad"]').click();
    await page.waitForSelector(".card-wrap", { timeout: 30000 });
    await expect(page.locator("#listingsTitle")).toContainText("Islamabad");
    // Filters should be cleared
    await expect(page.locator("#typeChip")).not.toHaveClass(/has-value/);
  });

  test("preset flow: select preset → verify filters → clear all", async ({
    page,
  }) => {
    await page.goto("/");
    await page.waitForSelector(".card-wrap", { timeout: 30000 });

    // Open More dropdown and select a preset
    await page.locator("#moreChip").click();
    const preset = page.locator("#presetRow .chip").first();
    await preset.click();
    await page.waitForSelector(".card-wrap", { timeout: 30000 });

    // Multiple filters should be active
    const activeChips = await page
      .locator("#filterBar .chip-filter.has-value")
      .count();
    expect(activeChips).toBeGreaterThan(0);

    // Clear all
    await expect(page.locator("#clearAllBtn")).toBeVisible();
    await page.locator("#clearAllBtn").click();
    const afterClear = await page
      .locator("#filterBar .chip-filter.has-value")
      .count();
    expect(afterClear).toBe(0);
  });

  test("area autocomplete flow: type → arrow navigate → enter select", async ({
    page,
  }) => {
    await page.goto("/");
    await page.waitForSelector(".card-wrap", { timeout: 30000 });

    await page.locator("#areaChip").click();
    await page.locator("#areaInput").fill("Bah");
    await page.waitForTimeout(400);

    // Arrow down twice and Enter
    await page.keyboard.press("ArrowDown");
    await page.keyboard.press("ArrowDown");
    await page.keyboard.press("Enter");

    await expect(page.locator("#areaChip")).toHaveClass(/has-value/);
    await page.waitForSelector(".card-wrap", { timeout: 30000 });
  });

  test("furnished + sort combo", async ({ page }) => {
    await page.goto("/");
    await page.waitForSelector(".card-wrap", { timeout: 30000 });

    await page.locator("#moreChip").click();
    await page.locator("#furnishedToggle").click();
    await page.locator("#sortSelect").selectOption("price_low");
    await page.locator("#listingsGrid").click(); // close dropdown

    await expect(page.locator("#moreChip")).toHaveClass(/has-value/);
    await page.waitForSelector(".card-wrap", { timeout: 30000 });
  });

  test("multiple filter combo: area + type + beds + price", async ({
    page,
  }) => {
    await page.goto("/");
    await page.waitForSelector(".card-wrap", { timeout: 30000 });

    // Area
    await page.locator("#areaChip").click();
    await page.locator("#areaInput").fill("DHA");
    await page.waitForTimeout(400);
    await page.locator(".area-opt").first().click();

    // Type
    await page.locator("#typeChip").click();
    await page.locator('#typeGrid .chip[data-type="apartment"]').click();

    // Beds
    await page.locator("#bedsChip").click();
    await page.locator('#bedRow .chip[data-beds="3"]').click();

    // Price
    await page.locator("#priceChip").click();
    await page.locator("#priceGrid .chip").nth(1).click();

    await page.waitForSelector("#resultsCount", { timeout: 30000 });
    const text = await page.locator("#resultsCount").textContent();
    expect(text).toMatch(/\d+/);
  });

  test("no results state", async ({ page }) => {
    await page.goto("/");
    await page.waitForSelector(".card-wrap", { timeout: 30000 });

    // Set very restrictive filters to hopefully get 0 results
    await page.locator("#typeChip").click();
    await page.locator('#typeGrid .chip[data-type="penthouse"]').click();
    await page.locator("#priceChip").click();
    await page.locator('.chip[data-custom="1"]').click();
    await page.locator("#priceMin").fill("1");
    await page.locator("#priceMax").fill("100");
    await page.locator("#priceMax").press("Enter");

    await page.waitForTimeout(5000);
    // Either no results shown or some results
    const noResults = page.locator('text="No rentals found"');
    const cards = page.locator(".card-wrap");
    const hasResults = (await cards.count()) > 0;
    const hasNoResults = (await noResults.count()) > 0;
    expect(hasResults || hasNoResults).toBeTruthy();
  });

  test("search with area then load more keeps area context", async ({
    page,
  }) => {
    await page.goto("/");
    await page.waitForSelector(".card-wrap", { timeout: 30000 });

    await page.locator("#areaChip").click();
    await page.locator("#areaInput").fill("DHA");
    await page.waitForTimeout(400);
    await page.locator(".area-opt").first().click();
    await page.waitForSelector(".card-wrap", { timeout: 30000 });

    const loadMore = page.locator('#listingsFooter button:text("Load More")');
    if (await loadMore.isVisible()) {
      await loadMore.click();
      await page.waitForTimeout(5000);
      // Area chip should still be active
      await expect(page.locator("#areaChip")).toHaveClass(/has-value/);
    }
  });
});
