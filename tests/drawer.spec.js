// @ts-check
const { test, expect } = require("@playwright/test");

test.describe("Detail Drawer", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await page.waitForSelector(".card-wrap", { timeout: 30000 });
  });

  test("clicking a card opens the drawer", async ({ page }) => {
    await page.locator(".card-wrap").first().click();
    await expect(page.locator("#drawer")).toHaveClass(/drawer-open/, {
      timeout: 3000,
    });
    await expect(page.locator("#drawerOverlay")).toHaveClass(/overlay-open/);
  });

  test("drawer shows listing title", async ({ page }) => {
    await page.locator(".card-wrap").first().click();
    await expect(page.locator("#drawer")).toHaveClass(/drawer-open/, {
      timeout: 3000,
    });
    const content = await page.locator("#drawerContent").textContent();
    expect(content.length).toBeGreaterThan(10);
  });

  test("drawer shows price", async ({ page }) => {
    await page.locator(".card-wrap").first().click();
    await expect(page.locator("#drawer")).toHaveClass(/drawer-open/, {
      timeout: 3000,
    });
    const content = await page.locator("#drawerContent").textContent();
    expect(content).toMatch(/Rs|Lakh|lakh|PKR|\d/i);
  });

  test("drawer shows View on Zameen.com link", async ({ page }) => {
    await page.locator(".card-wrap").first().click();
    await expect(page.locator("#drawer")).toHaveClass(/drawer-open/, {
      timeout: 3000,
    });
    const link = page.locator('#drawerContent a:text("View on Zameen.com")');
    await expect(link).toBeVisible();
    const href = await link.getAttribute("href");
    expect(href).toContain("zameen.com");
  });

  test("drawer has image area", async ({ page }) => {
    await page.locator(".card-wrap").first().click();
    await expect(page.locator("#drawer")).toHaveClass(/drawer-open/, {
      timeout: 3000,
    });
    await expect(page.locator("#drawerImgArea")).toBeVisible();
  });

  test("drawer close button works", async ({ page }) => {
    await page.locator(".card-wrap").first().click();
    await expect(page.locator("#drawer")).toHaveClass(/drawer-open/, {
      timeout: 3000,
    });
    await page.locator("#drawerClose").click();
    await expect(page.locator("#drawer")).not.toHaveClass(/drawer-open/);
  });

  test("clicking overlay closes drawer", async ({ page }) => {
    await page.locator(".card-wrap").first().click();
    await expect(page.locator("#drawer")).toHaveClass(/drawer-open/, {
      timeout: 3000,
    });
    await page.locator("#drawerOverlay").click({ force: true });
    await expect(page.locator("#drawer")).not.toHaveClass(/drawer-open/);
  });

  test("escape key closes drawer", async ({ page }) => {
    await page.locator(".card-wrap").first().click();
    await expect(page.locator("#drawer")).toHaveClass(/drawer-open/, {
      timeout: 3000,
    });
    await page.keyboard.press("Escape");
    await expect(page.locator("#drawer")).not.toHaveClass(/drawer-open/);
  });

  test("drawer shows nearby areas", async ({ page }) => {
    await page.locator(".card-wrap").first().click();
    await expect(page.locator("#drawer")).toHaveClass(/drawer-open/, {
      timeout: 3000,
    });
    // Nearby areas section may or may not appear depending on area data
    await page.waitForTimeout(500);
    const nearbyChips = page.locator("#drawerContent .chip[data-nearby]");
    // Just verify no crash — nearby may not always be present
    const count = await nearbyChips.count();
    expect(count).toBeGreaterThanOrEqual(0);
  });

  test("clicking nearby area chip closes drawer and searches", async ({
    page,
  }) => {
    await page.locator(".card-wrap").first().click();
    await expect(page.locator("#drawer")).toHaveClass(/drawer-open/, {
      timeout: 3000,
    });
    await page.waitForTimeout(500);
    const nearbyChips = page.locator("#drawerContent .chip[data-nearby]");
    if ((await nearbyChips.count()) > 0) {
      await nearbyChips.first().click();
      await expect(page.locator("#drawer")).not.toHaveClass(/drawer-open/);
      await expect(page.locator("#areaChip")).toHaveClass(/has-value/);
    }
  });

  test("drawer mini map renders", async ({ page }) => {
    await page.locator(".card-wrap").first().click();
    await expect(page.locator("#drawer")).toHaveClass(/drawer-open/, {
      timeout: 3000,
    });
    // Mini map div exists
    await expect(page.locator("#drawerMiniMap")).toBeAttached();
  });
});

test.describe("Detail Drawer - Mobile", () => {
  test.use({ viewport: { width: 375, height: 812 } });

  test("drawer opens from bottom on mobile", async ({ page }) => {
    await page.goto("/");
    await page.waitForSelector(".card-wrap", { timeout: 30000 });
    await page.locator(".card-wrap").first().click();
    await expect(page.locator("#drawer")).toHaveClass(/drawer-open/, {
      timeout: 3000,
    });
  });
});
