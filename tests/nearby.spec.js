// @ts-check
const { test, expect } = require('@playwright/test');

test.beforeEach(async ({ page }) => {
  await page.route('**/api/listing-detail?**', route => route.fulfill({ json: {} }));
});

const cases = [
  { from: 'lahore', to: 'islamabad', lat: 33.691531, lng: 73.005431 },
  { from: 'islamabad', to: 'lahore', lat: 31.522361, lng: 74.347172 },
  { from: 'lahore', to: 'karachi', lat: 24.82, lng: 67.028 },
  { from: 'islamabad', to: 'islamabad', lat: 33.691531, lng: 73.005431 },
  { from: 'lahore', to: 'islamabad', lat: 33.691531, lng: 73.005431, stored: true },
];

for (const { from, to, lat, lng, stored } of cases) {
  test(`Near Me selects ${to} from ${from}${stored ? ' with a saved location' : ''}`, async ({ page, context }) => {
    // Keep this frontend regression independent of upstream pin enrichment.
    await page.route('**/api/nearby-search?**', route => route.fulfill({
      json: {
        total: 1, page: 1, per_page: 25, source: 'local', mode: 'nearby',
        results: [{
          title: `Nearby rental in ${to}`,
          url: 'https://www.zameen.com/Property/test-nearby-city.html',
          price: 25000, bedrooms: 1, property_type: 'Apartment',
          latitude: lat, longitude: lng, has_exact_geography: true,
          location_source: 'listing_exact', distance_km: 0.1,
        }],
      },
    }));
    if (stored) {
      await page.addInitScript(({ lat, lng }) => {
        sessionStorage.setItem('rk_userLocation', JSON.stringify({ lat, lng, accuracy: 10, ts: Date.now() }));
        navigator.geolocation.getCurrentPosition = () => { throw new Error('Saved location should be reused'); };
      }, { lat, lng });
    } else {
      await context.grantPermissions(['geolocation']);
      await context.setGeolocation({ latitude: lat, longitude: lng });
    }

    // A previous city's area must not restrict the new city's nearby results.
    const oldArea = from === 'lahore' ? 'Gulberg' : 'F 10';
    await page.goto(`/?city=${from}&area=${encodeURIComponent(oldArea)}&type=apartment&beds=1&price_max=100000`);
    await expect(page.locator('.card-wrap').first()).toBeVisible();
    const nearbyResponse = page.waitForResponse(response => new URL(response.url()).pathname === '/api/nearby-search');
    await page.locator('#nearbyChip').click();
    const response = await nearbyResponse;
    expect(response.ok()).toBeTruthy();
    const params = new URL(response.url()).searchParams;
    expect(params.get('city')).toBe(to);
    expect(params.get('area')).toBeNull();
    expect(params.get('lat')).toBe(lat.toFixed(6));
    expect(params.get('lng')).toBe(lng.toFixed(6));
    expect(params.get('property_type')).toBe('apartment');
    expect(params.get('bedrooms')).toBe('1');
    expect(params.get('price_max')).toBe('100000');
    expect((await response.json()).total).toBeGreaterThan(0);
    await expect(page.locator(`.city-tab[data-city="${to}"]`)).toHaveClass(/active/);
    await expect(page.locator('#areaChip')).not.toHaveClass(/has-value/);
    await expect(page.locator('#listingsTitle')).toHaveText('Rentals near you');
    await expect(page.locator('.card-wrap').first()).toBeVisible();
    await expect(page.locator('#radiusChip')).toBeVisible();
    expect(await page.evaluate(() => JSON.parse(localStorage.getItem('rk_s') || '{}').city)).toBe(to);

    // Subsequent radius searches must keep the automatically selected city.
    const radiusResponse = page.waitForResponse(response => {
      const url = new URL(response.url());
      return url.pathname === '/api/nearby-search' && url.searchParams.get('radius_km') === '10';
    });
    await page.locator('#radiusChip').click();
    await page.locator('#radiusOptions [data-radius-km="10"]').click();
    expect(new URL((await radiusResponse).url()).searchParams.get('city')).toBe(to);
  });
}

test('denied location leaves the selected city unchanged', async ({ page }) => {
  await page.addInitScript(() => {
    navigator.geolocation.getCurrentPosition = (_success, error) => error({ code: 1 });
  });
  const nearbyRequests = [];
  page.on('request', request => {
    if (new URL(request.url()).pathname === '/api/nearby-search') nearbyRequests.push(request.url());
  });
  await page.goto('/?city=lahore');
  await expect(page.locator('.card-wrap').first()).toBeVisible();
  await page.locator('#nearbyChip').click();
  await expect(page.getByText('Location permission was denied.')).toBeVisible();
  await expect(page.locator('.city-tab[data-city="lahore"]')).toHaveClass(/active/);
  await expect(page.locator('#nearbyChip')).not.toHaveClass(/has-value/);
  expect(nearbyRequests).toHaveLength(0);
});

