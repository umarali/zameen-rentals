// @ts-check
// Urdu UI: language switch, RTL layout, persistence and ?lang=ur.
const { test, expect } = require("@playwright/test");

const urduButton = (page) => page.locator('[data-lang-option="ur"]:visible');
const englishButton = (page) => page.locator('[data-lang-option="en"]:visible');

async function waitForCards(page) {
  await expect(page.locator(".card-wrap").first()).toBeVisible();
}

test("switching to Urdu translates the page and turns it RTL without a reload", async ({ page }) => {
  await page.goto("/");
  await waitForCards(page);
  await expect(page.locator("html")).toHaveAttribute("dir", "ltr");
  await expect(page.locator("#nearbyChip")).toHaveText("Near Me");

  // A marker on window disappears if the switch reloads the page.
  await page.evaluate(() => { window.__noReload = true; });
  await urduButton(page).click();

  await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
  await expect(page.locator("html")).toHaveAttribute("lang", "ur");
  expect(await page.evaluate(() => window.__noReload)).toBe(true);

  // Static markup, JS-rendered chips, header counts and listing cards.
  await expect(page.locator("#nearbyChip")).toHaveText("میرے قریب");
  await expect(page.locator("#areaChip")).toContainText("علاقہ");
  await expect(page.locator('.city-tab[data-city="karachi"]')).toHaveText("کراچی");
  await expect(page.locator("#listingsTitle")).toContainText("کرائے کے گھر");
  await expect(page.locator("#resultsCount")).not.toContainText("Showing");
  await expect(page.locator("#nlInput")).toHaveAttribute("placeholder", /مثلاً/);
  await expect(page.locator(".card-wrap").first()).toContainText("/ ماہ");
  await expect(page.locator(".card-wrap").first().locator('[data-action="favorite"]'))
    .toHaveAttribute("aria-label", "پسندیدہ میں محفوظ کریں");
  await expect(page.locator("#reportBtn")).toContainText("رائے دیں");

  // Prices keep Western digits.
  const price = await page.locator(".card-wrap").first().locator("div.font-bold").first().innerText();
  expect(price).toMatch(/[0-9]/);
  expect(price).not.toMatch(/[۰-۹]/);

  // The map stays LTR inside the RTL page.
  await expect(page.locator("#mapContainer")).toHaveAttribute("dir", "ltr");
  await expect(page.locator("#mapContainerMobile")).toHaveAttribute("dir", "ltr");
});

test("the Urdu choice survives a reload and switching back restores English", async ({ page }) => {
  await page.goto("/");
  await waitForCards(page);
  await urduButton(page).click();
  await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
  expect(await page.evaluate(() => localStorage.getItem("rk_lang"))).toBe("ur");

  await page.reload();
  await waitForCards(page);
  await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
  await expect(page.locator("#nearbyChip")).toHaveText("میرے قریب");

  await englishButton(page).click();
  await expect(page.locator("html")).toHaveAttribute("dir", "ltr");
  await expect(page.locator("html")).toHaveAttribute("lang", "en");
  await expect(page.locator("#nearbyChip")).toHaveText("Near Me");
  await expect(page.locator(".card-wrap").first()).toContainText("/mo");
  await expect(page.locator("#listingsTitle")).toContainText("Rentals in");

  // English also sticks, even though the URL carried ?lang=ur earlier.
  await page.reload();
  await waitForCards(page);
  await expect(page.locator("html")).toHaveAttribute("dir", "ltr");
  expect(new URL(page.url()).searchParams.get("lang")).toBeNull();
});

test("?lang=ur opens the page in Urdu", async ({ page }) => {
  await page.goto("/?lang=ur");
  await waitForCards(page);
  await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
  await expect(page.locator("#nearbyChip")).toHaveText("میرے قریب");
  await expect(page.locator("#listingsTitle")).toContainText("کرائے کے گھر");
  expect(await page.evaluate(() => localStorage.getItem("rk_lang"))).toBe("ur");
});

test("filters, chips and the listing drawer read in Urdu", async ({ page }) => {
  await page.goto("/?lang=ur");
  await waitForCards(page);

  await page.locator("#typeChip").click();
  await expect(page.locator('#typeGrid .chip[data-type="apartment"]')).toHaveText("فلیٹ");
  await page.locator('#typeGrid .chip[data-type="apartment"]').click();
  await expect(page.locator("#typeChip")).toContainText("فلیٹ");

  await page.locator("#priceChip").click();
  await page.locator('#priceGrid .chip[data-pmax="60000"]').click();
  await expect(page.locator("#priceChip")).toContainText("30 ہزار تا 60 ہزار");
  await waitForCards(page);

  await page.locator(".card-wrap").first().click();
  await expect(page.locator("#drawer")).toHaveClass(/drawer-open/);
  await expect(page.locator("#drawerContent")).toContainText("کرائے کے لیے");
  await expect(page.locator("#drawerContent")).toContainText("ماہانہ");
});

test("Urdu-script search still applies filters while the UI is in Urdu", async ({ page }) => {
  await page.goto("/?lang=ur");
  await waitForCards(page);
  await page.locator('.city-tab[data-city="lahore"]').click();
  const searched = page.waitForResponse(response => {
    const url = new URL(response.url());
    return url.pathname === "/api/search" && url.searchParams.get("area") === "Gulberg"
      && url.searchParams.get("bedrooms") === "2";
  });
  await page.locator("#nlInput").fill("گلبرگ میں 2 بیڈ فلیٹ 50 ہزار تک");
  await page.locator("#nlInput").press("Enter");
  expect((await searched).ok()).toBeTruthy();
  await expect(page.locator("#nlUnderstood")).toContainText("ہم سمجھے");
  await expect(page.locator("#nlUnderstood")).toContainText("گلبرگ");
  await expect(page.locator("#bedsChip")).toContainText("2 بیڈ");
  await expect(page.locator("#priceChip")).toContainText("50 ہزار تک");
});

test("RTL layout has no horizontal overflow at 375px", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto("/?lang=ur");
  await waitForCards(page);
  await page.waitForTimeout(500);
  const overflow = await page.evaluate(() => ({
    doc: document.documentElement.scrollWidth - document.documentElement.clientWidth,
    body: document.body.scrollWidth - document.body.clientWidth,
    offenders: [...document.querySelectorAll("header, header > *, #filtersShell, main, .card-wrap")]
      .filter(el => {
        const r = el.getBoundingClientRect();
        return r.width > 0 && (r.left < -1 || r.right > window.innerWidth + 1);
      })
      .map(el => el.id || el.className.toString().slice(0, 40)),
  }));
  expect(overflow.doc).toBeLessThanOrEqual(0);
  expect(overflow.body).toBeLessThanOrEqual(0);
  expect(overflow.offenders).toEqual([]);
});
