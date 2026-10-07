// Recipe for features/filters.md: city tab → area autocomplete → type → clear all.
export default async ({ page, expect, proof, api }) => {
  await page.locator(".card-wrap").first().waitFor();
  await page.locator('.city-tab[data-city="karachi"]').click();
  await expect(page.locator('.city-tab[data-city="karachi"]')).toHaveClass(/active/);
  // Desktop titles a city switch "Rentals in this map view"; assert on the cards instead.
  await expect(page.locator("#listingsGrid .card-wrap").first()).toContainText("Karachi");
  await proof("karachi-baseline", await page.locator("#resultsCount").innerText());

  await page.locator("#areaChip").click();
  await page.locator("#areaInput").fill("Clifton");
  await page.locator(".area-opt", { hasText: "Clifton" }).first().click();
  await expect(page.locator("#areaChip")).toHaveClass(/has-value/);
  await expect(page.locator("#listingsTitle")).toContainText("Clifton");

  await page.locator("#typeChip").click();
  await page.locator('#typeGrid .chip[data-type="house"]').click();
  await expect(page.locator("#typeChip")).toHaveClass(/has-value/);
  await expect(page.locator("#listingsGrid .card-wrap").first()).toContainText(/house/i);
  const cards = await page.locator("#listingsGrid .card-wrap").allInnerTexts();
  expect(cards.length).toBeGreaterThan(0);
  expect(cards.every((t) => /house/i.test(t) && /Clifton/.test(t))).toBe(true);
  await proof("clifton-house", `${await page.locator("#resultsCount").innerText()} · ${cards.length} cards, all Clifton houses`);

  // Second view of the same state: the API the UI calls, plus the persisted filter state.
  const { json } = await api("/api/search?city=karachi&area=Clifton&property_type=house");
  expect(json.total).toBeGreaterThan(0);
  const saved = await page.evaluate(() => JSON.parse(localStorage.getItem("rk_s") || "{}"));
  expect(saved.city).toBe("karachi");

  await page.locator("#clearAllBtn").click();
  await expect(page.locator("#areaChip")).not.toHaveClass(/has-value/);
  await expect(page.locator("#typeChip")).not.toHaveClass(/has-value/);
  await expect(page.locator("#clearAllBtn")).toBeHidden();
  await proof("cleared", "all filter chips reset");
};
