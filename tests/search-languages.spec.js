// English and Urdu must reach the same filters and results on every city tab.
const { test, expect } = require('@playwright/test');
const cases = [
  ['karachi', 'Clifton', '2 bed flat in Clifton under 50k', 'کلفٹن میں ۲ کمروں کا فلیٹ ۵۰ ہزار تک'],
  ['lahore', 'Gulberg', '2 bed flat in Gulberg under 50k', 'گلبرگ میں دو کمروں کا فلیٹ پچاس ہزار تک'],
  ['islamabad', 'F 10', '2 bed flat in F-10 under 50k', 'ایف ۱۰ میں ۲ کمروں کا فلیٹ ۵۰ ہزار تک'],
];
for (const [city, area, english, urdu] of cases) {
  for (const [language, query] of [['English', english], ['Urdu', urdu]]) {
    test(`${city} ${language} applies area, beds, type and budget`, async ({ page }) => {
      await page.goto('/');
      await expect(page.locator('.card-wrap').first()).toBeVisible();
      await page.locator(`.city-tab[data-city="${city}"]`).click();
      await expect(page.locator('.card-wrap').first()).toBeVisible();
      const searched = page.waitForResponse(response => {
        const url = new URL(response.url());
        return url.pathname === '/api/search' && url.searchParams.get('area') === area
          && url.searchParams.get('bedrooms') === '2'
          && url.searchParams.get('price_max') === '50000';
      });
      await page.locator('#nlInput').fill(query);
      await page.locator('#nlInput').press('Enter');
      const response = await searched;
      expect(response.ok()).toBeTruthy();
      const body = await response.json();
      expect(body.results.length).toBeGreaterThan(0);
      for (const listing of body.results) {
        expect(listing.bedrooms).toBe(2);
        expect(listing.price).toBeLessThanOrEqual(50000);
      }
      await expect(page.locator('#nlUnderstood')).toContainText(area);
      await expect(page.locator('#bedsChip')).toContainText('2 Bed');
      await expect(page.locator('#priceChip')).toContainText('50K');
      await expect(page.locator('#typeChip')).toHaveClass(/has-value/);
    });
  }
}
