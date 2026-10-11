# Listing-trust implementation review

Reviewed 10 October 2026. **Both branches: merge after fixes.** No application fixes, commits, pushes, PRs, deployments or production SSH were performed.

Branch 1, `feat/listing-observations` at `3c4a08a30c553a2fe93e601fb893a09ca957d3b3`, implements the right evidence collection and UTC corrections, but should not merge with its current error handling and observation semantics. A real SQLite error can roll back the listing write while the wrapper returns success. Missing labels, cache reuse and same-second version recurrence also make the history less reliable than its documentation promises. Fix findings 1, 2, 3 and 4 before treating this as the ≥90% branch.

Branch 2, `feat/honest-listing-dates`, should merge only after the inherited fixes and findings 5, 6 and 7. Local first-seen ordering is implemented, but live fallback keeps a different meaning under the same label. The current compare view can attribute our discovery date to Zameen and drops Updated dates. The explanation also asserts an agent action that the prior evidence review did not establish. Keeping this product direction separate is appropriate; changing the interface does not itself validate its effect on renter trust.

The baseline was `origin/main` at `e9506fc6eb513173c412f4cd2631111aff3cd3ab`. I reviewed the original dates implementation at `1022a48a24578e41fa8819c03d570498e6d75400` and the current UI at `3d18e2595f5e5e0def7d9b66d00e315b2306702a`. The latter began as local changes and was committed by another actor during this review. My captured source matched that commit; I updated only the scratch test copy to match its final tests. Findings 6 and 7 concern this latest UI. Finding 5 also affects the original dates implementation. File links below point to the current dates worktree, which includes branch 1.

I used isolated copies under `/private/tmp/zameen-implementation-review`. The two source worktrees were clean immediately before writing this report. The live local database was opened with SQLite `mode=ro` only to create a `.backup`; all benchmarks and mutations used disposable databases. No fresh Zameen requests or paid API calls were needed. Browser tests were headless and used my own ports 18461–18464.

**Ranked findings**

Confidence percentages describe confidence in the stated code behavior or evidence gap. They are judgment estimates, not statistical estimates of how often users encounter a failure.

1. **P1: An observation error can discard the listing update and still return success.** [app/db_listings.py:448](/Users/umarali/Workspace/MVPs/zameenrental-trust-dates/app/db_listings.py:448), especially the catch and commit at lines 460–464. Both branches.

   `_write_listing_row` runs in the same transaction as the observation write. Catching every exception does not guarantee that SQLite has preserved that transaction. I limited a disposable database with `PRAGMA max_page_count`, then made the observation callback execute a real oversized SQL insert. SQLite raised `SQLITE_FULL` and ended the transaction. The wrapper returned `updated`, but a listing whose price should have changed from 10 to 20 still had price 10. This reproduces an engine rollback, rather than a callback merely raising `RuntimeError`.

   Evidence: `python3 /private/tmp/zameen-implementation-review/probes.py`; [output](/private/tmp/zameen-implementation-review/probes.txt) contains `engine error SQLITE_FULL in_transaction False` and `DISK_FULL_RESULT updated before 10 after 10`. The fault injection used a 5 MB value to trigger the boundary cheaply; it does not assert that real listings contain such values. An ordinary write at a genuinely full database can reach the same error class. Earlier uncommitted batch writes can also be lost, an inference from the shared transaction rather than a separately measured batch failure.

   Required change: distinguish errors that preserve the transaction from errors that invalidate it. Do not acknowledge the listing write after rollback. Preserve the batch's atomicity and expose a retryable failure. A savepoint alone cannot restore an outer transaction that SQLite has already rolled back. Confidence ≥99% in the reproduced failure; production incidence unknown.

