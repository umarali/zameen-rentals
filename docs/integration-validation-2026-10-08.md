# Four-branch integration

Combines PR #22, English/Urdu search and Claude request lifecycle; #14, Jev tags and evaluation; #19, keyboard accessibility and card readability; and #2, mobile layout improvements.

The older mobile branch predates favorites, comparison actions, the current map coverage controls, voice status messages and the full-height mobile drawer. Conflict resolution preserves those newer behaviors, readable card text, accessible button labels and the current swipe implementation. Compatible mobile changes add larger gallery controls, safe-area spacing, larger filter inputs and touch targets, bounded search suggestions and larger map cards. Generated static HTML comes from a fresh Vite build.

## Test plan

- Run the full Python suite on the combined tree with disposable databases and the live Claude key disabled. This covers search parsing, area reconciliation, provider failures, Jev response validation, stale-tag invalidation, migrations and APIs.
- Build the frontend and run every Playwright spec headlessly on desktop and mobile. Check filters, drawer/gallery, map, voice failure recovery, personalization, search and responsive layouts.
- Verify all four PR head commits are ancestors of the integrated commit and the remote main has not advanced before pushing.
- Do not include uncommitted nearby-map work from the original workspace.

The Python suite passed 783 tests with two optional transcription tests skipped. The first browser run exposed two bugs: city state was saved only after async area lookups, and the floating Feedback button covered mobile filter choices. City selection now saves synchronously, with a delayed-lookup regression test; the Feedback button now sits below filter overlays. The city and language checks passed all 32 cases after the fix. The final full Playwright run passed 430 tests, with 20 skips and retries disabled. The focused overlay/filter/responsive run passed 138 tests. The production build passed. No live provider accuracy benchmark or production deployment is part of this merge.

## Urdu area coverage

The explicit fallback aliases resolve 68 of 366 Karachi area names, 11 of 463 Lahore names and 35 of 304 Islamabad names. These are dictionary coverage counts, not measured AI accuracy or the share of real user searches supported. Many unmapped names are sub-areas.

The picker has a separate matching path: `/api/areas` exposes Urdu labels only for Karachi, `/api/search-areas` compares the query with English names, and the frontend uses the single `name_ur` display label rather than all parser aliases. For example, the parser recognizes `گلبرگ` in Lahore and `ایف ۱۰` in Islamabad, but the picker lacks those labels. `والنسیا ٹاؤن` in Lahore supplies no area candidates and the regex parser returns no area.

Recommendation: retain English and Urdu query input and keep canonical area names/IDs as the stored filter values. English display names are a suitable default wherever reviewed Urdu labels are missing. Use one city-scoped alias registry across the parser, API search and picker, including spelling variants and sub-area qualifiers. Expand that registry against the actual area inventory with Urdu-speaker review, and test each alias against its intended area. Claude can draft aliases offline, but generated translations should not become accepted mappings without review. When a requested place is unresolved, show a clarification or area picker instead of silently treating the query as city-wide.

This merge retains existing language support. Full Urdu coverage and the shared picker registry remain follow-up work.
