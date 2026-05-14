// Ad-hoc verification script for the QA fix session. Runs against the
// local uvicorn server on :8000. Not part of the pytest/Playwright suites.
// Usage: node tools/qa_verify.mjs

import { chromium } from 'playwright';
import { mkdirSync } from 'fs';

const BASE = 'http://127.0.0.1:8000';
const OUT = 'tools/qa_verify_out';
mkdirSync(OUT, { recursive: true });

function ok(label) { console.log('  PASS', label); }
function fail(label, detail) { console.log('  FAIL', label, detail ? '— ' + detail : ''); process.exitCode = 1; }

async function withClearState(browser, viewport) {
  const ctx = await browser.newContext({ viewport });
  const page = await ctx.newPage();
  await page.goto(BASE);
  await page.evaluate(() => localStorage.clear());
  return { ctx, page };
}

async function withWelcomeDismissed(browser, viewport) {
  const ctx = await browser.newContext({
    viewport,
    storageState: {
      cookies: [],
      origins: [{ origin: BASE, localStorage: [{ name: 'zr_welcomed', value: '1' }] }],
    },
  });
  const page = await ctx.newPage();
  await page.goto(BASE, { waitUntil: 'networkidle' });
  // Wait until initWelcome wired the trigger (runs after initial doSearch).
  await page.waitForFunction(() => {
    const btn = document.querySelector('#welcomeBtn');
    return btn && document.querySelector('#welcomeOverlay');
  }, { timeout: 10000 });
  return { ctx, page };
}

async function verifyWelcome(browser, viewport, tag) {
  console.log(`\n[welcome modal] ${tag} ${viewport.width}x${viewport.height}`);
  const { ctx, page } = await withWelcomeDismissed(browser, viewport);

  // Click trigger
  await page.locator('#welcomeBtn').click();
  await page.waitForSelector('#welcomeClose', { state: 'visible' });

  // Title/aria-label check
  const titleAttr = await page.locator('#welcomeBtn').getAttribute('title');
  const ariaLabel = await page.locator('#welcomeBtn').getAttribute('aria-label');
  if (titleAttr === 'Welcome / Quick start') ok('trigger title renamed'); else fail('trigger title', titleAttr);
  if (ariaLabel === 'Welcome / Quick start') ok('trigger aria-label renamed'); else fail('trigger aria-label', ariaLabel);

  // Esc closes and returns focus
  await page.keyboard.press('Escape');
  await page.waitForTimeout(350);
  const focusedId = await page.evaluate(() => document.activeElement?.id);
  if (focusedId === 'welcomeBtn') ok('focus returned after Esc'); else fail('focus after Esc', focusedId);

  // Reopen, X click closes
  await page.locator('#welcomeBtn').click();
  await page.waitForSelector('#welcomeClose', { state: 'visible' });
  await page.locator('#welcomeClose').click();
  await page.waitForTimeout(350);
  const focusedId2 = await page.evaluate(() => document.activeElement?.id);
  if (focusedId2 === 'welcomeBtn') ok('focus returned after X click'); else fail('focus after X', focusedId2);

  // Reopen, wrapper (outside-the-card) click closes
  await page.locator('#welcomeBtn').click();
  await page.waitForSelector('#welcomeClose', { state: 'visible' });
  await page.locator('.welcome-wrapper').click({ position: { x: 10, y: 10 } });
  await page.waitForTimeout(350);
  const focusedId3 = await page.evaluate(() => document.activeElement?.id);
  if (focusedId3 === 'welcomeBtn') ok('focus returned after outside-card click'); else fail('focus after outside-card', focusedId3);

  await page.screenshot({ path: `${OUT}/welcome_${tag}_${viewport.width}.png` });
  await ctx.close();
}

(async () => {
  const browser = await chromium.launch();
  await verifyWelcome(browser, { width: 1440, height: 900 }, 'desktop');
  await verifyWelcome(browser, { width: 375, height: 812 }, 'mobile');
  await browser.close();
  if (process.exitCode) console.log('\nResult: FAILURES'); else console.log('\nResult: ALL PASS');
})();
