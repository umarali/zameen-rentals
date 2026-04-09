// @ts-check
const { test, expect } = require("@playwright/test");

test.describe("Feedback Modal", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await page.waitForSelector(".card-wrap", { timeout: 30000 });
  });

  test("report button opens feedback modal", async ({ page }) => {
    await page.locator("#reportBtn").click();
    await expect(page.locator("#feedbackModal")).not.toHaveClass(/hidden/);
    await expect(page.locator("#feedbackOverlay")).not.toHaveClass(/hidden/);
    await expect(page.locator("#feedbackMsg")).toBeVisible();
  });

  test("submit button is disabled when textarea is empty", async ({ page }) => {
    await page.locator("#reportBtn").click();
    await expect(page.locator("#feedbackSubmit")).toBeDisabled();
  });

  test("typing enables submit button", async ({ page }) => {
    await page.locator("#reportBtn").click();
    await page.locator("#feedbackMsg").fill("Great app!");
    await expect(page.locator("#feedbackSubmit")).not.toBeDisabled();
  });

  test("clearing text re-disables submit button", async ({ page }) => {
    await page.locator("#reportBtn").click();
    await page.locator("#feedbackMsg").fill("test");
    await expect(page.locator("#feedbackSubmit")).not.toBeDisabled();
    await page.locator("#feedbackMsg").fill("");
    await expect(page.locator("#feedbackSubmit")).toBeDisabled();
  });

  test("close button closes modal", async ({ page }) => {
    await page.locator("#reportBtn").click();
    await expect(page.locator("#feedbackModal")).not.toHaveClass(/hidden/);
    await page.locator("#feedbackClose").click();
    await expect(page.locator("#feedbackModal")).toHaveClass(/hidden/);
    await expect(page.locator("#feedbackOverlay")).toHaveClass(/hidden/);
  });

  test("cancel button closes modal", async ({ page }) => {
    await page.locator("#reportBtn").click();
    await expect(page.locator("#feedbackModal")).not.toHaveClass(/hidden/);
    await page.locator("#feedbackCancel").click();
    await expect(page.locator("#feedbackModal")).toHaveClass(/hidden/);
  });

  test("clicking overlay closes modal", async ({ page }) => {
    await page.locator("#reportBtn").click();
    await expect(page.locator("#feedbackModal")).not.toHaveClass(/hidden/);
    // Overlay is behind modal (z-250 vs z-251), click an exposed edge
    await page.locator("#feedbackOverlay").evaluate((el) => el.click());
    await expect(page.locator("#feedbackModal")).toHaveClass(/hidden/);
  });

  test("successful submission shows toast and closes modal", async ({
    page,
  }) => {
    await page.route("**/api/feedback", (route) =>
      route.fulfill({ status: 200, json: { ok: true } })
    );

    await page.locator("#reportBtn").click();
    await page.locator("#feedbackMsg").fill("Love the new filters!");
    await page.locator("#feedbackSubmit").click();

    // Modal should close
    await expect(page.locator("#feedbackModal")).toHaveClass(/hidden/);
    // Toast should appear
    await expect(page.locator("#toastStack")).toContainText(
      "Thanks for your feedback!"
    );
  });

  test("failed submission shows error toast and keeps modal open", async ({
    page,
  }) => {
    await page.route("**/api/feedback", (route) =>
      route.fulfill({ status: 500, body: "Server Error" })
    );

    await page.locator("#reportBtn").click();
    await page.locator("#feedbackMsg").fill("Test error handling");
    await page.locator("#feedbackSubmit").click();

    // Modal should stay open
    await expect(page.locator("#feedbackModal")).not.toHaveClass(/hidden/);
    // Error toast
    await expect(page.locator("#toastStack")).toContainText(
      "Could not send feedback"
    );
    // Submit button re-enabled
    await expect(page.locator("#feedbackSubmit")).not.toBeDisabled();
  });
});
