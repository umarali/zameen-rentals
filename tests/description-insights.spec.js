const { test, expect } = require('@playwright/test');

test('stored descriptions show attributed floors, conflicts and readable safe text', async ({ page, request }, testInfo) => {
  // Real disposable SQLite -> search API -> card -> detail API -> drawer.
  const response = await request.get('/api/search?city=karachi&area=DHA%20Defence&property_type=apartment&price_max=25000');
  expect(response.ok()).toBeTruthy();
  const payload = await response.json();
  const listing = payload.results.find(item => item.zameen_id === '99000001');
  expect(listing).toBeTruthy();
  for (const endpoint of ['search', 'map-search']) {
    await page.route(`**/api/${endpoint}?**`, route => route.fulfill({ json: { ...payload, results: [listing], total: 1 } }));
  }
  await page.goto('/');
  const card = page.locator('.card-wrap').first();
  await expect(card.locator('[data-floor-summary]')).toHaveText('Multiple floors mentioned · check details');
  await card.click();
  await expect(page.getByRole('region', { name: 'Floor information' })).toContainText('Floor: 2');
  await expect(page.getByRole('region', { name: 'Floor information' })).toContainText('third floor');
  const notes = page.getByRole('region', { name: 'From the description' });
  await expect(notes).not.toContainText('No lift available.');
  await expect(notes).toContainText('Water only at night.');
  const description = page.locator('#drawerDesc');
  await expect(description).toContainText('Separate entrance & parking.');
  expect((await description.innerText()).match(/No lift available\./g)).toHaveLength(1);
  const conflicts = page.getByRole('region', { name: 'Check with the advertiser' });
  await expect(conflicts).toContainText('The description includes opposing statements.');
  await expect(conflicts).toContainText('Lift available.');
  await expect(conflicts).toContainText('No lift available.');
  const original = page.locator('[data-original-description]');
  await expect(original.locator('div')).not.toBeVisible();
  await original.locator('summary').click();
  await expect(original.locator('div')).toBeVisible();
  expect((await original.innerText()).match(/No lift available\./g)).toHaveLength(2);
  await expect(original).not.toContainText('window.descriptionInjected');
  expect(await original.locator('script,img,iframe').count()).toBe(0);
  await original.locator('summary').click();
  await expect(description).not.toContainText('<');
  await expect(description).not.toContainText('window.descriptionInjected');
  expect(await page.evaluate(() => window.descriptionInjected)).toBeUndefined();
  expect(await description.locator('script,img,iframe').count()).toBe(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  await page.screenshot({ path: testInfo.outputPath('listing-details.png'), fullPage: true });
  await description.scrollIntoViewIfNeeded();
  await page.screenshot({ path: testInfo.outputPath('description-notes.png'), fullPage: true });
});

test('comparison keeps the attributed floor and distinguishes missing information', async ({ page, request }) => {
  const response = await request.get('/api/search?city=karachi&area=DHA%20Defence&property_type=apartment&price_max=30000');
  const payload = await response.json();
  expect(payload.results).toHaveLength(2);
  for (const endpoint of ['search', 'map-search']) {
    await page.route(`**/api/${endpoint}?**`, route => route.fulfill({ json: payload }));
  }
  await page.goto('/');
  await expect(page.locator('.card-wrap [data-action="compare"]')).toHaveCount(2);
  for (const button of await page.locator('.card-wrap [data-action="compare"]').all()) await button.click();
  await page.locator('.compare-tray-btn').click();
  const dialog = page.getByRole('dialog', { name: 'Compare (2)' });
  await expect(dialog).toContainText('Floor');
  await expect(dialog).toContainText('Multiple floors mentioned · check details');
  await expect(dialog).toContainText('Unknown');
});


test('old comparison snapshots do not claim an unstated floor', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('zr_compare_v1', JSON.stringify([
    { zameen_id: '900001', title: 'Older saved flat', price: 50000 },
    { zameen_id: '900002', title: 'Another saved flat', price: 60000 },
  ])));
  await page.goto('/');
  await page.locator('.compare-tray-btn').click();
  const dialog = page.getByRole('dialog', { name: 'Compare (2)' });
  await expect(dialog).toContainText('Unknown');
  await expect(dialog).not.toContainText('Not stated');
});

test('floor attribution remains when detail enrichment is unavailable', async ({ page }) => {
  const listing = { zameen_id: '900005', title: 'Third floor flat', price: 50000,
    url: 'https://www.zameen.com/Property/test-900005-1-1.html',
    floor: { label: '3rd floor', source: 'title', conflict: false } };
  for (const endpoint of ['search', 'map-search']) {
    await page.route(`**/api/${endpoint}?**`, route => route.fulfill({ json: { results: [listing], total: 1 } }));
  }
  await page.route('**/api/listing-detail?**', route => route.fulfill({ json: {} }));
  await page.goto('/');
  await page.locator('.card-wrap').first().click();
  await expect(page.getByRole('region', { name: 'Floor information' })).toContainText('From title');
});
