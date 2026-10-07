# Product, UX, and Learning Backlog

Date: 2026-05-15

This document itemizes possible features, fixes, and enhancements for ZameenRentals after a strict UI/UX and product review. It is intentionally written as a planning backlog: each item should be small enough to discuss, scope, and turn into an issue.

---

## Audience-grounded review — proposal for discussion (reviewed 2026-06-02)

_Re-reviewed against the real audience (mobile-first renters on scraped Zameen data, low current traffic, single-dev open-source MVP) and the live database. This section is a **proposal to review, not a locked plan.** The detailed lists below are kept; shipped items are checked off, and the priority section at the bottom is replaced by this review._

### Verified data realities (these drive every call below)

- **52,829 active listings — 0 marked inactive**, and the newest `last_seen_at` in the DB snapshot is ~3 weeks old. ⚠️ **Prerequisite:** confirm the production crawler + `mark_stale_listings` are actually running. Until they are, any "new today / last seen" UI is empty or screams *"everything here is stale"* — shipping freshness UI first would **erode** trust, not build it.
- **~28% of active listings are reposts** (15,045 listings across 4,645 `content_hash` groups). Collapsing duplicates is the single most visible quality win, and the `content_hash` primitive already exists.
- **~33% of listings have no phone number** (67% do). A "phone available" badge lets renters spend taps on contactable listings — but label it **agent contact**, never "owner".
- **~34% of listings are geocoded to area-centroid**, not exact. This is why landmark/commute search ("near LUMS") and commute-radius overlays are a **trap right now** — a third of results would show confident-but-wrong distances.
- **Low traffic** means anything that *learns* from aggregate behaviour (popularity, learned ranking) has almost no signal yet and will overfit/mislead.

### Verified in code (2026-06-02) — what's already there

These were checked in the backend so the effort estimates below are real, not guessed:

- **Search returns everything**: `search_listings` runs `SELECT *` ([db_listings.py:619](../app/db_listings.py)), so `call_phone`/`whatsapp_phone`, `last_seen_at`, `location_source`, `content_hash`, `detail_images_json` are **already in each result** → dedup, freshness buckets, and the phone/confidence badges are **front-end-only** work.
- **Default sort is already freshness** (`_FRESHNESS_SQL = COALESCE(zameen_updated_at, zameen_posted_at, first_seen_at) DESC`) → "Default → Fresh first" is literally true, and rule-based quality ranking is a small `ORDER BY` extension.
- **`size_marla_min/max` is already a `/api/search` param** → the marla filter is UI-only.
- **`search_listings` already accepts `area_names` (plural)** → the multi-area *query layer* exists; only the endpoint param + NL parser ("DHA or Gulberg") + UI are missing.
- **`resolve_landmark` already maps a landmark → its area** (coarse, longest-match) → "near LUMS" already returns DHA-area results; what's missing/risky is *precise distance/radius* on 34% centroid coords — so keep landmark as a soft hint, don't build radius overlays.
- **`content_hash = hash(price, title, bedrooms, bathrooms, area_size)`** → it's **title-sensitive**, so collapsing by it catches *exact* reposts (~28%) but misses reposts with edited titles; a stronger fingerprint (price+area+beds+size, ignoring title, or `detail_hash` on phone+coords) catches more.
- **`mark_stale_listings(days=7)` exists and is called by the crawler** ([crawler.py:532](../app/crawler.py)) → the prerequisite is *confirming the crawler runs in production*, not building stale-marking.
- **`search_history.result_count` already logs zero-result searches** → that half of the "events table" is done; the real gaps are failed-parse logging + server-side contact-intent.
- **No first-party `events`/`impressions` table exists** → contact-intent lives only in client-side PostHog today.

### Already shipped (drop from "to build")

- **Personalization:** saved-search alerts + web push, favorites, hidden, recently viewed, "new since last visit", accountless persistence (`zr_client_id`).
- **Compare:** decision tool — transposed diff table, Rs/marla + Rs/bedroom, winner badges, in-modal call/WhatsApp, bigger images, scrollable.
- **Onboarding:** non-blocking intent strip, restructured help modal (one primary action, no implicit geolocation, city-aware examples), first-run guided tour (Driver.js).
- **Icons:** unified shared icon system. **Tracking:** client-side contact-intent. **Cards:** "New" freshness badge.

### Proposed priority (consequence-aware)

