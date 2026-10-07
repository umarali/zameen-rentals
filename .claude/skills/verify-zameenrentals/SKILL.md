---
name: verify-zameenrentals
description: "Launch a disposable ZameenRentals instance (seeded SQLite, no scraping, no Claude) and drive the web UI headlessly with Playwright to prove a change works the way a renter would see it: search, filters, listing drawer, map, favorites/alerts. Use after any frontend/ or app/ change that affects what users see, before claiming it works."
---

# Verify ZameenRentals

Proves user-visible behavior of the web UI (primary surface) and its `/api/*` JSON (secondary). Everything runs locally against a throwaway instance: `tests/serve_playwright.py` seeds fixture listings into a temp DB and sets `ZAMEENRENTALS_PLAYWRIGHT=1`, which disables live Zameen.com scraping, the Claude query parser (regex only), and rate limits. Nothing touches production data or the user's own servers.

All helpers live in `.claude/skills/verify-zameenrentals/scripts/` and run from any directory. Each Bash call is a fresh shell, so scripts find the live run themselves (newest under `.verify-artifacts/.state/`); pass a `RUN_ID` to target a specific one.

## Launch

```bash
S=.claude/skills/verify-zameenrentals/scripts
$S/launch.sh                      # → READY run=<RUN_ID> url=http://127.0.0.1:<port> pid=<pid>
```

