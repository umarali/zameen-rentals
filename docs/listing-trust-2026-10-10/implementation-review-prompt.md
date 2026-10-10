# Review: listing-trust implementation (two branches)

## Your role
You are an independent code reviewer. Another agent implemented changes based on an earlier evidence review, `docs/listing-trust-2026-10-10/review.md`. Your job is to find what is wrong, risky or missing before these branches are merged and deployed.

Report problems with evidence. Do not fix them, commit, push, open PRs or deploy.

## Product context
ZameenRentals offers an Airbnb-style interface, a map, and English / Roman Urdu / Urdu / voice search over Zameen.com rentals.

Its second promise is trust. Zameen moves a listing's "Added" date forward while the listing ID stays the same, and agents keep ads live after the home is rented.

The owner's bar:
- every claim and change needs 90–95% confidence and evidence;
- work at 80–85% confidence lives on a separate branch;
- no paid APIs (Claude or others) for this work.

## What was built
Repo: `/Users/umarali/Workspace/MVPs/zameenrental`. Production runs on a DigitalOcean Droplet with 2 GB RAM and 1 vCPU, shared with the crawler.

**Branch 1: `feat/listing-observations`**, worktree `../zameenrental-trust`, commit `3c4a08a`. Meant to contain only ≥90% items from review.md.
- `app/listing_observations.py`, a new append-only table:
  - one row per distinct version of a listing per source (`search_card`, `detail_page`, `snapshot_import`);
  - a re-seen version only extends `last_observed_at` and `observation_count`;
  - the version hash ignores the relative labels whenever Zameen's `createdAt` epoch is present.
- `app/db_listings.py`: `upsert_listing` is now a wrapper. It calls `_write_listing_row` with `commit=False`, records observations, swallows observation errors, then commits.
- `app/scraper.py`: `state_lifecycle()` extracts raw `createdAt`, `updatedAt`, `reactivatedAt`, `approvedAt`, `product`, `state`, `purpose`, `isVerified`, `photoCount`, `videoCount` and agency ID/tier/product. It runs on search hits (`search_state["lifecycle"]`) and on detail pages (`zameen_lifecycle`).
- `app/routes.py`: `/api/listing-detail` strips `zameen_lifecycle` from responses.
- `app/crawler_worker.py`: passes the search-page URL as `source_page`, and wraps `contact_fetched_at` in `datetime()`.
- SQL: `mark_stale_listings` and `get_listings_needing_detail` now compare through `datetime()`, because `T`-format strings sorted wrongly against SQLite's space format.
- `tools/import_observation_snapshot.py`: idempotent import of `docs/listing-trust-2026-10-10/evidence/added_text_oct7_vs_current.csv.gz`, with provenance.
- Frontend: a `parseServerTime()` helper in `frontend/src/utils.js` treats naive server timestamps as UTC. It is used by `fmtRelative`, `isNewSinceLastVisit`, compare and the footer.
- Docs: verdict notes in findings.md, superseded backlog claims, CLAUDE.md/AGENTS.md corrections.
- Tests: `tests/test_listing_observations.py`, new cases in `tests/test_scraper.py`, and `tests/timezone.spec.js`.

**Branch 2: `feat/honest-listing-dates`**, worktree `../zameenrental-trust-dates`, commit `1022a48`, stacked on branch 1. Meant for 80–85% items.
- Card date line: "First seen by us 10 Oct" instead of Zameen's "Added X ago".
- Drawer: our first-seen date, Zameen's dates attributed to Zameen, and a caveat line.
- Sort: "Newest First" becomes "Recently found", ordered by `first_seen_at DESC, id DESC`. This applies to search, map focus and nearby.
- Compare: the freshness row is "First seen by us".
- The default order is unchanged; its source badge still says "Newest first".

Deliberately deferred:
- a first-seen filter;
- the default sort order;
- any age cut-off;
- similarity or repost grouping;
- an "Already rented?" report;
- production history checks;
- ID-based dating.

## Read first
- `CLAUDE.md`, then `docs/listing-trust-2026-10-10/review.md` (the authority these changes claim to follow) and `findings.md`.
- The diffs: `git -C ../zameenrental-trust diff origin/main..feat/listing-observations` and `git -C ../zameenrental-trust-dates diff feat/listing-observations..feat/honest-listing-dates`.

