// @ts-check
const { test, expect } = require('@playwright/test');
const ORIGIN = 'https://zameenrentals.emerssive.com';

for (const path of ['/about', '/pricing', '/faq']) {
  test(`${path} works without JavaScript and links back to rental search`, async ({ browser, baseURL }, testInfo) => {
    const context = await browser.newContext({ javaScriptEnabled: false, viewport: testInfo.project.use.viewport });
    const page = await context.newPage();
    const response = await page.goto(`${baseURL}${path}`);
    expect(response.status()).toBe(200);
    await expect(page.locator('main h1')).toBeVisible();
    await expect(page.locator('link[rel="canonical"]')).toHaveAttribute('href', ORIGIN + path);
    const schema = JSON.parse(await page.locator('script[type="application/ld+json"]').textContent());
    expect(schema.url).toBe(ORIGIN + path);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: testInfo.outputPath('page.png'), fullPage: true });
    await page.getByRole('navigation', { name: 'Main navigation' }).getByRole('link', { name: 'Search rentals' }).click();
    expect(new URL(page.url()).pathname).toBe('/');
    await context.close();
  });
}

test('sitemap pages resolve and unknown paths remain 404', async ({ request }) => {
  const robots = await request.get('/robots.txt');
  expect(robots.status()).toBe(200);
  expect(robots.headers()['content-type']).toContain('text/plain');
  expect(await robots.text()).toContain(`Sitemap: ${ORIGIN}/sitemap.xml`);
  const sitemap = await request.get('/sitemap.xml');
  expect(sitemap.status()).toBe(200);
  expect(sitemap.headers()['content-type']).toContain('application/xml');
  const urls = [...(await sitemap.text()).matchAll(/<loc>(.*?)<\/loc>/g)].map(m => new URL(m[1]));
  expect(urls.map(u => u.pathname)).toEqual(['/', '/about', '/pricing', '/faq']);
  for (const url of urls) {
    expect(url.origin).toBe(ORIGIN);
    expect((await request.get(url.pathname)).status()).toBe(200);
  }
  for (const path of ['/not-a-page', '/private.txt', '/about.html', '/pricing/unknown']) {
    expect((await request.get(path)).status()).toBe(404);
  }
});

test('FAQ structured answers match visible answers', async ({ page }) => {
  await page.goto('/faq');
  const schema = JSON.parse(await page.locator('script[type="application/ld+json"]').textContent());
  const visible = await page.locator('.faq section').evaluateAll(sections => sections.map(s => ({question:s.querySelector('h2').textContent,answer:s.querySelector('p').textContent})));
  expect(schema.mainEntity.map(q => ({question:q.name,answer:q.acceptedAnswer.text}))).toEqual(visible);
});

test('pricing takes a visitor directly to search without a checkout', async ({ page }) => {
  await page.goto('/pricing');
  await page.locator('.plan .button').click();
  await expect(page.locator('#nlInput')).toBeVisible();
  await expect(page.locator('.card-wrap').first()).toBeVisible();
});

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
