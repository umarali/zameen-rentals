// @ts-check
// Credits: buy a pack through the local test provider, see the balance,
// restore on a second browser, and open the top-up sheet from a 402 event.
// The Playwright server runs PAYMENTS_PROVIDER=test with ZR_ENV=test.
const { test, expect } = require("@playwright/test");

const SHEET = "#creditsSheet";
const DIALOG = "#creditsDialog";

async function gotoApp(page) {
  await page.goto("/");
  await page.waitForLoadState("networkidle");
}

async function openMyRentals(page) {
  await page.click("#alertsBellBtn");
  await expect(page.locator("#personalizationPanel .personalization-drawer")).toBeVisible();
}

async function balanceText(page) {
  return page.locator("#creditsBalance");
}

async function buyStandardPack(page) {
  await gotoApp(page);
  await openMyRentals(page);
  await expect(await balanceText(page)).toHaveText("10 credits");

  await page.click("#creditsTopUpBtn");
  const dialog = page.locator(DIALOG);
  await expect(dialog).toBeVisible();
  await expect(dialog).toHaveAttribute("role", "dialog");
  await expect(dialog).toHaveAttribute("aria-modal", "true");
  await expect(dialog).toContainText("Pay once. Nothing renews.");
  // Packs come from the API: three radios, standard picked by default.
  await expect(dialog.locator('input[name="creditsPack"]')).toHaveCount(3);
  await expect(dialog.locator('input[name="creditsPack"][value="standard"]')).toBeChecked();
  await expect(dialog.locator('input[name="creditsPack"][value="standard"]')).toBeFocused();

  await page.click("#creditsCheckoutBtn");
  await page.waitForURL(/\/pay\/test\/pay_/);
  await expect(page.getByText("Test mode: no real money")).toBeVisible();
  await expect(page.getByText("PKR 499")).toBeVisible();
  await page.getByRole("button", { name: "Pay" }).click();

  // Back in the app with the verified result.
  await page.waitForURL((url) => url.pathname === "/" && !url.search.includes("payment="));
  await expect(page.locator("#creditsSheetTitle")).toHaveText("Payment received");
  await expect(page.locator("#creditsPaidText")).toContainText("60 credits added");
  await expect(page.locator("#creditsPaidText")).toContainText("70 credits");
  const code = (await page.locator("#creditsRestoreCode").textContent())?.trim() || "";
  expect(code).toMatch(/^[0-9A-Z]{4}-[0-9A-Z]{4}-[0-9A-Z]{4}-[0-9A-Z]{4}$/);
  await page.click("#creditsDone");
  await expect(page.locator(SHEET)).toBeHidden();
  return code;
}

test.describe("Credits", () => {
  test("buy a pack with the test provider and see the balance update", async ({ page }) => {
    await buyStandardPack(page);
    await openMyRentals(page);
    await expect(await balanceText(page)).toHaveText("70 credits");
  });

  test("cancelling checkout adds nothing", async ({ page }) => {
    await gotoApp(page);
    await page.evaluate(() => window.dispatchEvent(new CustomEvent("zr:open-topup")));
    await page.click("#creditsCheckoutBtn");
    await page.waitForURL(/\/pay\/test\/pay_/);
    await page.getByRole("button", { name: "Cancel" }).click();
    await expect(page.locator("#creditsSheetTitle")).toHaveText("Checkout cancelled");
    await page.click("#creditsResultClose");
    await openMyRentals(page);
    await expect(await balanceText(page)).toHaveText("10 credits");
  });

  test("restore code moves bought credits to a second browser", async ({ page, browser, baseURL }) => {
    const code = await buyStandardPack(page);

    const second = await browser.newContext({
      baseURL,
      viewport: page.viewportSize() || undefined,
      serviceWorkers: "block",
      storageState: {
        cookies: [],
        origins: [{ origin: new URL(baseURL || "").origin, localStorage: [
          { name: "zr_welcomed", value: "1" }, { name: "zr_tour_done", value: "1" },
        ] }],
      },
    });
    try {
      const other = await second.newPage();
      await gotoApp(other);
      await openMyRentals(other);
      await expect(await balanceText(other)).toHaveText("10 credits");
      await other.click("#creditsRestoreBtn");
      await expect(other.locator("#creditsRestoreInput")).toBeFocused();
      await other.fill("#creditsRestoreInput", "WRONG-CODE-0000-0000");
      await other.click("#creditsRestoreSubmit");
      await expect(other.locator("#creditsRestoreMsg")).toContainText("didn't match");
      await other.fill("#creditsRestoreInput", code.toLowerCase());
      await other.keyboard.press("Enter");
      await expect(other.locator("#creditsSheetTitle")).toHaveText("Credits restored");
      await expect(other.locator(DIALOG)).toContainText("60 credits moved to this device");
      await other.click("#creditsDone");
      await expect(await balanceText(other)).toHaveText("70 credits");
    } finally {
      await second.close();
    }

    // The first browser keeps only its starter credits.
    await gotoApp(page);
    await openMyRentals(page);
    await expect(await balanceText(page)).toHaveText("10 credits");
  });

  test("insufficient-credits event opens the sheet with cost and balance", async ({ page }) => {
    await gotoApp(page);
    const trigger = page.locator("#saveSearchBtn");
    await trigger.focus();
    await page.evaluate(() => window.dispatchEvent(new CustomEvent("zr:insufficient-credits", {
      detail: { code: "insufficient_credits", action: "tailored_list", balance: 2, cost: 25 },
    })));
    const dialog = page.locator(DIALOG);
    await expect(dialog).toBeVisible();
    await expect(page.locator("#creditsNeedNote")).toHaveText(/This needs 25 credits\. You have 10 credits\./);
    // Keyboard: Tab stays inside the dialog, Escape closes it and returns focus.
    for (let i = 0; i < 8; i++) await page.keyboard.press("Tab");
    expect(await page.evaluate(() => document.getElementById("creditsDialog")?.contains(document.activeElement))).toBe(true);
    await page.keyboard.press("Escape");
    await expect(page.locator(SHEET)).toBeHidden();
    await expect(trigger).toBeFocused();
  });

  test("sheet fits a 375px screen", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 740 });
    await gotoApp(page);
    await page.evaluate(() => window.dispatchEvent(new CustomEvent("zr:open-topup")));
    const box = await page.locator(DIALOG).boundingBox();
    expect(box).not.toBeNull();
    expect(box.x).toBeGreaterThanOrEqual(0);
    expect(box.x + box.width).toBeLessThanOrEqual(375);
    await expect(page.locator("#creditsCheckoutBtn")).toBeInViewport();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
    expect(overflow).toBe(false);
  });
});
