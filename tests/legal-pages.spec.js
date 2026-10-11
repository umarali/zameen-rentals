const { test, expect } = require('@playwright/test');

const PUBLIC_PAGES = ['/about', '/pricing', '/faq', '/privacy', '/terms'];
const CLIENT = { 'X-Client-Id': 'legalpagesspec01' };

test('pricing page shows the packs, costs and starter credits from /api/credits', async ({ page, request }) => {
  const res = await request.get('/api/credits', { headers: CLIENT });
  expect(res.status()).toBe(200);
  const credits = await res.json();
  await page.goto('/pricing');

  // Every pack the API sells is on the page with the same credits and price, and nothing else is.
  const packs = await page.locator('.pack-list li').evaluateAll(items => items.map(li => ({
    id: li.dataset.pack, credits: Number(li.dataset.credits), price_pkr: Number(li.dataset.pricePkr), text: li.textContent,
  })));
  expect(packs.map(p => p.id).sort()).toEqual(credits.packs.map(p => p.id).sort());
  for (const pack of credits.packs) {
    const shown = packs.find(p => p.id === pack.id);
    expect(shown).toMatchObject({ credits: pack.credits, price_pkr: pack.price_pkr });
    expect(shown.text).toContain(`${pack.credits} credits`);
    expect(shown.text).toContain(`Rs ${pack.price_pkr}`);
  }

  // Each listed action costs what the API charges, in the visible text too.
  const actions = await page.locator('.cost-list li').evaluateAll(items => items.map(li => ({
    action: li.dataset.action, cost: Number(li.dataset.cost), text: li.querySelector('.cost').textContent,
  })));
  expect(actions.length).toBeGreaterThan(0);
  for (const item of actions) {
    expect(credits.costs).toHaveProperty(item.action);
    expect(item.cost).toBe(credits.costs[item.action]);
    expect(item.text).toMatch(new RegExp(`^${credits.costs[item.action]} credits?\\b`));
  }

  // A brand-new client's balance is the starter grant.
  const starter = page.locator('[data-starter-credits]');
  await expect(starter).toHaveAttribute('data-starter-credits', String(credits.balance));
  await expect(starter).toContainText(`${credits.balance} free credits`);
  await expect(page.locator('main')).toContainText('Pay once. Nothing renews.');
  await expect(page.locator('main')).toContainText('Paid actions pause until you add credits');
});

test('public pages never render owner notes and link to privacy and terms', async ({ page }) => {
  for (const path of PUBLIC_PAGES) {
    await page.goto(path);
    const text = await page.locator('body').innerText();
    expect(text, path).not.toMatch(/DECISION|CHECK:|under consideration|not available yet/i);
    const footer = page.locator('footer nav');
    await expect(footer.locator('a[href="/privacy"]'), path).toHaveCount(1);
    await expect(footer.locator('a[href="/terms"]'), path).toHaveCount(1);
    const schema = JSON.parse(await page.locator('script[type="application/ld+json"]').textContent());
    expect(schema.url).toBe('https://zameenrental.com' + path);
    await expect(page.locator('meta[property="og:url"]')).toHaveAttribute('content', 'https://zameenrental.com' + path);
  }
  await page.goto('/pricing');
  await expect(page.locator('main a[href="/terms#refunds"]')).toHaveCount(1);
  await expect(page.locator('main a[href="/privacy"]')).toHaveCount(1);
  await page.goto('/faq');
  await expect(page.locator('main a[href="/terms#refunds"]')).toHaveCount(1);
  await expect(page.locator('main a[href="/privacy"]')).toHaveCount(1);
  await page.goto('/terms');
  for (const id of ['credits', 'refunds']) await expect(page.locator(`#${id}`)).toBeVisible();
});

test('sitemap lists the privacy and terms pages', async ({ request }) => {
  const xml = await (await request.get('/sitemap.xml')).text();
  for (const path of PUBLIC_PAGES) expect(xml).toContain(`<loc>https://zameenrental.com${path}</loc>`);
});

test('privacy and terms open from the menu without losing the search', async ({ page }) => {
  await page.goto('/?city=lahore');
  await expect(page.locator('.card-wrap').first()).toBeVisible();
  const url = page.url();
  for (const [name, title, text] of [['Privacy', 'Privacy policy', 'Your random ID'], ['Terms', 'Terms of use', 'nothing renews']]) {
    await page.getByRole('button', { name: 'Open menu', exact: true }).click();
    await page.locator('#siteMenu').getByRole('link', { name, exact: true }).click();
    const dialog = page.getByRole('dialog', { name: title, exact: true });
    await expect(dialog).toBeVisible();
    await expect(dialog).toContainText(text);
    await expect(dialog.locator('ul li').first()).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(dialog).toBeHidden();
    expect(page.url()).toBe(url);
  }
});
