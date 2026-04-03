// @ts-check
const { test, expect } = require("@playwright/test");

test.describe("Area Filter", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await page.waitForSelector(".card-wrap", { timeout: 30000 });
  });

  test("clicking area chip opens dropdown", async ({ page }) => {
    await page.locator("#areaChip").click();
    await expect(page.locator("#dd-area")).toHaveClass(/open/);
    await expect(page.locator("#areaInput")).toBeVisible();
  });

  test("area list shows popular areas when empty", async ({ page }) => {
    await page.locator("#areaChip").click();
    await page.locator("#areaInput").focus();
    await page.waitForSelector(".area-opt", { timeout: 5000 });
    const opts = await page.locator(".area-opt").count();
    expect(opts).toBeGreaterThan(0);
  });

  test("typing filters area options", async ({ page }) => {
    await page.locator("#areaChip").click();
    await page.locator("#areaInput").fill("DHA");
    await page.waitForTimeout(400); // debounce
    const opts = page.locator(".area-opt");
    expect(await opts.count()).toBeGreaterThan(0);
    // All results should contain DHA
    const first = await opts.first().textContent();
    expect(first.toLowerCase()).toContain("dha");
  });

  test("selecting area updates chip and triggers search", async ({ page }) => {
    await page.locator("#areaChip").click();
    await page.locator("#areaInput").fill("Clifton");
    await page.waitForTimeout(400);
    await page.locator(".area-opt").first().click();
    await expect(page.locator("#areaChip")).toHaveClass(/has-value/);
    await expect(page.locator("#dd-area")).not.toHaveClass(/open/);
    await expect(page.locator("#listingsTitle")).not.toContainText(
      "Rentals in Karachi"
    );
  });

  test("clear button in area input clears text", async ({ page }) => {
    await page.locator("#areaChip").click();
    await page.locator("#areaInput").fill("DHA");
    await expect(page.locator("#areaClear")).toBeVisible();
    await page.locator("#areaClear").click();
    await expect(page.locator("#areaInput")).toHaveValue("");
  });

  test("arrow keys navigate area options", async ({ page }) => {
    await page.locator("#areaChip").click();
    await page.locator("#areaInput").focus();
    await page.waitForSelector(".area-opt", { timeout: 5000 });
    await page.keyboard.press("ArrowDown");
    const highlighted = page.locator(".area-opt.hl");
    expect(await highlighted.count()).toBe(1);
    await page.keyboard.press("ArrowDown");
    await page.keyboard.press("Enter");
    // Should have selected an area
    await expect(page.locator("#areaChip")).toHaveClass(/has-value/);
  });

  test("clearing area filter via chip X", async ({ page }) => {
    // Select an area first
    await page.locator("#areaChip").click();
    await page.locator("#areaInput").fill("DHA");
    await page.waitForTimeout(400);
    await page.locator(".area-opt").first().click();
    await expect(page.locator("#areaChip")).toHaveClass(/has-value/);
    // Click the X button inside the chip to clear
    await page.locator('#areaChip .chip-clear').click();
    await expect(page.locator("#areaChip")).not.toHaveClass(/has-value/);
  });
});

