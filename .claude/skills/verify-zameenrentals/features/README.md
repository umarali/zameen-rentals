# ZameenRentals verification map

This directory is the maintained source for verifying what renters see in ZameenRentals. Read this index before driving the app, then use the matching feature file as the recipe. Harness details (launch, doctor, drive, cleanup) are in `../SKILL.md`.

## Baseline preconditions

- A disposable instance from `scripts/launch.sh` is running, and `scripts/doctor.sh` printed `DOCTOR OK`.
- Seeded data. Each area below has 12 listings of each type (`apartment`, `house`, `upper_portion`), with IDs `99000001+`, titled `Furnished <type> <id>`, priced from PKR 25,000 in 5,000 steps, and with 1–4 beds. A third of them carry an exact map pin.
  - Karachi: `DHA Defence`, `Clifton`, `Gulshan-e-Iqbal`
  - Lahore: `DHA Defence`, `Gulberg`, `Bahria Town`, `DHA 11 Rahbar`, `Bahria Nasheman Iris`
  - Islamabad: `F 10`, `G 11`, `Bahria Town`
- The app opens on **Lahore** (`S.city` defaults to `lahore`).
- Onboarding is pre-dismissed unless the drive uses `--fresh-user`.
- Never drive an instance this verification run didn't start.

## Driving conventions

- Every recipe is a steps file run with `scripts/drive.sh <steps.mjs> [--mobile]`. Code shown in feature files belongs inside the steps function, where `page`, `expect`, `proof` and `api` are in scope.
- Start each recipe from `/` with `await page.locator(".card-wrap").first().waitFor()`.
- Switch to Karachi first when a recipe uses Karachi areas.
- Prefer IDs, data attributes and state classes (`has-value`, `active`, `drawer-open`, `hidden`). Never use coordinates.
- Wait on web-first `expect` conditions, never on fixed sleeps.
- Each drive gets a fresh browser context, so personalization state (`zr_client_id`) starts empty every time.

## Proof and skip reporting

- Capture the user action and the resulting state with `proof()` before and after the key step.
- UI proof is the PNG plus the ARIA snapshot that `proof()` writes. Look at the PNG.
- A mutation (favorite, hide, alert) needs a second, read-only view: an `api()` read or a reopened panel.
- `run.json` must show 0 console errors, 0 page errors and 0 `/api` errors. Failed map-tile requests are harmless.
- Record the feature file and the entry point used. If an entry point can't be reached, report the attempted step and the unmet precondition. Don't count a skipped entry point as verified through a different one.
- Test mode doesn't exercise live scraping, contact lookups or the Claude parser. Report those as outside this map's reach.

## Feature entry contract

Each feature file starts with an H1 and one paragraph describing the user-visible behavior. It then has exactly four H2s, in this order:

1. `Sub-features`: short IDs, one line each.
2. `How to get to it (user POV)`: every user entry point.
3. `Driving it with drive.sh`: starts with `Preconditions:`, then labeled bullets that pair each user action with exact steps code and the observable result.
4. `Gotchas`: traps that waste or invalidate a run.

Keep implementation details out of the map. Name only user paths, stable handles, required state, code and observable proof.

## Features

- [Filters](./filters.md): city tabs, area autocomplete, type, beds, price, size, more/sort, clear all. Proven recipe: `../steps/filters.mjs`.
- [Natural-language search](./natural-language-search.md): typed queries, example suggestions, "Understood:" chips, approximate-match notice.
- [Listing drawer](./listing-drawer.md): card → detail drawer, photo gallery, nearby areas, close paths.
- [Map](./map.md): desktop map panel, mobile map overlay, coverage badge, layers, area markers and exact pins.
- [Personalization](./personalization.md): favorites, hiding listings, save-search alerts, the My rentals panel.
