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
    expect(text, path).not.toMatch(/DECISION|CHECK:|under consideration|not available yet|\[(?:OPERATOR NAME|CONTACT EMAIL|LOG RETENTION PERIOD)\]|registered company|Claude|AI model/i);
    if (path === "/about") {
      expect(text).toContain("rental aggregator");
      expect(text).toContain("currently come from Zameen.com");
      expect(text).not.toMatch(/Facebook|Graana|OLX/);
    }
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

test('legal menu links open new tabs and preserve the search', async ({ page, context }) => {
  await page.goto('/?city=lahore');
  await expect(page.locator('.card-wrap').first()).toBeVisible();
  await page.locator('#nlInput').fill('two bedrooms under 60000');
  const url = page.url();
  for (const [name, path, title] of [['Privacy', '/privacy', 'Privacy policy'], ['Terms', '/terms', 'Terms of use']]) {
    await page.locator('#siteMenuBtn').click();
    const link = page.locator('#siteMenu').getByRole('link', { name, exact: true });
    await expect(link).toHaveAttribute('target', '_blank');
    await expect(link).toHaveAttribute('rel', /\bnoopener\b/);
    const opened = context.waitForEvent('page');
    await link.click();
    const tab = await opened;
    await expect(tab).toHaveURL(new RegExp(`${path}$`));
    await expect(tab.getByRole('heading', { name: title, exact: true })).toBeVisible();
    expect(await tab.evaluate(() => window.opener === null)).toBe(true);
    await expect(page.locator('#siteInfoDialog')).toBeHidden();
    expect(page.url()).toBe(url);
    await expect(page.locator('#nlInput')).toHaveValue('two bedrooms under 60000');
    await tab.close();
    // Native new-tab navigation leaves the disclosure open in the original tab.
    await page.locator('#nlInput').click();
  }
});

test('pricing menu link navigates to a full page', async ({ page }) => {
  await page.goto('/?city=lahore');
  await expect(page.locator('.card-wrap').first()).toBeVisible();
  await page.locator('#siteMenuBtn').click();
  await page.locator('#siteMenu').getByRole('link', { name: 'Pricing', exact: true }).click();
  await expect(page).toHaveURL(/\/pricing$/);
  await expect(page.getByRole('heading', { name: 'Pricing', exact: true })).toBeVisible();
  await expect(page.locator('#siteInfoDialog')).toHaveCount(0);
  await expect(page.locator('main')).toContainText('Pay once. Nothing renews.');
  await page.locator('.return-search').click();
  await expect(page.locator('#nlInput')).toBeVisible();
});

test('every legal link on public pages opens its destination in a new tab', async ({ page, context }) => {
  for (const path of PUBLIC_PAGES) {
    await page.goto(path);
    // FAQ answers are collapsed by default; exercise their links too.
    for (const detail of await page.locator('details').all()) await detail.locator('summary').click();
    const links = page.locator('a[href^="/privacy"], a[href^="/terms"]');
    for (const link of await links.all()) {
      await expect(link).toHaveAttribute('target', '_blank');
      await expect(link).toHaveAttribute('rel', /\bnoopener\b/);
      const href = await link.getAttribute('href');
      const opened = context.waitForEvent('page');
      await link.click();
      const tab = await opened;
      await tab.waitForURL(url => url.pathname + url.hash === href);
      await expect(tab.locator('main h1')).toBeVisible();
      if (href.includes('#')) await expect(tab.locator(href.slice(href.indexOf('#')))).toBeVisible();
      expect(await tab.evaluate(() => window.opener === null)).toBe(true);
      expect(new URL(page.url()).pathname).toBe(path);
      await tab.close();
    }
  }
});

test('FAQ dialog links use new tabs for legal pages and full-page pricing', async ({ page, context }) => {
  await page.goto('/?city=lahore');
  await expect(page.locator('.card-wrap').first()).toBeVisible();
  await page.locator('#siteMenuBtn').click();
  await page.locator('#siteMenu').getByRole('link', { name: 'FAQs', exact: true }).click();
  const dialog = page.locator('#siteInfoDialog');
  for (const [question, href] of [['Can I get a refund?', '/terms#refunds'], ['What happens to my data?', '/privacy']]) {
    await dialog.locator('summary').filter({ hasText: question }).click();
    const opened = context.waitForEvent('page');
    await dialog.locator(`a[href="${href}"]`).click();
    const tab = await opened;
    await tab.waitForURL(url => url.pathname + url.hash === href);
    await expect(tab.locator('main h1')).toBeVisible();
    await tab.close();
    await expect(dialog).toBeVisible();
  }
  await dialog.locator('summary').filter({ hasText: 'What are credits?' }).click();
  await dialog.getByRole('link', { name: 'pricing page' }).click();
  await expect(page).toHaveURL(/\/pricing$/);
  await expect(page.locator('#siteInfoDialog')).toHaveCount(0);
});
