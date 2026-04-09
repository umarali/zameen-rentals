// @ts-check
const { test, expect } = require("@playwright/test");

test.describe("Report Issue Button", () => {
  test("report button is always visible", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator("#reportBtn")).toBeVisible();
  });

  test("report button opens feedback modal", async ({ page }) => {
    await page.goto("/");
    await page.waitForSelector(".card-wrap", { timeout: 30000 });

    await page.locator("#reportBtn").click();
    await expect(page.locator("#feedbackModal")).not.toHaveClass(/hidden/);
    await expect(page.locator("#feedbackOverlay")).not.toHaveClass(/hidden/);
    await expect(page.locator("#feedbackMsg")).toBeVisible();
    await expect(page.locator("#feedbackMsg")).toBeFocused();
  });
});
