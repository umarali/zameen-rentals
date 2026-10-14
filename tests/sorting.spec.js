const { test, expect } = require('@playwright/test');

const searchPaths = ['/api/search', '/api/map-search', '/api/nearby-search'];
function nextSearch(page, sort) {
  return page.waitForResponse(response => {
    const url = new URL(response.url());
    return searchPaths.includes(url.pathname) && url.searchParams.get('sort') === sort;
  });
}

test('sort is visible above the listings and changes their price order', async ({ page }) => {
  await page.goto('/?city=lahore');
  await expect(page.locator('.card-wrap').first()).toBeVisible();
  const sort = page.getByRole('combobox', { name: 'Sort by', exact: true });
  await expect(sort).toBeVisible();
  const sortBox = await sort.boundingBox();
  const countBox = await page.locator('#resultsCount').boundingBox();
  if (page.viewportSize().width >= 640) {
    expect(Math.abs(sortBox.y + sortBox.height / 2 - countBox.y - countBox.height / 2)).toBeLessThan(2);
  } else {
    expect(sortBox.y).toBeGreaterThanOrEqual(countBox.y + countBox.height);
  }
  await expect(page.locator('#dataSource')).toBeHidden();
  await expect(page.locator('body')).not.toContainText('Instant /');
  expect((await sort.boundingBox()).y).toBeLessThan((await page.locator('.card-wrap').first().boundingBox()).y);
  for (const value of ['price_low', 'price_high']) {
    const received = nextSearch(page, value);
    await sort.selectOption(value);
    const response = await received;
    expect(response.ok()).toBe(true);
    const data = await response.json();
    expect(data.results.length).toBeGreaterThan(1);
    const prices = data.results.map(item => item.price).filter(price => price != null);
    for (let i = 1; i < prices.length; i++) {
      if (value === 'price_low') expect(prices[i]).toBeGreaterThanOrEqual(prices[i - 1]);
      else expect(prices[i]).toBeLessThanOrEqual(prices[i - 1]);
    }
    await expect(page.locator('.card-wrap').first()).toHaveAttribute('data-zameen-id', String(data.results[0].zameen_id));
    await expect(sort).toHaveValue(value);
    await expect(page.locator('#moreChip')).not.toHaveClass(/has-value/);
  }
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test('clearing furnishing preserves sort; Clear all resets it', async ({ page }) => {
  await page.goto('/?city=lahore');
  await expect(page.locator('.card-wrap').first()).toBeVisible();
  const sort = page.getByRole('combobox', { name: 'Sort by', exact: true });
  const initiallySorted = nextSearch(page, 'price_low');
  await sort.selectOption('price_low');
  await initiallySorted;
  await page.locator('#moreChip').click();
  const furnished = page.waitForResponse(response => {
    const url = new URL(response.url());
    return searchPaths.includes(url.pathname) && url.searchParams.get('furnished') === 'true';
  });
  await page.locator('#furnishingRow [data-furnishing="furnished"]').click();
  await furnished;
  await page.keyboard.press('Escape');
  await expect(page.locator('#moreChip')).toContainText('More (1)');
  const cleared = nextSearch(page, 'price_low');
  await page.locator('[data-chip-clear="more"]').click();
  expect(new URL((await cleared).url()).searchParams.has('furnished')).toBe(false);
  await expect(sort).toHaveValue('price_low');
  await expect(page.locator('#moreChip')).not.toHaveClass(/has-value/);
  const reset = nextSearch(page, null);
  await page.locator('#clearAllBtn').click();
  await reset;
  await expect(sort).toHaveValue('');
});

test('Near Me offers nearest ordering and resets to browse ordering on exit', async ({ page, context }) => {
  await context.grantPermissions(['geolocation']);
  await context.setGeolocation({ latitude: 31.522361, longitude: 74.347172 });
  await page.goto('/?city=lahore');
  await expect(page.locator('.card-wrap').first()).toBeVisible();
  const sort = page.getByRole('combobox', { name: 'Sort by', exact: true });
  await expect(sort.locator('option[value="distance"]')).toHaveCount(0);
  await page.locator('#nearbyChip').click();
  await expect(page.locator('#listingsTitle')).toHaveText('Rentals near you');
  await expect(sort.locator('option[value=""]')).toHaveText('Nearest');
  const priced = nextSearch(page, 'price_low');
  await sort.selectOption('price_low');
  await priced;
  const received = nextSearch(page, null);
  await sort.selectOption({ label: 'Nearest' });
  const response = await received;
  expect(new URL(response.url()).pathname).toBe('/api/nearby-search');
  const data = await response.json();
  expect(data.results.length).toBeGreaterThan(1);
  const distances = data.results.map(item => item.distance_km);
  for (let i = 1; i < distances.length; i++) expect(distances[i]).toBeGreaterThanOrEqual(distances[i - 1]);
  await page.locator('[data-nearby-clear]').click();
  await expect(sort).toHaveValue('');
  await expect(sort.locator('option[value="distance"]')).toHaveCount(0);
});

async function expectUniqueOptions(page) {
  const labels = await page.locator('#sortSelect option:not([hidden])').allTextContents();
  expect(new Set(labels).size).toBe(labels.length);
}

test('sorting choices are unique in city, area and Near Me modes', async ({ page, context }) => {
  await context.grantPermissions(['geolocation']);
  await context.setGeolocation({ latitude: 31.522361, longitude: 74.347172 });
  await page.goto('/?city=lahore');
  await expect(page.locator('.card-wrap').first()).toBeVisible();
  await expectUniqueOptions(page); // Desktop viewport, or mobile city mode.
  await page.goto('/?city=lahore&area=Gulberg');
  await expect(page.locator('#listingsTitle')).toHaveText('Rentals in Gulberg');
  await expectUniqueOptions(page);
  await page.locator('#nearbyChip').click();
  await expect(page.locator('#listingsTitle')).toHaveText('Rentals near you');
  await expectUniqueOptions(page);
});

test('NL city switch resets the visible sort to match its request', async ({ page }) => {
  await page.route('**/api/parse-query?**', route => route.fulfill({ json: { filters: { city_hint: 'karachi' } } }));
  await page.goto('/?city=lahore');
  await expect(page.locator('.card-wrap').first()).toBeVisible();
  const sort = page.getByRole('combobox', { name: 'Sort by', exact: true });
  const sorted = nextSearch(page, 'price_low');
  await sort.selectOption('price_low');
  await sorted;
  const switched = page.waitForResponse(response => {
    const url = new URL(response.url());
    return searchPaths.includes(url.pathname) && url.searchParams.get('city') === 'karachi';
  });
  await page.locator('#nlInput').fill('rentals in Karachi');
  await page.locator('#nlInput').press('Enter');
  const requestSort = new URL((await switched).url()).searchParams.get('sort') || '';
  expect(requestSort).toBe('');
  await expect(sort).toHaveValue(requestSort);
});

test('saved explicit recency stays selected without duplicating its default', async ({ page }) => {
  await page.goto('/?city=lahore&area=Gulberg&sort=newest');
  await expect(page.locator('#listingsTitle')).toHaveText('Rentals in Gulberg');
  const sort = page.getByRole('combobox', { name: 'Sort by', exact: true });
  await expect(sort).toHaveValue('newest');
  await expectUniqueOptions(page);
  expect(new URL(page.url()).searchParams.get('sort')).toBe('newest');
  const priced = nextSearch(page, 'price_low');
  await sort.selectOption('price_low');
  await priced;
  const recent = nextSearch(page, null);
  await sort.selectOption({ label: 'Recently updated' });
  await recent;
  await expect(sort).toHaveValue('');
  await expectUniqueOptions(page);
});

test('Search tips city selection keeps the visible sort and request in sync', async ({ page }) => {
  await page.goto('/?city=lahore&sort=price_low');
  await expect(page.locator('.card-wrap').first()).toBeVisible();
  await page.locator('#siteMenuBtn').click();
  await page.locator('#welcomeBtn').click();
  const switched = page.waitForResponse(response => {
    const url = new URL(response.url());
    return searchPaths.includes(url.pathname) && url.searchParams.get('city') === 'karachi';
  });
  await page.locator('[data-wcity="karachi"]').click();
  const requestSort = new URL((await switched).url()).searchParams.get('sort');
  expect(requestSort).toBe('price_low');
  await page.locator('#welcomeBrowse').click();
  await expect(page.getByRole('combobox', { name: 'Sort by', exact: true })).toHaveValue(requestSort);
});
