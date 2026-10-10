const { test, expect } = require('@playwright/test');
async function ready(page) {
  await page.goto('/?city=lahore');
  await expect(page.locator('.card-wrap').first()).toBeVisible();
}
async function topic(page, name) {
  await page.getByRole('button', { name:'Open menu', exact:true }).click();
  await page.locator('#siteMenu').getByRole('link', { name, exact:true }).click();
}

test('menu is a light disclosure that closes outside and with Escape', async ({ page }) => {
  await ready(page);
  const trigger = page.locator('#siteMenuBtn');
  await trigger.click();
  await expect(trigger).toHaveAttribute('aria-expanded', 'true');
  await expect(page.locator('#siteInfoDialog')).toBeHidden();
  await expect(page.locator('#siteMenu')).toBeVisible();
  await page.locator('#nlInput').click();
  await expect(page.locator('#siteMenu')).toBeHidden();
  await trigger.focus();
  await page.keyboard.press('ArrowDown');
  await expect(page.locator('#siteMenu a').first()).toBeFocused();
  await page.keyboard.press('ArrowDown');
  await expect(page.locator('#siteMenu a').nth(1)).toBeFocused();
  await page.keyboard.press('Escape');
  await expect(trigger).toBeFocused();
  await expect(trigger).toHaveAttribute('aria-expanded', 'false');
});

test('information keeps the search intact and restores focus', async ({ page }, testInfo) => {
  await ready(page);
  await page.locator('#nlInput').fill('two bedrooms under 60000');
  const before = await page.locator('.card-wrap').first().innerText();
  const url = page.url();
  await topic(page, 'Pricing');
  const dialog = page.getByRole('dialog', { name:'Pricing', exact:true });
  await expect(dialog).toContainText('Rs 0');
  await expect(dialog).toContainText("Paid access and the trial aren't available yet");
  expect(page.url()).toBe(url);
  await expect(dialog.locator('[data-info-close]')).toBeFocused();
  for (let i=0;i<5;i++) {
    await page.keyboard.press('Tab');
    expect(await dialog.evaluate(d => d.contains(document.activeElement) || document.activeElement === document.body)).toBe(true);
  }
  const bounds = await dialog.boundingBox();
  expect(bounds.x).toBeGreaterThanOrEqual(0);
  expect(bounds.width).toBeLessThanOrEqual(testInfo.project.use.viewport.width);
  await page.keyboard.press('Escape');
  await expect(dialog).toBeHidden();
  await expect(page.locator('#siteMenuBtn')).toBeFocused();
  await expect(page.locator('#nlInput')).toHaveValue('two bedrooms under 60000');
  await expect(page.locator('.card-wrap').first()).toHaveText(before, { useInnerText:true });
  await topic(page, 'About ZameenRentals');
  await expect(page.locator('#siteInfoDialog')).toContainText('Only Zameen.com is connected today');
  await page.getByRole('button', {name:'Back to search'}).click();
  await expect(page.locator('#nlInput')).toBeFocused();
  expect(page.url()).toBe(url);
});

test('FAQs disclose answers and help restores the visible menu trigger', async ({ page }) => {
  await ready(page);
  await topic(page, 'FAQs');
  const dialog = page.locator('#siteInfoDialog');
  await dialog.locator('summary').filter({hasText:'Are the homes still available?'}).click();
  await expect(dialog.getByText(/We cannot confirm availability/)).toBeVisible();
  await dialog.getByRole('button', {name:'Close information'}).click();
  await page.locator('#siteMenuBtn').click();
  await page.getByRole('button', {name:'Search tips'}).click();
  await expect(page.locator('#welcomeOverlay .welcome-panel')).toBeVisible();
  await page.locator('#welcomeClose').click();
  await expect(page.locator('#welcomeOverlay .welcome-panel')).toBeHidden();
  await expect(page.locator('#siteMenuBtn')).toBeFocused();
});

test('failed information request offers its public URL', async ({ page }) => {
  await ready(page);
  await page.route('**/pricing', route => route.fulfill({status:503, body:'Unavailable'}));
  await topic(page, 'Pricing');
  await expect(page.locator('#siteInfoDialog').getByRole('link', {name:'Open the page'})).toHaveAttribute('href','/pricing');
  await expect(page.locator('.site-info-content')).not.toHaveAttribute('aria-busy','true');
});

test('closing a pending request cannot replace the next topic', async ({ page }) => {
  await ready(page);
  let finish;
  const gate = new Promise(resolve => { finish = resolve; });
  await page.route('**/pricing', async route => {
    await gate;
    await route.fulfill({status:200,body:'<div class="site-info-body">Stale pricing response</div>'}).catch(() => {});
  });
  await topic(page, 'Pricing');
  await expect(page.locator('.site-info-content')).toHaveAttribute('aria-busy','true');
  await page.keyboard.press('Escape');
  await topic(page, 'About ZameenRentals');
  finish();
  await expect(page.locator('#siteInfoDialog')).toContainText('Only Zameen.com is connected today');
  await expect(page.locator('#siteInfoDialog')).not.toContainText('Stale pricing response');
});

for (const path of ['/about','/pricing','/faq']) {
  test(`${path} works without JavaScript and links back to search`, async ({ browser, baseURL }, testInfo) => {
    const context = await browser.newContext({ javaScriptEnabled:false, viewport:testInfo.project.use.viewport });
    const page = await context.newPage();
    expect((await page.goto(baseURL+path)).status()).toBe(200);
    await expect(page.locator('main h1')).toBeVisible();
    await expect(page.locator('link[rel="canonical"]')).toHaveAttribute('href','https://zameenrental.com'+path);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.locator('.return-search').click();
    expect(new URL(page.url()).pathname).toBe('/');
    await context.close();
  });
}

test('FAQ schema matches visible answers and unknown routes stay 404', async ({ page, request }) => {
  await page.goto('/faq');
  const schema = JSON.parse(await page.locator('script[type="application/ld+json"]').textContent());
  const answers = await page.locator('details').evaluateAll(ds => ds.map(d => ({name:d.querySelector('summary').textContent,text:d.querySelector('p').textContent})));
  expect(schema.mainEntity.map(q => ({name:q.name,text:q.acceptedAnswer.text}))).toEqual(answers);
  for (const path of ['/not-a-page','/about.html','/pricing/unknown']) expect((await request.get(path)).status()).toBe(404);
  expect((await request.get('/robots.txt')).status()).toBe(200);
  expect((await request.get('/sitemap.xml')).status()).toBe(200);
});
