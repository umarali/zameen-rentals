// Headless Playwright driver for verify-zameenrentals. Invoke via drive.sh (pins Node 22).
// A steps file default-exports: async ({ page, expect, proof, api, url, log }) => { ... }
// It may live anywhere (scratchpad included): expect is injected, so it needs no imports.
import { readFileSync, readdirSync, statSync, mkdirSync, rmSync, writeFileSync } from "node:fs";
import { basename, dirname, join, resolve } from "node:path";
import { execSync } from "node:child_process";
import { pathToFileURL, fileURLToPath } from "node:url";
import * as pw from "@playwright/test";

const chromium = pw.chromium ?? pw.default?.chromium;
const expect = pw.expect ?? pw.default?.expect;
const args = process.argv.slice(2);
const flag = (name) => args.includes(name);
const opt = (name) => (args.includes(name) ? args[args.indexOf(name) + 1] : undefined);
const stepsPath = args.find((a, i) => !a.startsWith("--") && args[i - 1] !== "--run");
if (!stepsPath) {
  console.error("Usage: drive.sh <steps.mjs> [--mobile] [--run RUN_ID] [--fresh-user]");
  process.exit(2);
}

const root = execSync("git rev-parse --show-toplevel", { cwd: dirname(fileURLToPath(import.meta.url)) }).toString().trim();
const stateRoot = join(root, ".verify-artifacts", ".state");
let runId = opt("--run");
if (!runId) {
  const runs = readdirSync(stateRoot, { withFileTypes: true }).filter((d) => d.isDirectory())
    .map((d) => d.name).sort((a, b) => statSync(join(stateRoot, b)).mtimeMs - statSync(join(stateRoot, a)).mtimeMs);
  runId = runs[0];
}
if (!runId) { console.error("No live run; start one with launch.sh"); process.exit(1); }
const env = Object.fromEntries(readFileSync(join(stateRoot, runId, "env"), "utf8").trim().split("\n").map((l) => l.split("=")));
const url = env.VERIFY_URL;

const mobile = flag("--mobile");
const label = `${basename(stepsPath).replace(/\.m?js$/, "")}-${mobile ? "mobile" : "desktop"}`;
const outDir = join(env.VERIFY_EVIDENCE, label);
// A re-drive of the same recipe+viewport supersedes the previous attempt's evidence.
rmSync(outDir, { recursive: true, force: true });
mkdirSync(outDir, { recursive: true });

const record = { run: runId, url, label, steps: stepsPath, viewport: mobile ? "375x812" : "1440x900",
  startedAt: new Date().toISOString(), proofs: [], consoleErrors: [], pageErrors: [], failedRequests: [], apiErrors: [], ok: false };

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({
  baseURL: url,
  viewport: mobile ? { width: 375, height: 812 } : { width: 1440, height: 900 },
  serviceWorkers: "block",
  // Same pre-dismissal as playwright.config.js; --fresh-user drives the real first-run onboarding.
  storageState: flag("--fresh-user") ? undefined : { cookies: [], origins: [{ origin: url,
    localStorage: [{ name: "zr_welcomed", value: "1" }, { name: "zr_tour_done", value: "1" }] }] },
});
const page = await context.newPage();
page.on("console", (m) => m.type() === "error" && record.consoleErrors.push(m.text()));
page.on("pageerror", (e) => record.pageErrors.push(String(e)));
page.on("requestfailed", (r) => record.failedRequests.push(`${r.failure()?.errorText} ${r.url()}`));
page.on("response", (r) => r.url().startsWith(`${url}/api/`) && r.status() >= 400 && record.apiErrors.push(`${r.status()} ${r.url()}`));

let n = 0;
const proof = async (name, note = "") => {
  const stem = `${String(++n).padStart(2, "0")}-${name}`;
  // Let finite CSS transitions/animations (dropdown fades, chip colors) settle so the
  // screenshot shows the end state, not a half-faded frame. Capped at 3s.
  await page.evaluate(() => Promise.race([
    Promise.all(document.getAnimations()
      .filter((a) => a.playState === "running" && a.effect?.getComputedTiming().iterations !== Infinity)
      .map((a) => a.finished.catch(() => {}))),
    new Promise((r) => setTimeout(r, 3000)),
  ]));
  await page.screenshot({ path: join(outDir, `${stem}.png`) });
  writeFileSync(join(outDir, `${stem}.aria.yml`), await page.locator("body").ariaSnapshot());
  record.proofs.push({ stem, note, at: page.url() });
  console.log(`proof ${stem}${note ? ` — ${note}` : ""}`);
};
// Same-user API reads (favorites, alerts…) for side-effect proof: sends the page's X-Client-Id.
const api = async (path, init = {}) => {
  const clientId = await page.evaluate(() => localStorage.getItem("zr_client_id")).catch(() => null);
  const res = await fetch(new URL(path, url), { ...init,
    headers: { "Content-Type": "application/json", ...(clientId ? { "X-Client-Id": clientId } : {}), ...init.headers } });
  const body = await res.text();
  let json; try { json = JSON.parse(body); } catch { json = body; }
  return { status: res.status, json };
};
const log = (...m) => console.log(...m);

try {
  const steps = (await import(pathToFileURL(resolve(stepsPath)).href)).default;
  await page.goto("/");
  await steps({ page, expect, proof, api, url, log });
  record.ok = true;
} catch (e) {
  record.error = String(e?.stack || e);
  console.error(record.error);
  await page.screenshot({ path: join(outDir, "FAILED.png") }).catch(() => {});
} finally {
  record.finishedAt = new Date().toISOString();
  writeFileSync(join(outDir, "run.json"), JSON.stringify(record, null, 2));
  await browser.close();
}
const external = record.failedRequests.filter((r) => !r.includes(url));
console.log(`${record.ok ? "DRIVE OK" : "DRIVE FAILED"}  evidence: ${outDir}`);
console.log(`console errors: ${record.consoleErrors.length}  page errors: ${record.pageErrors.length}  api 4xx/5xx: ${record.apiErrors.length}  failed requests: ${record.failedRequests.length} (${external.length} external)`);
process.exit(record.ok ? 0 : 1);
