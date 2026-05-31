// @ts-check
const { test, expect } = require("@playwright/test");

// Helpers ─────────────────────────────────────────────────────────────────

async function gotoApp(page, { clearStorage = true } = {}) {
  await page.goto("/");
  if (clearStorage) {
    // Wipe personalization state between tests but keep the welcome dismissal.
    await page.evaluate(() => {
      for (const k of Object.keys(localStorage)) {
        if (k.startsWith("zr_") && k !== "zr_welcomed") localStorage.removeItem(k);
      }
    });
    await page.reload();
  }
  // Wait for app shell.
  await page.waitForLoadState("networkidle");
}

test.describe("Personalization UI — header controls", () => {
  test("save-search button and alerts bell are present", async ({ page }) => {
    await gotoApp(page);
    await expect(page.locator("#saveSearchBtn")).toBeVisible();
    await expect(page.locator("#alertsBellBtn")).toBeVisible();
  });

  test("alerts panel opens via bell, four tabs visible", async ({ page }) => {
    await gotoApp(page);
    await page.click("#alertsBellBtn");
    const panel = page.locator("#personalizationPanel");
    const drawer = page.locator("#personalizationPanel .personalization-drawer");
    await expect(panel).not.toHaveClass(/(?:^|\s)hidden(?:\s|$)/);
    await expect(drawer).toBeVisible();
    for (const id of ["alerts", "favorites", "recent", "hidden"]) {
      await expect(drawer.locator(`[data-ptab="${id}"]`)).toBeVisible();
    }
  });

  test("alerts panel closes on Escape", async ({ page }) => {
    await gotoApp(page);
    await page.click("#alertsBellBtn");
    const drawer = page.locator("#personalizationPanel .personalization-drawer");
    await expect(drawer).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.locator("#personalizationPanel")).toHaveClass(/(?:^|\s)hidden(?:\s|$)/);
  });

  test("alerts panel shows empty state when no alerts", async ({ page }) => {
    await gotoApp(page);
    await page.click("#alertsBellBtn");
    await expect(page.locator("#personalizationBody")).toContainText(/Set up your first alert|No alerts yet/);
  });
});

test.describe("Personalization UI — save search modal", () => {
  test("opens with no filters, shows fallback name", async ({ page }) => {
    await gotoApp(page);
    await page.click("#saveSearchBtn");
    await expect(page.locator("#saveSearchModal")).toBeVisible();
    await expect(page.locator("#saveSearchTitle")).toHaveText(/Save this search as an alert/);
    await expect(page.locator("#saveSearchPush")).toBeChecked();
    await expect(page.locator("#saveSearchInapp")).toBeChecked();
    // Close.
    await page.click("#saveSearchClose");
    await expect(page.locator("#saveSearchModal")).toBeHidden();
  });

  test("creates an alert via API, alert appears in panel", async ({ page, request }) => {
    await gotoApp(page);
    const clientId = await page.evaluate(() => localStorage.getItem("zr_client_id"));
    expect(clientId).toBeTruthy();

    // Create via API (skips push permission dialog).
    const create = await request.post("/api/alerts", {
      headers: { "X-Client-Id": clientId, "Content-Type": "application/json" },
      data: { label: "E2E test alert", filters: { city: "lahore", bedrooms: 2 } },
    });
    expect(create.ok()).toBeTruthy();

    await page.click("#alertsBellBtn");
    const body = page.locator("#personalizationBody");
    await expect(body).toContainText("E2E test alert");
    await expect(body).toContainText("Your alerts");
  });

  test("alert can be deleted from the panel", async ({ page, request }) => {
    await gotoApp(page);
    const clientId = await page.evaluate(() => localStorage.getItem("zr_client_id"));
    await request.post("/api/alerts", {
      headers: { "X-Client-Id": clientId, "Content-Type": "application/json" },
      data: { label: "Delete me alert", filters: { city: "lahore" } },
    });
    page.on("dialog", dialog => dialog.accept());
    await page.click("#alertsBellBtn");
    await expect(page.locator("#personalizationBody")).toContainText("Delete me alert");
    await page.locator('#personalizationBody [data-alert-action="delete"]').first().click();
    // Toast confirmation.
    await expect(page.locator("#toastStack")).toContainText("Alert deleted");
    // Empty state should return.
    await expect(page.locator("#personalizationBody")).toContainText(/Set up your first alert|No alerts yet/);
  });
});