2. **P2: A retained label can acquire a later observation time, and some Updated changes disappear from the version history.** [app/listing_observations.py:96](/Users/umarali/Workspace/MVPs/zameenrental-trust-dates/app/listing_observations.py:96) and [app/listing_observations.py:129](/Users/umarali/Workspace/MVPs/zameenrental-trust-dates/app/listing_observations.py:129). Both branches.

   A version observed at 00:00 with `Added: 2 hours ago`, followed at 01:00 and 02:00 by the same epoch/title without an Added label, becomes one row with `last_observed_at=02:00`, `last_added_text=Added: 2 hours ago`, and count 3. There is no field saying that the retained label was last seen at 00:00. A later analyst cannot reliably pair that label with its observation time, the same class of evidence problem identified in the prior review.

   Also, the hash ignores both labels whenever `created_epoch` exists. With no `updated_epoch`, changing `Updated: 2 days ago` to `Updated: 1 minute ago` produces the same hash. A series of such changes retains only its first and final labels. The assumption that a created epoch explains every Updated label is unsupported.

   Evidence: the `STALE_LABEL` and `hash updated label absent epoch True` outputs in [probes.txt](/private/tmp/zameen-implementation-review/probes.txt). Required change: give retained labels their actual observation times and preserve missingness; decide label deduplication independently against the corresponding epoch. Document any deliberate loss of intermediate labels. Confidence ≥99% in both reproductions; their frequency in future crawls is unmeasured.

3. **P2: Cached detail reads are recorded as fresh upstream observations.** [app/scraper.py:685](/Users/umarali/Workspace/MVPs/zameenrental-trust-dates/app/scraper.py:685), [app/routes.py:718](/Users/umarali/Workspace/MVPs/zameenrental-trust-dates/app/routes.py:718), [app/db_listings.py:458](/Users/umarali/Workspace/MVPs/zameenrental-trust-dates/app/db_listings.py:458). Both branches.

   A listing without exact geography takes the detail fallback. `fetch_listing_detail` can return its five-minute cached dict, including lifecycle fields. The route upserts it again, and the recorder uses the current clock. Two visitors therefore increase the source observation count and advance its timestamp without a second Zameen fetch.

   Evidence: `python3 /private/tmp/zameen-implementation-review/route_probes.py`; [output](/private/tmp/zameen-implementation-review/route-probes.txt). Two GETs served a seeded cache without an upstream fetch, yet produced one detail observation spanning 01:00 to 01:04 with count 2. The clock was patched deliberately to make the error visible. Both public responses correctly omitted lifecycle metadata.

   Required change: carry the original fetch time and cache-hit identity to the recorder, or record only actual upstream fetches. App reads and source sightings need different semantics. Confidence ≥99% in the reproduced route behavior.

4. **P2: A version that recurs within one second is silently dropped.** [app/listing_observations.py:60](/Users/umarali/Workspace/MVPs/zameenrental-trust-dates/app/listing_observations.py:60), [app/listing_observations.py:82](/Users/umarali/Workspace/MVPs/zameenrental-trust-dates/app/listing_observations.py:82), [app/listing_observations.py:145](/Users/umarali/Workspace/MVPs/zameenrental-trust-dates/app/listing_observations.py:145). Both branches.

   Live timestamps have one-second precision. For one listing/source, feed versions A, B, A, A within that second. The latest row is B, so the third event tries to insert A, conflicts with the earlier A's unique key, and is ignored. The fourth A is ignored too. Only two rows with count 1 remain; latest still points at B, although the two latest inputs were A.

   Evidence: the four `ABA` calls and `ABA_ROWS` in [probes.txt](/private/tmp/zameen-implementation-review/probes.txt), using epochs 100, 200, 100, 100 and a fixed timestamp. This is a synthetic boundary test, not an observed upstream recurrence. Concurrent or overlapping search pages can expose differing cached source states close together; that exposure is plausible, not measured.

   Required change: separate live event identity from historical-import idempotency. Preserve recurrent versions and counts even at identical observation timestamps. Confidence ≥99% in the failure; operational frequency unknown.