**Build now — cheap, on data that already exists, directly on the funnel**
- **Collapse duplicate reposts** — `content_hash` is already in every search result; group by it to turn "same flat ×6" into one card. Catches *exact* reposts (~28%); for the title-edited ones, add a looser fingerprint (price+area+beds+size) as a fast-follow. _S–M._
- **Copy relabels** — "Default" → "Fresh first", "Map Coverage" → "Areas on map", clarify/hide "Local only". Makes the already-built freshness sort legible = perceived trust. _S._
- **Zero-result recovery** (drop budget / widen area / nearby) **+ editable parsed-NL chips + "Did you mean" + expose the marla filter.** Rescues the #1 abandonment moment for a budget, Roman-Urdu-typing renter; "Did you mean" and the marla filter are near-free (backend already returns `area_approximate` / accepts `size_marla`). _S–M._
- **Filters & presets** — budget presets from real per-city price distribution (**exclude "price on request"**), property-type + bedroom as **tap chips** (not dual-thumb sliders), client-side min>max validation. _S._
- **"Phone available" confidence badge** — 67% have a number; flag them so taps land on contactable listings (labelled *agent contact*). _S._
- **Deterministic quality ranking** (rule-based only) — fresh + contactable + has-photos + complete up; stale/duplicate/photo-less down. Signals already stored; no "learning". _S._