test.describe("Personalization API contract", () => {
  test("touch endpoint requires X-Client-Id", async ({ request }) => {
    const res = await request.post("/api/personalization/touch");
    expect(res.status()).toBe(400);
  });

  test("touch endpoint returns vapid_public_key", async ({ request }) => {
    const res = await request.post("/api/personalization/touch", {
      headers: { "X-Client-Id": "playwright-touch-abc12345" },
    });
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    expect(body.vapid_public_key).toBeTruthy();
    expect(typeof body.vapid_public_key).toBe("string");
    expect(body.vapid_public_key.length).toBeGreaterThan(40);
  });

  test("favorite + hidden lifecycle via API", async ({ request }) => {
    const headers = { "X-Client-Id": "playwright-fav-abc54321", "Content-Type": "application/json" };
    // Favorite.
    let res = await request.post("/api/favorites", {
      headers, data: { zameen_id: "FAKE-FAV-1" },
    });
    expect(res.ok()).toBeTruthy();
    res = await request.get("/api/favorites", { headers });
    const favBody = await res.json();
    expect(favBody.favorites.length).toBeGreaterThan(0);
    expect(favBody.favorites[0].zameen_id).toBe("FAKE-FAV-1");

    res = await request.delete("/api/favorites/FAKE-FAV-1", { headers });
    expect(res.ok()).toBeTruthy();

    // Hidden.
    res = await request.post("/api/hidden", {
      headers, data: { zameen_id: "FAKE-HIDE-1" },
    });
    expect(res.ok()).toBeTruthy();
    res = await request.get("/api/hidden", { headers });
    const hiddenBody = await res.json();
    expect(hiddenBody.hidden.length).toBeGreaterThan(0);
  });

  test("alert CRUD + match-cycle via API", async ({ request }) => {
    const headers = { "X-Client-Id": "playwright-alert-abc99999", "Content-Type": "application/json" };
    // Create alert.
    let res = await request.post("/api/alerts", {
      headers, data: { label: "API contract alert", filters: { city: "lahore" } },
    });
    expect(res.ok()).toBeTruthy();
    const alert = await res.json();
    expect(alert.id).toBeGreaterThan(0);
    expect(alert.label).toBe("API contract alert");

    // List.
    res = await request.get("/api/alerts", { headers });
    const list = await res.json();
    expect(list.alerts.find(a => a.id === alert.id)).toBeTruthy();

    // Update.
    res = await request.patch(`/api/alerts/${alert.id}`, {
      headers, data: { paused: true },
    });
    expect(res.ok()).toBeTruthy();
    expect((await res.json()).paused).toBe(true);

    // Delete.
    res = await request.delete(`/api/alerts/${alert.id}`, { headers });
    expect(res.ok()).toBeTruthy();
  });

  test("push subscribe requires endpoint and keys", async ({ request }) => {
    const headers = { "X-Client-Id": "playwright-push-abc88888", "Content-Type": "application/json" };
    const res = await request.post("/api/push/subscribe", {
      headers, data: { endpoint: "https://example/x" },
    });
    expect(res.status()).toBe(400);
  });
});

test.describe("Card actions", () => {
  test("favorite button toggles when a card is present", async ({ page }) => {
    await gotoApp(page);
    const card = page.locator(".card-wrap").first();
    const count = await page.locator(".card-wrap").count();
    test.skip(count === 0, "No listings available in test DB");

    const favBtn = card.locator('[data-action="favorite"]').first();
    await expect(favBtn).toBeVisible();
    const before = await favBtn.getAttribute("aria-pressed");
    await favBtn.click();
    // Toast confirmation.
    await expect(page.locator("#toastStack")).toContainText(/Saved to favorites|Removed from favorites/);
    // After click, aria-pressed should have flipped.
    await expect(favBtn).not.toHaveAttribute("aria-pressed", before || "false");
  });

  test("hide button removes the card from the grid", async ({ page }) => {
    await gotoApp(page);
    const count = await page.locator(".card-wrap").count();
    test.skip(count === 0, "No listings available in test DB");
    const card = page.locator(".card-wrap").first();
    const zid = await card.getAttribute("data-zameen-id");
    test.skip(!zid, "First card has no zameen_id");

    await card.locator('[data-action="hide"]').first().click();
    await expect(page.locator("#toastStack")).toContainText("Hidden");
    await expect(page.locator(`.card-wrap[data-zameen-id="${zid}"]`)).toBeHidden();
    const nextVisibleCard = page.locator(".card-wrap:not(.card-hidden)").first();
    if ((await nextVisibleCard.count()) > 0) {
      await expect(nextVisibleCard).toHaveAttribute("data-idx", "0");
    }
  });
});

test.describe("Personalization edge cases", () => {
  test("recent history does not render a favorite-removal action", async ({ page, request }) => {
    await gotoApp(page);
    const card = page.locator(".card-wrap").first();
    const zid = await card.getAttribute("data-zameen-id");
    test.skip(!zid, "First card has no zameen_id");
    const clientId = await page.evaluate(() => localStorage.getItem("zr_client_id"));
    await request.post("/api/recent-views", {
      headers: { "X-Client-Id": clientId, "Content-Type": "application/json" },
      data: { zameen_id: zid },
    });

    await page.click("#alertsBellBtn");
    await page.locator('[data-ptab="recent"]').click();
    await expect(page.locator("#personalizationBody")).toContainText("Recently viewed");
    await expect(page.locator('#personalizationBody [data-personalization-action="remove-favorite"]')).toHaveCount(0);
  });

  test("drawer compare stays unselected when the tray is full", async ({ page }) => {
    await gotoApp(page);
    const cards = page.locator(".card-wrap");
    test.skip((await cards.count()) < 5, "Need at least five listings");
    for (let i = 0; i < 4; i += 1) {
      await cards.nth(i).locator('[data-action="compare"]').click();
    }

    await cards.nth(4).click();
    const drawerCompare = page.locator('[data-drawer-action="compare"]');
    await expect(drawerCompare).toHaveAttribute("aria-pressed", "false");
    await drawerCompare.click();
    await expect(page.locator("#toastStack")).toContainText("up to 4 listings");
    await expect(drawerCompare).toHaveAttribute("aria-pressed", "false");
    await expect(drawerCompare).toContainText("Compare");
  });
});

test.describe("Service worker push handler", () => {
  test("sw.js exposes push and notificationclick event listeners", async ({ request }) => {
    const res = await request.get("/sw.js");
    expect(res.ok()).toBeTruthy();
    const text = await res.text();
    expect(text).toMatch(/addEventListener\(['"]push['"]/);
    expect(text).toMatch(/addEventListener\(['"]notificationclick['"]/);
  });
});