5. **P2: “Recently found” switches to Zameen's date order during live fallback.** [frontend/index.html:218](/Users/umarali/Workspace/MVPs/zameenrental-trust-dates/frontend/index.html:218), [app/routes.py:492](/Users/umarali/Workspace/MVPs/zameenrental-trust-dates/app/routes.py:492), [frontend/src/main.js:480](/Users/umarali/Workspace/MVPs/zameenrental-trust-dates/frontend/src/main.js:480). Dates branch, original and current.

   An empty local result sends `sort=newest` upstream, where the URL builder maps it to `date_desc`. Live cards have no local first-seen timestamp. The selected option still says “Recently found.” The new header correctly renames the default option to “Zameen's order,” but does not rename this explicit selection.

   Evidence: the mocked live-fallback request in [route-probes.txt](/private/tmp/zameen-implementation-review/route-probes.txt) returns `source=live` for `/api/search?city=islamabad&sort=newest`, generates `https://www.zameen.com/Rentals/Islamabad-3-1.html?sort=date_desc`, and returns a card without `first_seen_at`. No upstream request was made.

   Required change: explicitly report the actual sort and label or disable the local-discovery option when the source cannot support it. Confidence ≥99% in the request path and ≥95% in the UI mismatch from the selected-option code.

6. **P2: Compare attributes our first-seen date to Zameen and loses the Updated date.** [frontend/src/compare.js:119](/Users/umarali/Workspace/MVPs/zameenrental-trust-dates/frontend/src/compare.js:119) and [frontend/src/compare.js:375](/Users/umarali/Workspace/MVPs/zameenrental-trust-dates/frontend/src/compare.js:375). Current dates UI at `3d18e25`.

   The existing snapshot function substitutes `first_seen_at` for missing `posted_at` and does not retain `updated_at`. Using that snapshot for the new “Date on Zameen” row creates two failures. A listing with only our first-seen timestamp gains an “Added 1 day ago” source date in compare. A card showing “Updated 1 hour ago” becomes “Added 5 days ago” in compare when both source dates originally existed.

   Evidence: `TZ=Asia/Karachi node /private/tmp/zameen-implementation-review/compare_probe.mjs` runs the actual snapshot function and current date-label helper. The first case returns an empty card date and a nonempty compare date. The second mismatch was also observed in the rendered mobile Chromium UI, [ui-probes.txt](/private/tmp/zameen-implementation-review/ui-probes.txt). The desktop diagnostic fixture did not reproduce that mismatch because its viewport search bypassed the particular mocked response; I do not count it as a desktop reproduction.

   Required change: preserve source timestamps independently, retain `updated_at`, and remove the discovery-time substitution. Handle already-saved compare snapshots whose substituted dates cannot be reliably distinguished. Confidence ≥99%.

7. **P2: The explanation promotes an unverified causal claim into customer copy.** [frontend/src/listing-date.js:30](/Users/umarali/Workspace/MVPs/zameenrental-trust-dates/frontend/src/listing-date.js:30). Current dates UI at `3d18e25`.

   “Agents can refresh an ad, which moves its date forward” attributes the observed changes to an actor and mechanism. The authority document establishes same-ID date movement and leaves the mechanism unresolved. Paid promotion, edit, reactivation or another source action were hypotheses. The earlier branch's neutral caveat avoided this claim.

   Evidence: direct comparison with H1 and the confidence recommendations in [review.md](/Users/umarali/Workspace/MVPs/zameenrental-trust-dates/docs/listing-trust-2026-10-10/review.md). Required change: state the observed fact, for example, “Zameen's displayed date can move forward for the same ad, so this date does not establish when the ad first appeared.” Keep the existing availability caveat. Confidence ≥95% that the supplied evidence does not support the present causal wording; this does not prove that agents cannot refresh ads.

8. **P3: First-seen ordering has no supporting ordering index.** [app/db_listings.py:17](/Users/umarali/Workspace/MVPs/zameenrental-trust-dates/app/db_listings.py:17) and its search uses. Dates branch.

   On the 34,718-listing database copy, a Lahore query ordered by first-seen used `idx_listings_default` to select city rows and a temporary B-tree to sort them. The previous source-date ordering used `idx_listings_source_freshness`. For 30 warm samples of `SELECT * ... WHERE is_active=1 AND city='lahore' ... LIMIT 25`, the medians were 14.13 ms and 0.214 ms respectively. These are local SQL timings, not endpoint latency or a production regression percentage.

   Evidence: [sort-growth.txt](/private/tmp/zameen-implementation-review/sort-growth.txt), including both query plans. Add an index suited to the common unfiltered first-seen query, or show that production-equivalent load stays within a stated latency budget. Distance/filter variants need their own plans. Confidence ≥99% in the plan and local cost; impact on the Droplet remains unverified. This is a performance follow-up, not an independent correctness blocker.