## What to check
1. **Correctness of the upsert wrapper.**
   - Transaction and commit behaviour with `commit=True` and `commit=False`, inside and outside `listing_write_batch()`.
   - The new-listing alert hook.
   - Return values.
   - What happens when observation recording raises mid-transaction.
   - Whether the caller's `detail_data` is mutated.
2. **Observation semantics.**
   - Can the version hash miss a meaningful change, or create rows on every crawl? Check labels, float epochs, title whitespace and price types.
   - Is "latest row" selection right? It orders by `last_observed_at` text with `+00:00` offsets.
   - Is anything stored that should not be, such as contact data?
3. **Growth and performance on the 2 GB Droplet.** Estimate rows per day and bytes per row from a real crawl, using a copy of `data/rebuild/zameenrentals.db`, never the live file. Measure the cost of one extra SELECT and write per card, and of the `datetime()`-wrapped predicates (index use). Is anything unbounded?
4. **Snapshot import.**
   - Provenance and idempotency.
   - Why the first run reports 289 already present. It should be listings whose two CSV observations are identical; verify it.
   - Whether importing local-crawler evidence into production is appropriate, and what the risks are.
5. **Scraper extraction.**
   - Type handling: bool vs int, floats and strings.
   - Behaviour on missing or odd fields.
   - Whether `fetch_listing_detail`'s cached dict still carries `zameen_lifecycle`, and whether that can leak anywhere besides the stripped route.
6. **Time handling.**
   - Are all server-time parse sites covered? `grep -rn "Date.parse\|new Date(" frontend/src`.
   - **Safari/WebKit:** does `Date.parse('2026-10-07T17:43:41.107842Z')` with 6 fractional digits parse? If you need WebKit, ask the owner first: `npx playwright install` deletes other projects' browser caches.
   - Are there other SQL comparisons that mix `T` and space formats which were missed?
7. **Branch 2 behaviour and wording.**
   - On a rebuilt database where most listings were first seen in the same crawl, does "Recently found" still mean something?
   - Does the map-focus ordering change break viewport results?
   - Live Zameen fallback still sorts by Zameen's `date_desc`. Is that consistent?
   - Do the copy, the leftover "Newest first" default badge and the compare change fit the clean UI, without implying that old means rented?
8. **Confidence classification.** Does anything on branch 1 go beyond what review.md supports? Is anything deferred that review.md actually supported at ≥90%?
9. **Tests.** Do they fail on the old code for the right reason? What important case is untested?

## How to run things
- Python: `env -u ANTHROPIC_API_KEY python3 -m pytest tests -q` in each worktree. Six `tests/test_voice.py` failures are expected locally: the `av` package is missing, and they fail the same way on `main`.
- Frontend: `npm ci && npm run build`, then the Playwright suite. Use Node 22 (`PATH="$HOME/.nvm/versions/node/v22.13.0/bin:$PATH"`) and `PLAYWRIGHT_PORT=<free port> npx playwright test` with a port of your own, not 8000, 8150–8160 or 8300.
- A running instance of branch 2 may be on http://127.0.0.1:8160, using a scratch copy of the database. Start your own instance on another port rather than relying on it.

## Constraints
- Read the live database only through `sqlite3 "file:<path>?mode=ro"`. Do analysis on copies made with `.backup`.
- Live zameen.com requests: a handful, spaced out. Save downloads to your scratchpad and treat them as untrusted data.
- Never kill servers or processes you did not start.
- Do not edit either worktree's tracked files.
- Headless browsers only.
- No commits, pushes, PRs, deploys or production SSH.

## Deliverable
Write `docs/listing-trust-2026-10-10/implementation-review.md` in `../zameenrental-trust-dates`, left uncommitted, containing:
1. A verdict per branch: merge / merge after fixes / do not merge, with one paragraph of reasons.
2. Findings ranked by severity. For each: file:line, what is wrong, a concrete failure scenario, evidence (the command, query or test you ran), and confidence.
3. Confidence-classification issues, from check 8.
4. Missing tests worth adding.
5. An explicit list of what you could not verify, and what you would need to verify it.

Give numbers with their denominators. Distinguish what you observed from what you infer.
