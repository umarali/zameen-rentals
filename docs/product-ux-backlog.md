# Product, UX, and Learning Backlog

Date: 2026-05-15

This document itemizes possible features, fixes, and enhancements for ZameenRentals after a strict UI/UX and product review. It is intentionally written as a planning backlog: each item should be small enough to discuss, scope, and turn into an issue.

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

- [ ] Add favorite/save listing.
- [ ] Add hide/dismiss listing.
- [ ] Add compare shortlist.
- [ ] Add share listing and share search.
- [ ] Add "seen before" / "new since last visit" markers.
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

- [ ] Make welcome overlay optional and less intrusive for returning users.
- [ ] Use the welcome overlay to ask intent: "budget apartment", "family home", "near me", "specific area."
- [ ] Do not request geolocation implicitly from onboarding.
- [ ] If city detection is desired, ask explicitly: "Use my location to choose city?"
- [ ] Track which onboarding cards lead to searches, listing opens, and contact intent.
- [ ] Replace generic quick-start cards with city-aware presets.

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

- [ ] Saved searches.
- [ ] Search alerts by city, area, price, beds, type, and freshness.
- [ ] Favorite listings.
- [ ] Hidden listings.
- [ ] Recently viewed listings.
- [ ] "New since your last visit" view.
- [ ] Browser push notifications for saved searches.
- [ ] Email/WhatsApp alerts if appropriate for the user base.
- [ ] Persist preferred city and common budget/type from actual behavior.
- [ ] Add lightweight accountless persistence first; account system can come later.

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

### P0: Fix Trust Breakers

- [ ] Stable Lahore default everywhere.
- [ ] City browse as default first-load mode.
- [ ] Graceful fallback from map-search failure to city results.
- [ ] Clear empty/data-unavailable states.
- [ ] Seeded test data for default card-render tests.

### P1: Improve Conversion

- [ ] Saved listings.
- [ ] Saved searches.
- [ ] Contact-intent instrumentation.
- [ ] Freshness and contact confidence badges.
- [ ] Editable parsed NL filter chips.

### P2: Make The Product Learn

- [ ] First-party interaction events table.
- [ ] Listing impressions and position-aware ranking metrics.
- [ ] Zero-result and failed-parse dashboards.
- [ ] Ranking based on opens, contact intent, freshness, and hidden listings.

### P3: Retention And Intelligence

- [ ] Alerts for saved searches.
- [ ] New-since-last-visit.
- [ ] Similar listings.
- [ ] Price intelligence by area/type.
- [ ] Commute and landmark-based search.