**What held up under review**

Normal transaction behavior remained consistent with the existing caller contract. Outside a batch, `commit=False` left a transaction pending and another connection could not see the row; `commit=True` persisted it. Inside a batch, `commit=False` persisted at batch exit. Calling `commit=True` inside the batch commits early, as it already did before this wrapper. That is not a new regression. These four cases appear in `probes.txt`.

The wrapper passes authoritative search state into the listing write before the alert hook and retains the existing hook's `commit=False` behavior. Existing alert tests passed; I found no normal-path alert regression. The detail dict is copied before removing lifecycle metadata, and its nonmutation test passed. Return values for ordinary inserted, updated and unchanged records remained consistent. Finding 1 is the exception that invalidates the stronger promise that observation failures never affect listings.

Lifecycle data is separated by source and whitelist. The detail cache intentionally retains it, while the public detail route strips it on every inspected return through that fallback. Both cache-hit test responses omitted it and the cached dict remained intact. Other inspected callers consume specific detail fields rather than returning the whole enriched dict. I found no demonstrated public lifecycle or contact leak.

The extraction helpers reject bool epochs/counts, accept numeric epochs, and omit numeric strings; counts accept integers but omit fractional floats. Labels are stripped. They are not comprehensive validators: nonfinite epochs survive, an infinite detail price raises `OverflowError`, and an arbitrary dict in `agency.externalID` is converted to a string. The synthetic dict probe contained a fake `phone` key and was stored as the ID string. That demonstrates an overly broad conversion, not a real contact leak from the sampled pages. Restrict IDs to expected scalar types, require finite numbers and bound retained strings. Missing normal fields are handled; malformed nested object/array shapes need tests.

The version hash changes for `price=10` versus `10.0` and for title whitespace. This can create extra rows if callers vary representations. Extracted epochs are normalized to float, so ordinary numeric epoch representations converge. With no created epoch, changing relative labels produces new rows by design. With epochs, replaying the 100 distinct listing IDs in the existing 102-hit capture and changing only the Added hour extended all 100 rows without inserting another version. This verifies that narrow deduplication case, not a future source-change rate.

All current production recorder timestamps use canonical UTC `+00:00` strings with the same precision, so lexicographic latest-row ordering works for those inputs. `observed_at` itself accepts arbitrary strings; imports normalize it, but future callers should validate it. Mixed offsets would break that assumption. The store updates counters and endpoint labels, so “version history” is more accurate than literally “append-only.” `get_observations` fetches all history for an ID without pagination. No public endpoint currently exposes that unbounded read.

**Time handling and interface checks**

The frontend search `rg -n 'Date.parse|new Date\(' frontend/src` found server parsing centralized in `parseServerTime`. Remaining `new Date` calls construct local now, ISO saved-at values or dates from already-parsed milliseconds. Under `TZ=Asia/Karachi`, a naive UTC value one hour old displayed as six hours old on the baseline and one hour old on both branches. The stale-listing same-day cutoff probe marked zero on the baseline and one on both branches. The first-seen sort probe retained the old source-date order on baseline/observations and reversed it correctly on dates. These failures are behavioral, rather than old-code import errors.

The six-digit fractional timestamp parsed in headless Chromium and in the installed system JavaScriptCore through JXA. `Date.parse('2026-10-07T17:43:41.107842Z')` and the three-digit form both returned `1791395021107`. This is useful engine evidence; it is not a full Safari or iOS browser acceptance run. No browsers were installed or browser caches removed.

