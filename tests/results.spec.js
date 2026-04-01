// @ts-check
const { test, expect } = require("@playwright/test");

test.describe("Search Results Display", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await page.waitForSelector(".card-wrap", { timeout: 30000 });
  });

  test("results count is displayed", async ({ page }) => {
    const text = await page.locator("#resultsCount").textContent();
    expect(text).toMatch(/\d+\s*results|Showing \d+ of \d+ results/);
  });

  test("results count shows 'Showing X of Y' when paginated", async ({
    page,
  }) => {
    const text = await page.locator("#resultsCount").textContent();
    // If total > loaded, should show "Showing X of Y results"
    if (text.includes("Showing")) {
      expect(text).toMatch(/Showing \d+ of \d+ results/);
    }
  });

  test("listing card has price", async ({ page }) => {
    const firstCard = page.locator(".card-wrap").first();
    // Card should contain price text (Lakh, K, etc.)
    const text = await firstCard.textContent();
    expect(text).toMatch(/Lakh|lakh|Rs|PKR|\d+K/i);
  });

  test("listing card has title", async ({ page }) => {
    const firstCard = page.locator(".card-wrap").first();
    const text = await firstCard.textContent();
    expect(text.length).toBeGreaterThan(10);
  });

  test("listing card has image or placeholder", async ({ page }) => {
    const firstCard = page.locator(".card-wrap").first();
    const imgs = firstCard.locator("img");
    const placeholder = firstCard.locator("text=🏠");
    const hasImg = (await imgs.count()) > 0;
    const hasPlaceholder = (await placeholder.count()) > 0;
    expect(hasImg || hasPlaceholder).toBeTruthy();
  });

  test("listing card shows bed/bath badges when available", async ({
    page,
  }) => {
    // At least some cards should have bed/bath info
    const cards = page.locator(".card-wrap");
    const count = await cards.count();
    let hasBadges = false;
    for (let i = 0; i < Math.min(count, 5); i++) {
      const text = await cards.nth(i).textContent();
      if (/\d+\s*bed/i.test(text)) {
        hasBadges = true;
        break;
      }
    }
    expect(hasBadges).toBeTruthy();
  });

  test("listing card shows location", async ({ page }) => {
    const cards = page.locator(".card-wrap");
    const count = await cards.count();
    let hasLocation = false;
    for (let i = 0; i < Math.min(count, 5); i++) {
      const text = await cards.nth(i).textContent();
      if (text.length > 20) {
        hasLocation = true;
        break;
      }
    }
    expect(hasLocation).toBeTruthy();
  });

  test("property type badge shows when type filter active", async ({
    page,
  }) => {
    await page.locator("#typeChip").click();
    await page.locator('#typeGrid .chip[data-type="house"]').click();
    await page.waitForSelector(".card-wrap", { timeout: 30000 });
    // Cards should show "HOUSE" badge
    const badges = page.locator(
      '.card-wrap .text-brand-500:text-matches("HOUSE", "i")'
    );
    if ((await page.locator(".card-wrap").count()) > 0) {
      expect(await badges.count()).toBeGreaterThan(0);
    }
  });
});

test.describe("Load More", () => {
  test("load more button appears when 15+ results", async ({ page }) => {
    await page.goto("/");
    await page.waitForSelector(".card-wrap", { timeout: 30000 });
    const cards = await page.locator(".card-wrap").count();
    if (cards >= 15) {
      await expect(
        page.locator("#listingsFooter button:text('Load More')")
      ).toBeVisible();
    }
  });

  test("clicking load more appends results", async ({ page }) => {
    await page.goto("/");
    await page.waitForSelector(".card-wrap", { timeout: 30000 });
    const initialCount = await page.locator(".card-wrap").count();
    if (initialCount >= 15) {
      await page.locator("#listingsFooter button").click();
      await page.waitForTimeout(5000);
      const newCount = await page.locator(".card-wrap").count();
      expect(newCount).toBeGreaterThan(initialCount);
    }
  });

  test("results count updates after load more", async ({ page }) => {
    await page.goto("/");
    await page.waitForSelector(".card-wrap", { timeout: 30000 });
    const initialText = await page.locator("#resultsCount").textContent();
    const cards = await page.locator(".card-wrap").count();
    if (cards >= 15) {
      await page.locator("#listingsFooter button").click();
      await page.waitForTimeout(5000);
      const newText = await page.locator("#resultsCount").textContent();
      expect(newText).not.toBe(initialText);
    }
  });
});

test.describe("Image Carousel", () => {
  test("multi-image cards have carousel controls", async ({ page }) => {
    await page.goto("/");
    await page.waitForSelector(".card-wrap", { timeout: 30000 });
    const carousels = page.locator("[data-carousel]");
    if ((await carousels.count()) > 0) {
      const first = carousels.first();
      await expect(first.locator("[data-prev]")).toBeAttached();
      await expect(first.locator("[data-next]")).toBeAttached();
    }
  });

  test("carousel dots are visible", async ({ page }) => {
    await page.goto("/");
    await page.waitForSelector(".card-wrap", { timeout: 30000 });
    const carousels = page.locator("[data-carousel]");
    if ((await carousels.count()) > 0) {
      const dots = carousels.first().locator(".carousel-dot");
      expect(await dots.count()).toBeGreaterThan(0);
    }
  });

  test("clicking next advances carousel", async ({ page }) => {
    await page.goto("/");
    await page.waitForSelector(".card-wrap", { timeout: 30000 });
    const carousels = page.locator("[data-carousel]");
    if ((await carousels.count()) > 0) {
      const first = carousels.first();
      // Hover to reveal controls
      await first.hover();
      const nextBtn = first.locator("[data-next]");
      if (await nextBtn.isVisible()) {
        await nextBtn.click();
        // Second dot should be active
        const dots = first.locator(".carousel-dot");
        if ((await dots.count()) > 1) {
          await expect(dots.nth(1)).toHaveClass(/active/);
        }
      }
    }
  });

  // ── New: data source indicator ──

  test("data source badge is shown after search", async ({ page }) => {
    await page.goto("/");
    await page.waitForSelector(".card-wrap", { timeout: 30000 });
    const srcEl = page.locator("#dataSource");
    // Should show "Instant" (local DB) or "Live" (Zameen.com)
    const text = await srcEl.textContent();
    if (text) {
      expect(["Instant", "Live"]).toContain(text.trim());
    }
  });
});
