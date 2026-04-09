// @ts-check
const { test, expect } = require("@playwright/test");

const STUB_PAYLOAD = {
  total: 1,
  page: 1,
  per_page: 25,
  source: "local",
  mode: "viewport",
  visible_areas: 1,
  area_totals: { Clifton: 1 },
  ranking: "map_focus",
  results: [
    {
      title: "Gallery Test Listing",
      url: "https://www.zameen.com/Property/test-gallery-1.html",
      price: 85000,
      bedrooms: 3,
      bathrooms: 2,
      area_size: "1200 sqft",
      location: "Clifton, Karachi",
      property_type: "House",
      images: [
        "https://dummyimage.com/600x400/ccc/333.jpg&text=1",
        "https://dummyimage.com/600x400/aaa/333.jpg&text=2",
        "https://dummyimage.com/600x400/888/333.jpg&text=3",
      ],
      latitude: 24.821,
      longitude: 67.031,
      has_exact_geography: true,
    },
  ],
};

async function stubAndLoad(page) {
  await page.route("**/api/map-search**", (route) =>
    route.fulfill({ json: STUB_PAYLOAD })
  );
  await page.route("**/api/search**", (route) =>
    route.fulfill({ json: STUB_PAYLOAD })
  );
  await page.goto("/");
  await page.waitForSelector(".card-wrap", { timeout: 30000 });
}

async function openGallery(page) {
  await page.locator(".card-wrap").first().click();
  await expect(page.locator("#drawer")).toHaveClass(/drawer-open/, {
    timeout: 3000,
  });
  await page.waitForTimeout(300);
  await page.locator("[data-gallery]").first().click();
  await expect(page.locator("#galleryModal")).not.toHaveClass(/hidden/, {
    timeout: 3000,
  });
}

test.describe("Image Gallery Modal", () => {
  test("clicking drawer image opens gallery", async ({ page }) => {
    await stubAndLoad(page);
    await openGallery(page);
    await expect(page.locator("#galleryCounter")).toHaveText("1 / 3");
  });

  test("next button advances to next image", async ({ page }) => {
    await stubAndLoad(page);
    await openGallery(page);
    await page.locator("#galleryNext").click();
    await expect(page.locator("#galleryCounter")).toHaveText("2 / 3");
  });

  test("prev button goes back to previous image", async ({ page }) => {
    await stubAndLoad(page);
    await openGallery(page);
    await page.locator("#galleryNext").click();
    await expect(page.locator("#galleryCounter")).toHaveText("2 / 3");
    await page.locator("#galleryPrev").click();
    await expect(page.locator("#galleryCounter")).toHaveText("1 / 3");
  });

  test("close button dismisses gallery", async ({ page }) => {
    await stubAndLoad(page);
    await openGallery(page);
    await page.locator("#galleryClose").click();
    await expect(page.locator("#galleryModal")).toHaveClass(/hidden/);
  });

  test("arrow keys navigate images", async ({ page }) => {
    await stubAndLoad(page);
    await openGallery(page);
    await page.keyboard.press("ArrowRight");
    await expect(page.locator("#galleryCounter")).toHaveText("2 / 3");
    await page.keyboard.press("ArrowRight");
    await expect(page.locator("#galleryCounter")).toHaveText("3 / 3");
    await page.keyboard.press("ArrowLeft");
    await expect(page.locator("#galleryCounter")).toHaveText("2 / 3");
  });

  test("next does not go past last image", async ({ page }) => {
    await stubAndLoad(page);
    await openGallery(page);
    await page.locator("#galleryNext").click();
    await page.locator("#galleryNext").click();
    await expect(page.locator("#galleryCounter")).toHaveText("3 / 3");
    await page.locator("#galleryNext").click();
    await expect(page.locator("#galleryCounter")).toHaveText("3 / 3");
  });

  test("prev does not go before first image", async ({ page }) => {
    await stubAndLoad(page);
    await openGallery(page);
    await page.locator("#galleryPrev").click();
    await expect(page.locator("#galleryCounter")).toHaveText("1 / 3");
  });

  test("clicking gallery backdrop closes modal", async ({ page }) => {
    await stubAndLoad(page);
    await openGallery(page);
    await page.locator("#galleryModal").click({ position: { x: 5, y: 5 } });
    await expect(page.locator("#galleryModal")).toHaveClass(/hidden/);
  });
});
