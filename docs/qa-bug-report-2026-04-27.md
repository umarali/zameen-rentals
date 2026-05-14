# QA Bug Report - Desktop Smoke Test

Website tested: https://zameenrentals.emerssive.com  
Test date: April 27, 2026  
Environment: Desktop, Chromium 130

This report consolidates the original issue log into deduplicated, dev-ready tickets. Two pairs were merged during cleanup:

- Original Issues 3 and 7 are combined into `BR-04` because they describe the same map accessibility problem.
- Original Issues 5 and 8 are combined into `BR-02` because the fragile post-reset behavior appears to be part of the same stale-state defect.

## Summary

| ID | Severity | Title | Likely code areas |
|---|---|---|---|
| BR-01 | High | Welcome modal can trap first-time users | `frontend/src/welcome.js` |
| BR-02 | High | `Clear All` resets chips but leaves stale search state | `frontend/src/filters.js`, `frontend/src/main.js`, `frontend/src/state.js` |
| BR-03 | Medium | Listing metadata renders as concatenated or malformed text | `frontend/src/cards.js`, `app/scraper.py`, `app/db_listings.py` |
| BR-04 | Medium | Map exposes many unlabeled interactive buttons | `frontend/src/map.js` and Leaflet-generated marker DOM |
| BR-05 | Medium | `Type` filter options are non-semantic chip elements | `frontend/index.html`, `frontend/src/filters.js` |
| BR-06 | Low | Natural-language parsing feedback can feel stalled | `frontend/src/main.js`, `app/parsing.py`, `app/routes.py` |

## BR-01: Welcome modal can trap first-time users

**Severity:** High

**User impact:** A first-visit user can be blocked before reaching the main experience.

**Repro:**

1. Open the site in a fresh browser profile or after clearing local storage.
2. Wait for the welcome modal to appear.
3. Try to dismiss it with `Explore on my own` or the close button.

**Expected:** The modal closes immediately and reliably.

**Actual:** The dismissal controls are reported as intermittently non-interactable, leaving the user stuck in the modal.

**Notes:**

- The original log mentioned a `missing location` symptom. If that came from automation tooling rather than the product UI, keep it in a separate debug note instead of the user-facing bug title.
- Because the overlay appears automatically, intermittent dismissal failures should be treated as a release-blocking onboarding issue.

**Suggested regression coverage:**

- Add a first-visit dismissal test that clears welcome state, opens `/`, dismisses the overlay, and asserts the listings UI becomes usable.

## BR-02: `Clear All` resets chips but leaves stale search state

**Severity:** High

**User impact:** The UI appears reset, but results, title, counts, and rendered cards remain out of sync with filter state.

**Repro:**

1. Open the site.
2. Run the query `3 bed house Bahria Town under 80k`.
3. Click `Clear All`.

**Expected:**

- Area, type, beds, price, and other filters reset fully.
- URL/query state resets.
- Listings title and result count return to the default browse state.
- Cards remain fully rendered and consistent with the cleared state.

**Actual:**

- Filter chips reset to defaults such as `Area`, `Type`, `Beds`, and `Price`.
- The title remains `Rentals in Bahria Town`.
- The count remains `41 total in this area`.
- Listing rendering becomes inconsistent, including an empty visible card container.
- Subsequent map interactions are likely to make the UI, URL, and result state diverge further.

**Notes:**

- Current automated coverage in [`tests/filters.spec.js`](/Users/umarali/Workspace/MVPs/zameenrental/tests/filters.spec.js:277) only checks that chip state resets. It does not assert URL reset, header reset, or stable card rendering.
- This looks like a state synchronization problem rather than a pure styling issue.

**Suggested regression coverage:**

- Extend the existing `Clear All` test to assert:
  - query params are removed
  - the title and count return to a default browse state
  - at least one visible card still renders valid content after reset
  - map and list remain in the same mode after reset

## BR-03: Listing metadata renders as concatenated or malformed text

**Severity:** Medium