The remaining raw comparison `card_scraped_at > detail_scraped_at` at `app/db_listings.py:1202` assumes identical timestamp formats. In the copy, all 34,718 card timestamps and all 5 populated detail timestamps used `T`, as did all 34,718 last-seen and 34,713 populated contact timestamps. First-seen used spaces. Crawl-state and search-history comparisons against SQLite `datetime()` inspected here use SQLite-format writes. I did not find another proven current mixed-format failure in those paths; legacy production data could differ.

The current targeted browser suite covered sort synchronization, results, map behavior, responsive behavior and dates. Existing viewport tests passed. The nearby first-seen backend test also passed. The intended ordering still means first discovered by this database, including on rebuild. In the snapshot, 33,324/34,718 listings, 95.98%, were first seen on 7 October; the other daily counts were 695, 630 and 69. Most initial ordering therefore reflects crawl sequence. It says little about source age or availability. Keeping the default order unchanged is consistent with the prior review.

The native select has a text label and visible keyboard focus. The date button has an accessible name, `aria-describedby`, `aria-expanded` and a tooltip role. Headless checks covered its interaction behavior. Extra geometry probes found the tooltip inside card/viewport bounds at desktop width 1440 and mobile width 375 despite the card's `overflow-hidden`. That checks these two layouts only. The unsupported `field-sizing: content` fallback should use native select sizing, but actual Safari/Firefox layout and screen-reader announcements remain unverified. The explicit availability caveat avoids asserting that an older listing is rented. Hiding our first-seen date in an explanation is an owner-directed design choice whose user benefit has not been measured.

**Growth, write cost and import evidence**

The backup contained 34,718 listings. Its earliest first-seen was `2026-10-07 05:56:17` UTC and latest last-seen was `2026-10-10T05:34:48.311731` UTC. This is a local crawler dataset, not production history.

| Measurement on disposable copies | Observed result |
| --- | --- |
| First history pass over 34,718 real stored card records, commits every 25 | 34,718 inserts in 2.671 s, 76.94 µs/card |
| Identical second pass over those 34,718 records | 34,718 extensions in 1.461 s, 42.07 µs/card, zero new rows |
| Initial history table plus both indexes | 17,666,048 bytes / 34,718 rows = 508.84 bytes/row |
| Full upsert of 5,000 real stored cards, 200 batches of 25 | Existing write body 2.216 s; wrapper with history 3.671 s |
| Same full-upsert sample, mean per card | 443.23 µs without history; 734.27 µs with history; difference 291.04 µs/card |
| Same sample, median / p95 batch time | Without 5.96 / 35.39 ms; with 9.25 / 64.65 ms |
| Historical import table plus both indexes | 39,862,272 bytes / 67,645 rows = 589.29 bytes/row |

Commands are in [bench.py](/private/tmp/zameen-implementation-review/bench.py) and [upsert_bench.py](/private/tmp/zameen-implementation-review/upsert_bench.py); outputs are [bench.txt](/private/tmp/zameen-implementation-review/bench.txt) and [upsert-bench.txt](/private/tmp/zameen-implementation-review/upsert-bench.txt). The full-upsert comparator calls the unchanged `_write_listing_row` body directly. These were local Mac runs, some concurrent with browser tests, with filesystem/cache noise and no repeated controlled load experiment. Do not extrapolate the time ratio to the 1-vCPU Droplet. Byte totals exclude other app tables, transient WAL growth and backup copies.

There is no measured steady-state rows/day for the new epoch-aware recorder. The frozen two-snapshot CSV supports a conditional estimate for the label-only fallback. Of 32,987 IDs whose card timestamp advanced, 28,860 changed labels. Their mean interval was 2.3088 days, giving roughly 12,500 changed-version rows/day for that cohort if this pattern repeats. At the measured 508.84 bytes/row, that is about 6.36 MB/day or 191 MB/30 days, excluding new IDs and other changes. This is an extrapolation from two endpoints; intermediate events are missing. It is not a production forecast. Epoch-aware replay deduplicates elapsed-hour labels, but the observed capture has no longitudinal epoch series from which to estimate its actual daily changes.

