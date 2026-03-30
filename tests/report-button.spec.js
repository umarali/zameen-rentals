// @ts-check
const { test, expect } = require("@playwright/test");

test.describe("Report Issue Button", () => {
  test("report button hidden before results load", async ({ page }) => {
    await page.goto("/");
    // Before results load, button should be hidden
    await expect(page.locator("#reportBtn")).toBeHidden();
  });

  test("report button visible after results load", async ({ page }) => {
    await page.goto("/");
    await page.waitForSelector(".card-wrap", { timeout: 30000 });
    await expect(page.locator("#reportBtn")).toBeVisible();
  });

  test("report button opens GitHub issue in new tab", async ({ page, context }) => {
    await page.goto("/");
    await page.waitForSelector(".card-wrap", { timeout: 30000 });

    // Listen for new page (new tab)
    const [newPage] = await Promise.all([
      context.waitForEvent("page"),
      page.locator("#reportBtn").click(),
    ]);

    const url = newPage.url();
    expect(url).toContain("github.com");
    expect(url).toContain("issues/new");
    expect(url).toContain("Feedback");
    await newPage.close();
  });
});
