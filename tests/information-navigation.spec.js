const { test, expect } = require('@playwright/test');
const paths = ['/faq', '/pricing', '/privacy', '/terms'];

test('menu destinations match their icons and preserve the search', async ({ page, context }) => {
  await page.goto('/?city=lahore');
  await expect(page.locator('.card-wrap').first()).toBeVisible();
  await page.locator('#nlInput').fill('two bedrooms under 60000');
  const original = page.url();
  for (const path of paths) {
    await page.locator('#siteMenuBtn').click();
    const link = page.locator(`#siteMenu a[href="${path}"]`);
    await expect(link).toHaveAttribute('target', '_blank');
    await expect(link).toHaveAccessibleName(/opens in a new tab/);
    await expect(link.locator('[aria-hidden="true"]')).toHaveText('↗');
    const opened = context.waitForEvent('page');
    await link.click();
    const tab = await opened;
    await expect(tab).toHaveURL(new RegExp(`${path}$`));
    await expect(tab.locator('main h1')).toBeVisible();
    expect(await tab.evaluate(() => window.opener === null)).toBe(true);
    expect(page.url()).toBe(original);
    await expect(page.locator('#nlInput')).toHaveValue('two bedrooms under 60000');
    await expect(page.locator('#siteInfoDialog')).toBeHidden();
    await tab.close();
  }
  await page.locator('#siteMenuBtn').click();
  const about = page.locator('#siteMenu a[href="/about"]');
  await expect(about).not.toHaveAttribute('target', '_blank');
  await expect(about).toHaveAttribute('aria-haspopup', 'dialog');
  await expect(about).not.toContainText('↗');
  await about.click();
  await expect(page.getByRole('dialog', { name: 'About ZameenRentals', exact: true })).toBeVisible();
  await expect(page.locator('[data-info-search]')).not.toContainText('↗');
  await page.keyboard.press('Escape');
  await page.locator('#siteMenuBtn').click();
  const tips = page.locator('#welcomeBtn');
  await expect(tips).not.toContainText('↗');
  await expect(tips).toHaveAttribute('aria-haspopup', 'dialog');
  await expect(tips.locator('[aria-hidden="true"]')).toHaveText('›');
  await tips.click();
  await expect(page.locator('#welcomeOverlay .welcome-panel')).toBeVisible();
});

test('page headers, footers and content links announce and open new tabs', async ({ page, context }) => {
  for (const path of ['/about', ...paths]) {
    await page.goto(path);
    for (const details of await page.locator('details').all()) await details.locator('summary').click();
    const links = page.locator('a[href^="/faq"], a[href^="/pricing"], a[href^="/privacy"], a[href^="/terms"]');
    for (const link of await links.all()) {
      await expect(link).toHaveAttribute('target', '_blank');
      await expect(link).toHaveAttribute('rel', /\bnoopener\b/);
      await expect(link).toHaveAccessibleName(/opens in a new tab/);
      await expect(link.locator('[aria-hidden="true"]')).toHaveText('↗');
      const href = await link.getAttribute('href');
      const opened = context.waitForEvent('page');
      await link.click();
      const tab = await opened;
      await tab.waitForURL(url => url.pathname + url.hash === href);
      await expect(tab.locator('main h1')).toBeVisible();
      expect(await tab.evaluate(() => window.opener === null)).toBe(true);
      await tab.close();
      expect(new URL(page.url()).pathname).toBe(path);
    }
    await expect(page.locator('.return-search')).not.toContainText('↗');
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  }
});

test('credit-sheet pricing and refunds open separately without closing the sheet', async ({ page, context }) => {
  await page.goto('/?city=lahore');
  await expect(page.locator('.card-wrap').first()).toBeVisible();
  await page.locator('#alertsBellBtn').click();
  await page.locator('#creditsTopUpBtn').click();
  for (const href of ['/pricing', '/terms#refunds']) {
    const link = page.locator(`#creditsSheet a[href="${href}"]`);
    await expect(link).toHaveAttribute('target', '_blank');
    await expect(link).toHaveAccessibleName(/opens in a new tab/);
    const opened = context.waitForEvent('page');
    await link.click();
    const tab = await opened;
    await tab.waitForURL(url => url.pathname + url.hash === href);
    expect(await tab.evaluate(() => window.opener === null)).toBe(true);
    await tab.close();
    await expect(page.locator('#creditsSheet')).toBeVisible();
  }
});