For `datetime()` cost I timed simplified count predicates 12 times each on the copy. They isolate the changed comparison and are not full crawler queries or UPDATE timings.

| Predicate | Median before / after | Query-plan observation |
| --- | --- | --- |
| Seven-day stale last-seen | 1.79 / 3.93 ms | Both use covering source-freshness index for `is_active` |
| Seven-day detail age | 15.79 / 20.57 ms | Both use active index |
| Three-day contact age | 20.57 / 19.09 ms | Both use active index; timing difference is not evidence of a speedup |

Every diagnostic predicate matched zero rows in this recent dataset. Neither form used a timestamp range index in these plans, so the wrappers did not remove an existing timestamp range lookup here. Real stale distributions, full OR clauses, ordering and concurrent writers still need production-equivalent testing. The comparison correction is nevertheless demonstrated by the separate boundary test.

History has no retention or storage budget. Daily changes, WAL, backups, and large title/image strings can keep growing. Set disk/WAL monitoring and measure live insertion/extension rates before estimating operating cost. Retention must preserve the evidence needed for the trust feature rather than quietly deleting inconvenient history.

The snapshot importer produced 67,934 candidate observations from 34,658 CSV rows. Its first run inserted 67,645 and skipped 289. Direct CSV comparison confirmed that exactly 289 IDs had identical card timestamps, Added labels and Updated labels across both snapshots. They are duplicate observations, not 289 unexplained failures. The second run inserted zero and recognized all 67,934 candidates. Provenance includes filename, uncompressed SHA-256, source-column prefix and tool version. The input hash was `8dfa412248a8d0a0a6175a1de56a057577792c2cdc5e83a28d6cd9ae4be8ba73`.

The first and repeat import runs took 5.392 s and 4.173 s locally. A separate repeat measured about 230 MB peak child RSS, roughly 220 MiB; the tool materializes decompressed input, CSV rows and the pending observations. It uses one write transaction. On a shared 2 GB / 1-vCPU machine this deserves a controlled import window or a measured batch strategy, especially with the five-second SQLite busy timeout. Lock contention on that host was not tested.

Importing local evidence can be appropriate as explicitly identified historical evidence. It must not imply that production observed those ads, establish production first-seen dates, or confirm availability. The tool leaves listing first-seen and active status alone and uses `snapshot_import`. Before running it against production, retain the input/hash, label the originating local environment, back up the target and verify its schema and writer schedule. No production import is recommended without those checks; none was attempted.

**Confidence classification**

The earlier review supports raw source observations, cautious same-ID date-change language, timestamp correctness and preserving the existing ranking while evidence develops. Those belong on the high-confidence branch once the implementation defects are repaired. Collecting epochs as uninterpreted values is justified; calling a particular epoch original creation, a refresh or proof of availability is not.

Branch 1's current history semantics go beyond that support when cache hits imply new source sightings or retained labels inherit later times. Its blanket statement that history failure cannot fail a listing write is disproved. The version hash also assumes more about Updated labels than the reviewed evidence establishes. These are implementation confidence problems, not reasons to abandon observation collection.

Branch 2's local sort is testable and works locally. The desirability of “Recently found,” its placement and the information popover remain product hypotheses. The owner has supplied direction, not a measured user outcome. The agent-refresh sentence crosses from a UI hypothesis into an unsupported factual claim and should be corrected even on the experimental branch.

I found no clearly supported ≥90% product change wrongly left deferred. A first-seen filter and default-sort change need utility validation; age cutoffs, similarity grouping and ID-based dating still lack the required evidence. An “Already rented?” report needs a trustworthy reporting workflow. Production history checks remain valuable evidence gathering, and the no-SSH scope properly leaves them undone. Deferring them does not authorize treating the local rebuild as production history.

**Validation results and missing tests**