**Build next**
- **Confirm the crawler is running in production (it already calls `mark_stale_listings(days=7)`), then ship freshness buckets & soft stale warnings.** Only after the crawler is verified live — the function exists, so this is an ops check, not a build. Lead with positive "seen today"; soft "last seen 3 weeks ago — confirm before visiting", never punitive. _S (ops check) + S (UI)._
- **Structured report-issue types** (wrong price / wrong area / already rented / duplicate). Turns renters into a free data-quality sensor; "already rented" is ground truth you can't auto-detect. _S._
- **Thin first-party events table** — zero-result searches are *already* in `search_history.result_count`; add failed-parse logging + server-side contact-intent by channel (today it's PostHog-only). The cure for "low traffic = no signal" and the prerequisite for any future learning. **Log only — no dashboards/weekly report yet.** _S–M._
- **Share a listing via WhatsApp** — rental decisions here are WhatsApp/family decisions; near-free viral loop. Pair with the freshness badge so a shared-then-rented link doesn't burn the sharer. _S._

**Later**
- "More in this area" / "similar" in the drawer — **only after dedup**, else it surfaces reposts.
- Multi-area search ("DHA or Gulberg under 80k") — the query layer already accepts `area_names` (plural); remaining work is the `/api/search` param + NL "OR" parsing + UI. Could be pulled forward since the hard part is done.
- Map: pin clustering (once an area is dense), "Search this map area" button, map-mode indicator.
- Solo-dev ops views (read-only): crawl coverage/freshness, top zero-result queries, duplicate review — **as scrappy SQL-backed pages, not an admin app.**
- a11y plumbing (ARIA live regions, bottom-sheet focus traps) as steady work.

**Reconsider / skip for now (looks good on paper, hurts this audience today)**
- **Learned/behavioural ranking** — "popular in this area", learned area/budget prefs, "similar to viewed": no traffic to learn from → overfits to a handful of clicks and misleads; also amplifies dupes. Revisit once the events table has volume.
- **"Good value for area" badge** — layers a judgment on noisy Rs/marla + centroid sizes; would flag misparsed outliers as "deals" to the exact budget renters who'd trust it.
- **Precise landmark/commute distance + commute-radius overlays** — basic landmark→area already works (`resolve_landmark`), so keep that soft hint; but drawing radii / "X km from LUMS" on 34% centroid coords gives confident-but-wrong distances and erodes trust more than no result.
- **Compare extras** — weighted fit-score (false precision on noisy data), mini-map, persisted compare tab. (A shareable `?compare=` link can ride the WhatsApp-share work.)
- **Analytics dashboards / weekly auto-report / impressions-by-position** — vanity at this traffic; log raw events and query them.
- **Property-type presets that duplicate the existing type filter**; **dual-thumb bedroom range slider** (use tap chips instead).
- **Polished admin CRUD** (alias-management screens, triage boards) — scripts until volume justifies a UI.
- **Any shareable link before dedup/freshness ship** — a shared dead listing damages credibility on a surface whose timing you don't control.

### Genuine cross-lens tensions (resolved)
- **Analytics:** data-quality lens said "build now" (you can't learn until you log); others said "later". → Build the **thin events table now**, defer dashboards.
- **Sharing:** conversion/mobile said "build now" (viral loop); data-quality said "later" (stale-link liability). → Build it, but **after/with** the freshness badge.
- **Freshness UI:** high value, but **sequenced behind** confirming the crawler — otherwise it's empty or alarming.

---

## Product Positioning

- [ ] Make the first-run promise explicit: "Fresh Lahore rentals first, refine by area, budget, or natural language."
- [ ] Keep Lahore as the stable no-state default across frontend, backend, cached shell, and tests.
- [ ] Avoid silent city switching. Use stored city, URL city, or explicit user choice only.
- [ ] Treat map search as an exploration mode, not the default landing state.
- [ ] Add a short empty-state explanation that distinguishes "no matching rentals" from "data unavailable" from "map coverage unavailable."
- [ ] Add a lightweight "data freshness" note near results, using crawl status rather than a generic live-data banner.

## Search Experience

- [ ] Make natural-language search the primary affordance visually, with filters as supporting controls.
- [ ] Keep parsed NL filters visible as editable chips instead of briefly showing parsed text and hiding it.
- [ ] Add a "Did you mean..." state for approximate area matches.
- [ ] Add zero-result recovery suggestions: remove budget, widen area, switch property type, or show nearby areas.
- [ ] Add query examples based on current city and inventory availability.
- [ ] Support multi-area searches, such as "DHA or Gulberg under 80k."
- [ ] Support landmark/commute searches, such as "near LUMS", "near Emporium", "near Blue Area."
- [ ] Support size filters in the visible UI, since backend already accepts marla ranges.
- [ ] Add "recently added" as a visible default-sort label instead of the vague "Default."
- [ ] Add a clear difference between city browse, area search, map viewport search, and nearby search.
- [ ] Preserve the user's last successful query separately from the current input text.
- [ ] Add typo-tolerant search for Lahore and Islamabad area aliases, not only Karachi/Roman Urdu.

## Filters

- [ ] Replace "More" with a clearer label when active, such as "Furnished" or "Sort: Newest."
- [ ] Add active filter count on mobile when chips overflow horizontally.
- [ ] Add common Lahore-specific presets, not generic global presets only.
- [ ] Add budget presets based on actual city price distribution.
- [ ] Add property-type presets that match local rental behavior: portion, apartment, full house, room.
- [ ] Add "clear this filter" affordances that are large enough for mobile.
- [ ] Validate custom price ranges client-side before calling the API.
- [ ] Add min/max bedroom range UI if `bedrooms_max` remains supported.
- [ ] Persist last used filters only after successful searches, not every transient state.

## Listings And Cards

- [x] Add favorite/save listing. _(shipped)_
- [x] Add hide/dismiss listing. _(shipped)_
- [x] Add compare shortlist. _(shipped — now a full decision tool)_
- [ ] Add share listing and share search. _(build now: share-a-listing via WhatsApp)_
- [x] Add "seen before" / "new since last visit" markers. _(shipped: "New" badge)_
- [ ] Add confidence badges: exact location, approximate area, phone available, recently seen.
- [ ] Add stale-listing warnings based on `last_seen_at` and crawl freshness.
- [ ] Add duplicate detection across reposted or repeated listings.
- [ ] Show agent/agency only when known and useful.
- [ ] Add one-tap WhatsApp/call states that show when contact is being fetched.
- [ ] Track and display whether contact information was available locally or had to be fetched live.
- [ ] Add "open on Zameen" as a secondary action, not the primary conversion path.
- [ ] Improve photo fallback so no-image cards do not feel broken.
- [ ] Add skeleton/error states that preserve layout and explain what is happening.

## Detail Drawer

- [ ] Add save, hide, share, call, and WhatsApp actions in a persistent drawer action bar.
- [ ] Add "similar listings" at the bottom of the drawer.
- [ ] Add "more in this area" action from the drawer location section.
- [ ] Add exact/approximate map-location explanation.
- [ ] Add expandable property facts table with amenities and features.
- [ ] Add photo gallery analytics: image count, gallery open, next/prev, time in drawer.
- [ ] Add report-listing issue types: wrong price, wrong area, inactive, duplicate, bad photos, bad contact.

## Map Experience

- [ ] Keep default landing in city-browse mode; enter viewport search only after explicit map movement/zoom.
- [ ] Add a clear "Search this map area" button instead of automatically firing map searches on every viewport change.
- [ ] Show current map mode: "Browsing Lahore", "Searching this map view", or "Near me."
- [ ] Explain area-count badges and coverage badges in plain product language.
- [ ] Add visible recovery when map search fails: "Showing Lahore results instead."
- [ ] Add map/list sync polish: selected card highlights marker and selected marker scrolls card into view.
- [ ] Add clustering for exact listing pins when density grows.
- [ ] Add commute radius/time overlays for landmarks.
- [ ] Add saved map viewport as part of saved searches.

## Mobile UX

- [ ] Reduce first-screen vertical clutter: header, info banner, filters, list title, map button compete for space.
- [ ] Make filter drawers feel native on mobile with full-width bottom sheets and sticky apply/clear actions.
- [ ] Keep the map FAB away from card contact actions and feedback button.
- [ ] Consider a segmented List/Map control instead of a floating map button.
- [ ] Add bottom navigation only if saved searches/favorites become core flows.
- [ ] Ensure dropdown open tests and mobile click targets are robust; current mobile tests expose intermittent card-load timing issues.

## Onboarding

- [x] Make welcome overlay optional and less intrusive for returning users. _(shipped: non-blocking strip + on-demand modal + guided tour)_
- [x] Use the welcome overlay to ask intent: "budget apartment", "family home", "near me", "specific area." _(shipped: intent strip + modal example chips)_
- [x] Do not request geolocation implicitly from onboarding. _(shipped)_
- [ ] If city detection is desired, ask explicitly: "Use my location to choose city?"
- [ ] Track which onboarding cards lead to searches, listing opens, and contact intent. _(partial — basic tracking only)_
- [x] Replace generic quick-start cards with city-aware presets. _(shipped: city-aware NL example chips)_

## Trust And Data Quality

- [ ] Add last crawl time per city and per area.
- [ ] Add listing freshness buckets: new today, seen this week, older.
- [ ] Add stale result handling when live scrape fails.
- [ ] Add area coverage score and show low-coverage caveats.
- [ ] Add "phone verified recently" or "contact unavailable" states.
- [ ] Add duplicate/stale listing reporting and feed it into ranking.
- [ ] Add admin/data dashboard for crawl failures, empty areas, stale areas, and contact fetch rates.
- [ ] Add source transparency in a quieter place than the first-run info banner.

## Personalization And Retention

- [x] Saved searches. _(shipped)_
- [x] Search alerts by city, area, price, beds, type, and freshness. _(shipped)_
- [x] Favorite listings. _(shipped)_
- [x] Hidden listings. _(shipped)_
- [x] Recently viewed listings. _(shipped)_
- [x] "New since your last visit" view. _(shipped)_
- [x] Browser push notifications for saved searches. _(shipped, web push)_
- [ ] Email/WhatsApp alerts if appropriate for the user base.
- [ ] Persist preferred city and common budget/type from actual behavior. _(learned — deferred, needs traffic)_
- [x] Add lightweight accountless persistence first; account system can come later. _(shipped, `zr_client_id`)_

## Ranking And Recommendations

- [ ] Rank default city results by freshness, contact availability, image quality, and data completeness.
- [ ] Boost listings users open/contact more often, normalized by position.
- [ ] Down-rank stale, duplicate, photo-less, or repeatedly hidden listings.
- [ ] Add "similar to saved/opened listings."
- [ ] Add "popular in this area" and "good value for area" modules.
- [ ] Learn preferred areas from repeated searches and listing opens.
- [ ] Learn preferred budget/type from contact intent, not just searches.
- [ ] Use zero-result queries to identify missing area aliases and crawl gaps.

## Analytics And Learning

- [ ] Ensure PostHog env vars are configured in production if analytics are expected.
- [ ] Add first-party `events` table for critical learning events so learning does not depend only on PostHog.
- [ ] Track anonymous session id, user id if available, timestamp, city, mode, filters, result count, and source.
- [ ] Track search submitted, search succeeded, search failed, zero results, and fallback used.
- [ ] Track natural-language parse latency, parse success, parsed fields, approximate area, and user correction.
- [ ] Track filter changes with previous/new values.
- [ ] Track listing impressions by position.
- [ ] Track listing opens by position and source.
- [ ] Track contact intent by channel, listing id, position, source, and whether phone was already known.
- [ ] Track favorite, hide, share, report, and save-search actions.
- [ ] Track scroll depth and card exposure on list and map carousel.
- [ ] Track map interactions separately: pan, zoom, marker click, search-this-area.
- [ ] Track onboarding card selection and downstream conversion.
- [ ] Track feedback issue type in structured form, not only free text.
- [ ] Build a weekly product report: searches, zero-result rate, listing-open rate, contact-intent rate, top areas, failed parses, crawl freshness.

## Feedback System

- [ ] Add structured feedback categories.
- [ ] Attach listing id or search id automatically when feedback comes from a listing or result set.
- [ ] Add admin view for feedback.
- [ ] Add status fields: new, triaged, fixed, ignored.
- [ ] Queue offline feedback with visible confirmation.
- [ ] Use feedback data to create area alias fixes, crawl fixes, and ranking penalties.

## Performance And Reliability

- [ ] Add API timing to search responses or client analytics.
- [ ] Add graceful fallback from failed map search to city search.
- [ ] Avoid repeated automatic map-search calls during page load.
- [ ] Cache default Lahore city browse aggressively but safely.
- [ ] Add explicit timeout and retry behavior for live scrape fallback.
- [ ] Make Playwright tests independent of live inventory where possible.
- [ ] Add seeded local data fixtures for default load tests.
- [ ] Investigate intermittent mobile/combined Playwright timeouts waiting for `.card-wrap`.
- [ ] Add a stable no-results test path separate from successful card rendering.

## Accessibility

- [ ] Add accessible names to icon-only card action buttons.
- [ ] Add keyboard support and focus states for all chips/dropdowns.
- [ ] Ensure mobile bottom sheets trap focus while open.
- [ ] Ensure drawer and gallery have proper focus management.
- [ ] Add ARIA live region for search loading, result count, and parse feedback.
- [ ] Avoid relying on color alone for active filters and freshness states.
- [ ] Verify touch target sizes for chip clear buttons and card actions.

## Copy And Content

- [ ] Replace "Default" sort label with "Recently updated" or "Fresh first."
- [ ] Replace "Map Coverage" with a user-facing phrase such as "Areas visible on map."
- [ ] Make "Local only" understandable or hide it from normal users.
- [ ] Use city-aware examples in placeholders and welcome cards.
- [ ] Make empty states specific and actionable.
- [ ] Reduce persistent explanatory banners; put trust/details behind subtle affordances.

## Admin And Operations

- [ ] Crawl coverage dashboard by city and area.
- [ ] Crawl freshness dashboard.
- [ ] Contact fetch success dashboard.
- [ ] Top zero-result searches dashboard.
- [ ] Top approximate-match searches dashboard.
- [ ] Area alias management UI.
- [ ] Duplicate listing review UI.
- [ ] Feedback triage UI.
- [ ] Data quality score per listing and per area.

## Suggested Priority

> **Superseded by the [Audience-grounded review](#audience-grounded-review--proposal-for-discussion-reviewed-2026-06-02) at the top of this doc (reviewed 2026-06-02).** The original P0–P3 list below is kept for reference; several items shipped (saved searches, alerts, favorites, new-since-last-visit, contact-intent instrumentation) and others were re-sequenced or flagged as premature (learned ranking, dashboards, landmark/commute) after checking the data and code. Use the reviewed priority for what to build next.

<details><summary>Original P0–P3 (pre-review, kept for reference)</summary>

### P0: Fix Trust Breakers

- [ ] Stable Lahore default everywhere.
- [ ] City browse as default first-load mode.
- [ ] Graceful fallback from map-search failure to city results.
- [ ] Clear empty/data-unavailable states.
- [ ] Seeded test data for default card-render tests.

### P1: Improve Conversion

- [x] Saved listings.
- [x] Saved searches.
- [x] Contact-intent instrumentation. _(client-side; server-side pending)_
- [ ] Freshness and contact confidence badges. _(build now — data already in results)_
- [ ] Editable parsed NL filter chips. _(build now)_

### P2: Make The Product Learn

- [ ] First-party interaction events table. _(build next — thin, log-only)_
- [ ] Listing impressions and position-aware ranking metrics. _(reconsider — vanity at this traffic)_
- [ ] Zero-result and failed-parse dashboards. _(zero-result already in search_history; skip dashboards, query raw)_
- [ ] Ranking based on opens, contact intent, freshness, and hidden listings. _(deterministic half = build now; learned half = defer)_

### P3: Retention And Intelligence

- [x] Alerts for saved searches.
- [x] New-since-last-visit.
- [ ] Similar listings. _(later — only after dedup)_
- [ ] Price intelligence by area/type. _(reconsider — "good value" badge risky on noisy data)_
- [ ] Commute and landmark-based search. _(reconsider — coarse landmark ok; radius is a trap on centroid coords)_

</details>