test.describe("Property Type Filter", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await page.waitForSelector(".card-wrap", { timeout: 30000 });
  });

  test("clicking type chip opens dropdown", async ({ page }) => {
    await page.locator("#typeChip").click();
    await expect(page.locator("#dd-type")).toHaveClass(/open/);
  });

  test("selecting a property type updates chip", async ({ page }) => {
    await page.locator("#typeChip").click();
    await page.locator('#typeGrid .chip[data-type="house"]').click();
    await expect(page.locator("#typeChip")).toHaveClass(/has-value/);
  });

  test("all 7 property types are available", async ({ page }) => {
    await page.locator("#typeChip").click();
    const types = [
      "house",
      "apartment",
      "upper_portion",
      "lower_portion",
      "room",
      "penthouse",
      "farm_house",
    ];
    for (const t of types) {
      await expect(page.locator(`#typeGrid .chip[data-type="${t}"]`)).toBeVisible();
    }
  });

  test("selecting type triggers new search", async ({ page }) => {
    const countBefore = await page.locator("#resultsCount").textContent();
    await page.locator("#typeChip").click();
    await page.locator('#typeGrid .chip[data-type="apartment"]').click();
    await page.waitForTimeout(2000);
    // Results count may change
    await expect(page.locator("#resultsCount")).not.toHaveText("");
  });

  test("type is single-select (mutual exclusion)", async ({ page }) => {
    await page.locator("#typeChip").click();
    await page.locator('#typeGrid .chip[data-type="house"]').click();
    await page.locator("#typeChip").click();
    await expect(
      page.locator('#typeGrid .chip[data-type="house"]')
    ).toHaveClass(/active/);
    await page.locator('#typeGrid .chip[data-type="apartment"]').click();
    await page.locator("#typeChip").click();
    await expect(
      page.locator('#typeGrid .chip[data-type="house"]')
    ).not.toHaveClass(/active/);
    await expect(
      page.locator('#typeGrid .chip[data-type="apartment"]')
    ).toHaveClass(/active/);
  });

  test("deselecting type clears filter", async ({ page }) => {
    await page.locator("#typeChip").click();
    await page.locator('#typeGrid .chip[data-type="house"]').click();
    await expect(page.locator("#typeChip")).toHaveClass(/has-value/);
    // Click same type again to deselect
    await page.locator("#typeChip").click();
    await page.locator('#typeGrid .chip[data-type="house"]').click();
    await expect(page.locator("#typeChip")).not.toHaveClass(/has-value/);
  });
});

test.describe("Bedrooms Filter", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await page.waitForSelector(".card-wrap", { timeout: 30000 });
  });

  test("clicking beds chip opens dropdown", async ({ page }) => {
    await page.locator("#bedsChip").click();
    await expect(page.locator("#dd-beds")).toHaveClass(/open/);
  });

  test("bed options available: Any, 1-5+", async ({ page }) => {
    await page.locator("#bedsChip").click();
    await expect(page.locator('#bedRow .chip[data-beds=""]')).toBeVisible();
    for (const b of ["1", "2", "3", "4", "5"]) {
      await expect(
        page.locator(`#bedRow .chip[data-beds="${b}"]`)
      ).toBeVisible();
    }
  });

  test("Any is active by default", async ({ page }) => {
    await page.locator("#bedsChip").click();
    await expect(page.locator('#bedRow .chip[data-beds=""]')).toHaveClass(
      /active/
    );
  });

  test("selecting bedroom count updates chip", async ({ page }) => {
    await page.locator("#bedsChip").click();
    await page.locator('#bedRow .chip[data-beds="3"]').click();
    await expect(page.locator("#bedsChip")).toHaveClass(/has-value/);
  });
});

test.describe("Price Filter", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await page.waitForSelector(".card-wrap", { timeout: 30000 });
  });

  test("clicking price chip opens dropdown", async ({ page }) => {
    await page.locator("#priceChip").click();
    await expect(page.locator("#dd-price")).toHaveClass(/open/);
  });

  test("preset price ranges available", async ({ page }) => {
    await page.locator("#priceChip").click();
    const chips = page.locator("#priceGrid .chip");
    expect(await chips.count()).toBeGreaterThanOrEqual(6); // 5 presets + Custom
  });

  test("selecting a preset updates chip", async ({ page }) => {
    await page.locator("#priceChip").click();
    await page.locator("#priceGrid .chip").first().click();
    await expect(page.locator("#priceChip")).toHaveClass(/has-value/);
  });

  test("custom price inputs appear when Custom clicked", async ({ page }) => {
    await page.locator("#priceChip").click();
    await expect(page.locator("#customPrice")).toBeHidden();
    await page.locator('.chip[data-custom="1"]').click();
    await expect(page.locator("#customPrice")).toBeVisible();
    await expect(page.locator("#priceMin")).toBeVisible();
    await expect(page.locator("#priceMax")).toBeVisible();
  });

  test("enter in custom price input closes dropdown and searches", async ({
    page,
  }) => {
    await page.locator("#priceChip").click();
    await page.locator('.chip[data-custom="1"]').click();
    await page.locator("#priceMin").fill("50000");
    await page.locator("#priceMax").fill("100000");
    await page.locator("#priceMax").press("Enter");
    await expect(page.locator("#dd-price")).not.toHaveClass(/open/);
  });
});