| Scope | Result |
| --- | --- |
| Branch 1 Python suite | Initially 853 passed, 7 failed, 2 skipped; the sandbox-blocked server test passed on rerun, leaving 6 missing-`av` failures |
| Original dates Python suite | Initially 855 passed, 7 failed, 2 skipped; the same server test passed on rerun, leaving 6 missing-`av` failures |
| Baseline voice comparison | Same 6 failures, 22 passed, 2 skipped |
| Branch 1 full headless Playwright | 466 passed, 20 skipped, 486 total |
| Original dates full headless Playwright | 468 passed, 20 skipped, 488 total |
| Current `3d18e25` targeted headless suite | 79 passed, 17 skipped, 96 total |
| Current extra UI diagnostics | 2 passed; diagnostic output exposed finding 6, so these are not assertions that compare is correct |
| Frontend builds | Passed in observations, original dates and current-UI scratch copies; existing large-chunk warning |

The Python command was `env -u ANTHROPIC_API_KEY -u OPENAI_API_KEY -u JEV_API_KEY python3 -m pytest tests -q`. The extra failure was a local socket-binding restriction in `test_serve_playwright`, not an application failure; that test passed with local-server permission. Browser commands used Node 22 and `PLAYWRIGHT_PORT=18461` or `18462` with `npx playwright test`. The current targeted run used port 18463 and selected timezone, results, map and responsive tests. The two diagnostic tests used 18464. Build dependencies were installed only in scratch copies. No browser install occurred. Full logs remain in [the scratch evidence directory](/private/tmp/zameen-implementation-review).

Tests worth adding, in priority order:

- Real SQLite rollback during observation recording, both standalone and inside a multi-listing batch. Assert persisted listing values, alert rows and truthful return/failure behavior.
- Missing-label/reappearing-label timestamps; created epoch present with Updated epoch absent; A→B→A within one second; cache-hit detail reads versus fresh fetches.
- Compare dates with only first-seen, with both source dates, with no dates, and with existing persisted snapshots. Assert agreement with card/drawer date attribution.
- Explicit `newest` live fallback, verifying the displayed actual sort and absence of invented first-seen dates.
- Map-focus and nearby first-seen ties, pagination and viewport changes with a rebuilt cohort. Existing nearby and viewport tests cover parts of this, not the whole matrix.
- Malformed/nonfinite lifecycle numbers, numeric strings, nested object shape errors, bounded scalar agency IDs, and price/title representation changes.
- Detail/contact same-day SQL cutoff tests, alongside the existing stale cutoff test. Add a mixed-format fixture if legacy data can contain both formats.
- Safari/Firefox at narrow widths and zoom, keyboard-only dismissal with sensible focus, screen-reader announcement, and tooltip bounds for extreme card content. Verify native select fallback when `field-sizing` is unavailable.

**What remains unverified**

- Production database age, timestamp formats, stored observation history, disk headroom and import provenance. Requires an authorized read-only production snapshot or operator-supplied extracts; no SSH was used.
- Actual daily epoch-aware version growth and cache-hit frequency. Requires instrumented insertion/extension counts over several crawl cycles, with source fetch times and source identity retained.
- Shared-Droplet latency, SQLite lock contention, WAL growth and peak import memory with crawler/API traffic. Requires a comparable load environment and an agreed latency/storage budget.
- Full Safari/iOS/WebKit and Firefox layout, assistive technology behavior, and `field-sizing` fallback. Requires an already-available browser environment or explicit approval for a safe browser provisioning plan. The JXA result is limited to the installed JavaScriptCore date parser.
- The entire Playwright suite at current `3d18e25`. The full suites covered the original commits; current UI changes received the 96-test targeted run and two additional diagnostics. Backend code was unchanged between the original and current dates UI reviewed here.
- Any actual agent refresh action, original listing age, rented status or causal effect of a paid product. Requires direct source/action evidence or independently confirmed outcomes. This review did not contact agents or infer availability from date movement.
- Whether renters understand and benefit from the chosen date/sort design. Requires usability evidence. Automated correctness checks cannot establish that product claim.

The report is the only requested worktree artifact. Reproduction scripts, disposable databases and test logs remain outside the worktrees in the scratch directory and may be removed by ordinary temporary-file cleanup.