- Picks the first free port in 8300–8399. `VERIFY_PORT=8323 $S/launch.sh` pins one and **refuses** if it's taken. Stay off 8000 and 5173 (the user's own uvicorn and Vite) and off 8100 and 8200 (Playwright ports used by other sessions' worktrees). Never kill any of them.
- Needs `node_modules/`. In a fresh git worktree, run `npm ci` there once (or symlink the main checkout's `node_modules`).
- The server serves the built `static/`, not `frontend/`. If any `frontend/` file is newer than `static/index.html`, or the bundle it references is missing (always true in a fresh worktree), launch runs `npm run build` first. That rewrites tracked `static/index.html`, which is the normal workflow here. `VERIFY_SKIP_BUILD=1` skips the build and warns that you're proving a stale build.
- Ready means `/api/health` answers. Launch waits for it, or prints the server log tail and exits 1.
- Several instances can run side by side: each has its own port and temp DB.
- Teardown: see Cleanup.

## Doctor

```bash
$S/doctor.sh [RUN_ID]             # read-only; ends with DOCTOR OK or DOCTOR FAILED
```

Checks that:
- the PID is our `serve_playwright.py`
- the port's listener is that PID
- `/api/health` is ok
- `/api/cities` lists karachi, lahore and islamabad
- Karachi/Clifton search returns fixture IDs (`99…`), proving this is the disposable DB
- the built JS bundle is served

Run it before the first drive, after any failed drive, and whenever something looks off. If it fails, read `.verify-artifacts/.state/<RUN_ID>/server.log`, clean up, and relaunch. Don't drive a sick instance.

## Drive

```bash
$S/drive.sh <steps.mjs> [--mobile] [--run RUN_ID] [--fresh-user]
```

Headless Chromium (Playwright 1.58.2 under Node 22, both pinned by the script) opens the app with onboarding already dismissed (`zr_welcomed`, `zr_tour_done`) and service workers blocked, the same as `playwright.config.js`.

- `--mobile` uses a 375×812 viewport. The default is 1440×900.
- `--fresh-user` drives the real first-run welcome strip and Driver.js tour.

A steps file can live anywhere (the scratchpad is fine) and needs no imports:

```js
export default async ({ page, expect, proof, api, url, log }) => {
  await page.locator(".card-wrap").first().waitFor();          // app loaded
  await page.locator('.city-tab[data-city="karachi"]').click();
  await proof("karachi", "city switched");                      // screenshot + ARIA snapshot
  const { status, json } = await api("/api/favorites");         // same-user API read (sends X-Client-Id)
};
```

- `page` starts at `/`. `expect` is Playwright's (web-first, auto-retrying).
- `proof(name, note)` waits up to 3s for running CSS transitions to finish (dropdown fades and chip colors otherwise leave ghost frames), then writes `NN-name.png` and `NN-name.aria.yml`.
- `api(path, init)` calls the instance with the page's `zr_client_id`, so personalization reads see this browser's favorites and alerts.
- A thrown error marks the drive failed and saves `FAILED.png`.

Ready-made recipes live in `steps/`. `steps/filters.mjs` is proven at both viewports. Per-feature recipes, entry points and gotchas are in `features/README.md`; read it before driving and use the matching feature file.

Prefer stable handles: element IDs (`#nlInput`, `#areaChip`, `#drawer`), data attributes (`.city-tab[data-city]`, `#typeGrid .chip[data-type]`, `[data-action="favorite"]`, `[data-chip-remove]`), and state classes (`has-value`, `active`, `drawer-open`). Avoid coordinates and nth-child.

## Evidence

Everything goes to `.verify-artifacts/<RUN_ID>/<recipe>-<desktop|mobile>/`, which is gitignored and survives cleanup:
- numbered `.png` and `.aria.yml` per `proof()`
- `run.json` with the proof list, console errors, page errors, `/api` 4xx/5xx responses, and failed requests
- `server.log`, copied at cleanup

Re-driving the same recipe at the same viewport replaces that folder.

Proof standards:
- Drive the real user path: click the chip, type in the box. Never set `S`/`refs` state or call internal functions to fake a step.
- Capture the action **and** the resulting state: a proof before and after, not just the final screen.
- Verify side effects through a second view: `api()` reads (`/api/favorites`, `/api/alerts`, `/api/search`) or persisted state (`localStorage.rk_s` for filters, `zr_*` for personalization), alongside what's visible.
- `run.json` must show 0 console errors, 0 page errors and 0 `/api` errors. Failed requests to `tile.openstreetmap.org` / `arcgisonline.com` are map tiles cancelled on pan/zoom and are harmless. Any failed request to the instance URL is a real problem.
- Test mode is not production. It skips Zameen.com scraping (search falls back to seeded rows; contact lookups return null phones) and the Claude parser (regex only). A change in those paths needs `pytest`-level proof (`tests/test_scraper.py`, `tests/test_parsing.py`), not this skill. Say so instead of claiming UI proof.
- Look at the screenshots before reporting. A passing `expect` with a broken layout is not proof.

## Cleanup

```bash
$S/cleanup.sh [RUN_ID]            # or --all for residue from failed iterations
```

- Sends SIGTERM to the recorded PID only, after checking it's still `serve_playwright.py`. If it hangs, it sends SIGKILL to that same PID. It never kills by name or port.
- Deletes the temp DB dir that PID held open. uvicorn re-raises SIGTERM, so `serve_playwright.py` never cleans up its own `TemporaryDirectory`.
- Copies `server.log` into the evidence folder and removes the state dir.
- Reports that the port is free and the evidence was kept.

Run it after every failed iteration too, so no strays are left behind.

## Helpers

| Script | Invocation | What it does |
| --- | --- | --- |
| `scripts/launch.sh` | `VERIFY_PORT=… VERIFY_SKIP_BUILD=1 launch.sh` (both optional) | Rebuild if stale, start the seeded instance, wait for health |
| `scripts/doctor.sh` | `doctor.sh [RUN_ID]` | Read-only health and identity checks |
| `scripts/drive.sh` | `drive.sh <steps.mjs> [--mobile] [--run ID] [--fresh-user]` | Headless Playwright run that writes evidence (wraps `drive.mjs`) |
| `scripts/cleanup.sh` | `cleanup.sh [RUN_ID \| --all]` | Kill only our PID, delete its temp DB, keep evidence |
| `steps/*.mjs` | `drive.sh .claude/skills/verify-zameenrentals/steps/filters.mjs` | Proven recipes |

Missing browser? `drive.sh` needs `~/Library/Caches/ms-playwright/chromium_headless_shell-1208`. `npx playwright install --only-shell chromium` installs it but **garbage-collects other Playwright versions' browsers**, so ask the user first.

Keeping this skill honest as the app changes: `/maintain-verification-skill`.