**Example observed:** `Garden Town - Abu Bakar Block, Garden Town551 Kanal`

**Expected:** Location and size metadata render with correct separators, spacing, and ordering.

**Actual:** Location and area text can appear concatenated without spacing, with units such as `Kanal` appended incorrectly.

**Notes:**

- [`frontend/src/cards.js`](/Users/umarali/Workspace/MVPs/zameenrental/frontend/src/cards.js:87) renders location and area size as separate UI elements, so the malformed string may already be arriving from the scraped or cached listing data rather than being introduced only by card layout.
- Triage should check both frontend rendering and backend normalization before narrowing ownership.

**Suggested regression coverage:**

- Add a fixture-based rendering test for cards with representative Lahore data to confirm that location and area size remain distinct and readable.

## BR-04: Map exposes many unlabeled interactive buttons

**Severity:** Medium

**User impact:** Screen readers and keyboard users may encounter large numbers of unnamed controls; automation against the map also becomes brittle.

**Observed behavior:**

- The map exposes large sets of interactive elements with `role="button"` and no clear accessible name.
- Zooming changes marker density, but unlabeled button elements still persist.

**Expected:** Marker and map interactions should expose meaningful accessible names, or decorative elements should be hidden from assistive technology.

**Actual:** Numerous unlabeled interactive elements remain present in the map DOM.

**Notes:**

- This ticket intentionally combines the original unlabeled-button and post-zoom observations because they describe the same underlying accessibility problem.
- Root cause may be custom marker markup, Leaflet-generated interactive containers, or both.

**Suggested regression coverage:**

- Add a Playwright accessibility smoke check that counts unnamed interactive elements inside the map container before and after zoom.

## BR-05: `Type` filter options are non-semantic chip elements

**Severity:** Medium

**User impact:** Keyboard, screen-reader, and automation interactions are less reliable than they should be.

**Repro:**

1. Open the `Type` filter dropdown.
2. Inspect the option markup or try to navigate/filter using keyboard-only controls.

**Expected:** Each property type option should be a native interactive element such as `button`, `input`, or a well-formed ARIA option pattern.

**Actual:** The options are rendered as `span.chip` elements inside `#typeGrid`, with click handling attached at the container level.

**Notes:**

- This is a confirmed DOM issue in the current markup at [`frontend/index.html`](/Users/umarali/Workspace/MVPs/zameenrental/frontend/index.html:125).
- The same pattern may exist in other chip groups, but this ticket is scoped to the `Type` filter because that was the observed defect.

**Suggested regression coverage:**

- Add a DOM/accessibility assertion that each `Type` option is reachable and activatable via keyboard, not only pointer clicks.

## BR-06: Natural-language parsing feedback can feel stalled

**Severity:** Low

**User impact:** The search box appears to pause while the query is being parsed, which can make the product feel frozen even when it is still working.

**Repro:**

1. Enter a natural-language query such as `3 bed house Bahria Town under 80k`.
2. Submit the query and observe the `Parsing filters...` state.

**Expected:** Immediate responsive feedback with predictable progress timing.

**Actual:** The parsing indicator is visible, but the wait can feel longer than expected before results update.

**Notes:**

- The current UI in [`frontend/src/main.js`](/Users/umarali/Workspace/MVPs/zameenrental/frontend/src/main.js:913) does show a spinner and status text, so this is more of a responsiveness/perceived-latency issue than a missing-feedback issue.
- Before closing or reprioritizing this ticket, capture actual parse timings so the team can distinguish UX polish from backend latency.

**Suggested regression coverage:**

- Record client-side timing for `/api/parse-query` and track p50/p95 latency in QA or analytics before making a product decision.

## Positive Validation

- Query `3 bed house Bahria Town under 80k` returned a top result that matched Zameen.com listing ID `53890161` for price, beds, location, and destination link.
- This is useful to preserve in the ticket set because it shows the core search/linking flow can be correct even while state-reset and accessibility issues remain open.