// These cases use the actual local API and seeded exact-pin listings.
for (const { from, to, lat, lng } of cases.slice(0, 3)) {
  test(`Near Me returns real API results in ${to} from ${from}`, async ({ page, context }) => {
    await context.grantPermissions(['geolocation']);
    await context.setGeolocation({ latitude: lat, longitude: lng });
    await page.goto(`/?city=${from}`);
    await expect(page.locator('.card-wrap').first()).toBeVisible();
    const pending = page.waitForResponse(r => new URL(r.url()).pathname === '/api/nearby-search');
    await page.locator('#nearbyChip').click();
    const response = await pending;
    expect(response.ok()).toBeTruthy();
    expect(new URL(response.url()).searchParams.get('city')).toBe(to);
    const data = await response.json();
    expect(data.total).toBeGreaterThan(0);
    expect(data.results.length).toBeGreaterThan(0);
    for (const result of data.results) {
      expect(result.has_exact_geography).toBeTruthy();
      expect(result.distance_km).toBeLessThanOrEqual(5);
    }
    await expect(page.locator(`.city-tab[data-city="${to}"]`)).toHaveClass(/active/);
    await expect(page.locator('#listingsTitle')).toHaveText('Rentals near you');
    await expect(page.locator('.card-wrap').first()).toBeVisible();
  });
}

test('Near Me outside the three cities explains instead of searching', async ({ page, context }) => {
  let nearbyCalls = 0;
  await page.route('**/api/nearby-search?**', route => { nearbyCalls += 1; return route.fulfill({ json: { total: 0, results: [] } }); });
  await context.grantPermissions(['geolocation']);
  await context.setGeolocation({ latitude: 30.1575, longitude: 71.5249 }); // Multan, ~310 km from Lahore
  await page.goto('/?city=karachi');
  await expect(page.locator('.card-wrap').first()).toBeVisible();
  await page.locator('#nearbyChip').click();
  await expect(page.getByText(/Near Me covers Karachi, Lahore and Islamabad/)).toBeVisible();
  await expect(page.locator('.city-tab[data-city="karachi"]')).toHaveClass(/active/);
  await expect(page.locator('#nearbyChip')).not.toHaveClass(/has-value/);
  expect(nearbyCalls).toBe(0);
});

test('Near Me asks again when the remembered location is older than 30 minutes', async ({ page }) => {
  await page.route('**/api/nearby-search?**', route => route.fulfill({
    json: { total: 0, page: 1, per_page: 25, source: 'local', mode: 'nearby', results: [] },
  }));
  // A controlled location service: counts requests and answers with window.__geo.
  // (Chromium's own position cache follows real time, not the page clock.)
  await page.addInitScript(() => {
    window.__geo = { lat: 31.522361, lng: 74.347172 }; // Lahore
    window.__geoCalls = 0;
    Object.defineProperty(navigator, 'geolocation', { configurable: true, value: {
      getCurrentPosition(ok) {
        window.__geoCalls += 1;
        ok({ coords: { latitude: window.__geo.lat, longitude: window.__geo.lng, accuracy: 10 } });
      },
      watchPosition() { return 0; }, clearWatch() {},
    } });
  });
  await page.clock.install();
  await page.goto('/?city=lahore');
  await expect(page.locator('.card-wrap').first()).toBeVisible();
  let request = page.waitForRequest(r => new URL(r.url()).pathname === '/api/nearby-search');
  await page.locator('#nearbyChip').click();
  expect(new URL((await request).url()).searchParams.get('city')).toBe('lahore');
  expect(await page.evaluate(() => window.__geoCalls)).toBe(1);

  // Within 30 minutes the remembered location is reused without asking.
  await page.locator('[data-nearby-clear]').click();
  await page.clock.fastForward('10:00');
  request = page.waitForRequest(r => new URL(r.url()).pathname === '/api/nearby-search');
  await page.locator('#nearbyChip').click();
  await request;
  expect(await page.evaluate(() => window.__geoCalls)).toBe(1);

  // The app stays open while the user travels to Islamabad.
  await page.locator('[data-nearby-clear]').click();
  await page.clock.fastForward('21:00');
  await page.evaluate(() => { window.__geo = { lat: 33.691531, lng: 73.005431 }; });
  request = page.waitForRequest(r => new URL(r.url()).pathname === '/api/nearby-search');
  await page.locator('#nearbyChip').click();
  expect(new URL((await request).url()).searchParams.get('city')).toBe('islamabad');
  expect(await page.evaluate(() => window.__geoCalls)).toBe(2);
  await expect(page.locator('.city-tab[data-city="islamabad"]')).toHaveClass(/active/);
});