test.describe("More Filters", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await page.waitForSelector(".card-wrap", { timeout: 30000 });
  });

  test("clicking more chip opens dropdown", async ({ page }) => {
    await page.locator("#moreChip").click();
    await expect(page.locator("#dd-more")).toHaveClass(/open/);
  });

  test("furnished toggle works", async ({ page }) => {
    await page.locator("#moreChip").click();
    const toggle = page.locator("#furnishedToggle");
    await expect(toggle).toBeVisible();
    await toggle.click();
    await expect(toggle).toHaveClass(/toggle-on/);
    // More chip should show count
    await expect(page.locator("#moreChip")).toHaveClass(/has-value/);
  });

  test("sort select has all options", async ({ page }) => {
    await page.locator("#moreChip").click();
    const select = page.locator("#sortSelect");
    await expect(select).toBeVisible();
    const options = select.locator("option");
    expect(await options.count()).toBe(5); // Default, Distance, Price Low, Price High, Newest
  });

  test("sort select updates chip", async ({ page }) => {
    await page.locator("#moreChip").click();
    await page.locator("#sortSelect").selectOption("price_low");
    await expect(page.locator("#moreChip")).toHaveClass(/has-value/);
  });

  test("preset chips apply combined filters", async ({ page }) => {
    await page.locator("#moreChip").click();
    // Click "Family Home" preset (house, 3 bed, 50-150K)
    const presets = page.locator("#presetRow .chip");
    expect(await presets.count()).toBeGreaterThan(0);
    await presets.nth(1).click(); // Family Home
    await expect(page.locator("#typeChip")).toHaveClass(/has-value/);
    await expect(page.locator("#bedsChip")).toHaveClass(/has-value/);
    await expect(page.locator("#priceChip")).toHaveClass(/has-value/);
  });
});

test.describe("Clear All", () => {
  test("clear all button resets all filters", async ({ page }) => {
    await page.goto("/");
    await page.waitForSelector(".card-wrap", { timeout: 30000 });

    // Set multiple filters
    await page.locator("#typeChip").click();
    await page.locator('#typeGrid .chip[data-type="house"]').click();
    await page.locator("#bedsChip").click();
    await page.locator('#bedRow .chip[data-beds="3"]').click();

    await expect(page.locator("#clearAllBtn")).toBeVisible();
    await page.locator("#clearAllBtn").click();

    await expect(page.locator("#typeChip")).not.toHaveClass(/has-value/);
    await expect(page.locator("#bedsChip")).not.toHaveClass(/has-value/);
    await expect(page.locator("#clearAllBtn")).toBeHidden();
  });
});

test.describe("Dropdown Management", () => {
  test("clicking outside closes dropdown", async ({ page }) => {
    await page.goto("/");
    await page.waitForSelector(".card-wrap", { timeout: 30000 });
    await page.locator("#typeChip").click();
    await expect(page.locator("#dd-type")).toHaveClass(/open/);
    // Click on body/listings area
    await page.locator("#listingsGrid").click();
    await expect(page.locator("#dd-type")).not.toHaveClass(/open/);
  });

  test("opening one dropdown closes another", async ({ page }) => {
    await page.goto("/");
    await page.waitForSelector(".card-wrap", { timeout: 30000 });
    await page.locator("#typeChip").click();
    await expect(page.locator("#dd-type")).toHaveClass(/open/);
    await page.locator("#bedsChip").click();
    await expect(page.locator("#dd-type")).not.toHaveClass(/open/);
    await expect(page.locator("#dd-beds")).toHaveClass(/open/);
  });

  test("escape key closes dropdown", async ({ page }) => {
    await page.goto("/");
    await page.waitForSelector(".card-wrap", { timeout: 30000 });
    await page.locator("#typeChip").click();
    await expect(page.locator("#dd-type")).toHaveClass(/open/);
    await page.keyboard.press("Escape");
    await expect(page.locator("#dd-type")).not.toHaveClass(/open/);
  });
});
