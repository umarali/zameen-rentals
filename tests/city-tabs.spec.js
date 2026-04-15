// @ts-check
const { test, expect } = require("@playwright/test");

async function clickCityAndWait(page, city) {
  const activeCity = await page.locator(".city-tab.active").getAttribute("data-city");
  if (activeCity !== city) {
    const citySearch = page.waitForResponse((response) => {
      if (!response.ok()) return false;
      const url = new URL(response.url());
      return ["/api/search", "/api/map-search"].includes(url.pathname) &&
        url.searchParams.get("city") === city;
    });
    await page.locator(`.city-tab[data-city="${city}"]`).click();
    await citySearch;
  }

  await expect(page.locator(`.city-tab[data-city="${city}"]`)).toHaveClass(/active/);
  await expect(page.locator("#resultsCount")).not.toHaveText("", { timeout: 30000 });
  await expect(page.locator(".card-wrap").first()).toBeVisible();
  await expect.poll(async () => page.evaluate(() => JSON.parse(localStorage.getItem("rk_s") || "{}").city)).toBe(city);
  await expect(page.locator("#listingsTitle")).toContainText(
    city.charAt(0).toUpperCase() + city.slice(1)
  );
}

test.describe("City Tabs", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await page.waitForSelector(".card-wrap", { timeout: 30000 });
  });

  test("clicking Lahore tab switches city", async ({ page }) => {
    await clickCityAndWait(page, "karachi");
    await clickCityAndWait(page, "lahore");
    await expect(
      page.locator('.city-tab[data-city="karachi"]')
    ).not.toHaveClass(/active/);
  });

  test("clicking Islamabad tab switches city", async ({ page }) => {
    await clickCityAndWait(page, "karachi");
    await clickCityAndWait(page, "islamabad");
  });

  test("switching city clears filters", async ({ page }) => {
    // Determine the current active city and pick a different one to switch to
    const activeTab = page.locator('.city-tab.active');
    const currentCity = await activeTab.getAttribute('data-city');
    const targetCity = currentCity === 'karachi' ? 'lahore' : 'karachi';

    // Set an area filter first
    await page.locator("#areaChip").click();
    await page.locator("#areaInput").fill("DHA");
    await page.waitForSelector(".area-opt", { timeout: 5000 });
    await page.locator(".area-opt").first().click();
    await expect(page.locator("#areaChip")).toHaveClass(/has-value/);

    // Switch to a different city
    await clickCityAndWait(page, targetCity);
    // Area chip should be cleared
    await expect(page.locator("#areaChip")).not.toHaveClass(/has-value/);
  });

  test("switching city loads new results", async ({ page }) => {
    await clickCityAndWait(page, "karachi");
    await clickCityAndWait(page, "lahore");
    const count = await page.locator(".card-wrap").count();
    expect(count).toBeGreaterThan(0);
  });

  test("city persists in localStorage", async ({ page }) => {
    await clickCityAndWait(page, "karachi");
    await clickCityAndWait(page, "islamabad");
    const saved = await page.evaluate(() => {
      const d = JSON.parse(localStorage.getItem("rk_s") || "{}");
      return d.city;
    });
    expect(saved).toBe("islamabad");
  });

  test("switching back to Karachi works", async ({ page }) => {
    await clickCityAndWait(page, "lahore");
    await clickCityAndWait(page, "karachi");
    await expect(page.locator('.city-tab[data-city="lahore"]')).not.toHaveClass(/active/);
  });
});
