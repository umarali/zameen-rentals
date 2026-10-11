// @ts-check
const { test, expect } = require('@playwright/test');

test('saved comparisons do not present mixed recorded dates as posting or availability checks', async ({ page }) => {
  await page.addInitScript(() => {
    const common = { title:'Comparison fixture', price:50000, bedrooms:2, bathrooms:2, area_size:'5 Marla', location:'Lahore', property_type:'Flat' };
    const date = new Date(Date.now() - 2 * 86400000).toISOString();
    localStorage.setItem('zr_compare_v1', JSON.stringify([
      {...common, zameen_id:'99100001', posted_at:date, first_seen_at:date},
      {...common, zameen_id:'99100002', posted_at:null, first_seen_at:date},
    ]));
  });
  await page.goto('/');
  await page.locator('[data-compare-open]').click();
  const modal = page.getByRole('dialog', {name:'Compare (2)'});
  await expect(modal.getByText('Recorded dates may be source dates or when first seen. They do not confirm availability.')).toBeVisible();
  const row = modal.getByRole('row').filter({hasText:'Recorded date'});
  await expect(row).toContainText(/2 days?/);
  await expect(row).not.toContainText(/Newest|Posted|Available/);
});
