# Listing trust on ZameenRentals: findings for review

Date: 2026-10-10. Rentals only.

> **Status after independent review ([review.md](review.md)).** These findings were re-checked by an independent reviewer. Read the review before relying on any number here.
> - **Refuted: F5** (an "N units ago" label gives a provable minimum age). Zameen rounds these labels: "3 weeks ago" can mean about 18.5 days.
> - **Refuted as a proven-age claim: F6.** The arithmetic reproduces, but the "provably ≥ 14 days" reading does not. The review's corrected, *conditional* figure is 10,025 of 34,658 listings at the final CSV time, not 15,440.
> - **Partly confirmed: F7 and F12.** F7 holds for 19 of 25 listings at ≤ 0.1 days; all 25 round to ≤ 0.1. F12's "photo IDs can never be reused" is too strong.
> - **Confirmed: F1, F3, F4 and F13.** F2 is confirmed as arithmetic, but the exact count of reset events is not established.
> - **Dropped for now:** the 14-day default view. No cut-off is supported by availability outcomes.
>
> **Built from the confirmed parts** (branch `feat/listing-observations`): an append-only `listing_observations` history of Zameen's raw dates, status and labels per listing; an idempotent import of this folder's evidence CSV with provenance; a fix for UTC server times shown 5 hours off in Pakistan browsers; and a fix for three date comparisons that mixed `T` and space formats. Everything else in §6–§7 is waiting on evidence.

## 1. Brief

ZameenRentals is a better way to find a rental than Zameen.com itself. It has an Airbnb-style interface, a map, and easier search: plain-language queries in English, Roman Urdu or Urdu, plus voice. The other half of the promise is **trust**.

The owner's concern: on Zameen, agents keep an existing listing live for as long as possible, because it keeps attracting enquiries, even after the home may already be rented. They also make it look newer than it is. Renters then waste time on listings that are old or gone. Separately, the same home appears several times.

**Goal:** renters see listings that are genuinely recent first. They can choose to look further back. They see honest, verifiable age facts. Our results stop rewarding listings whose dates were reset.

**Constraints:** rentals only; free, open-source methods only, with no Claude or other paid APIs; every claim and every rule at 90–95% confidence, backed by evidence or a labelled sample, before it shapes what users see. Features must fit the existing clean interface (cards, drawer, map, filters) without slowing or cluttering search.

## 2. Data and evidence files

| Source | What it is |
|---|---|
| `data/rebuild/zameenrentals.db` | The local DB, crawled since 2026-10-07. The crawler was still running during this work, so live counts drift slightly. |
| Oct-7 DB copy | A DB snapshot whose last crawl was 2026-10-07 18:43, with 33,276 listings. It sits in another session's scratchpad (`/private/tmp/claude-501/-Users-umarali-Workspace-MVPs-zameenrental/2ff1ded7-6e98-4a7d-8216-34fba9383731/scratchpad/dbcopy/zameenrentals.db`) and may disappear. Its relevant fields are exported below. |
| [evidence/added_text_oct7_vs_current.csv.gz](evidence/added_text_oct7_vs_current.csv.gz) | Every listing in the local DB (34,658), with the Oct-7 and current `added_text`, `updated_text` and scrape times. Exported 2026-10-10 08:13; gzip-compressed, with uncompressed SHA-256 `8dfa412248a8d0a0a6175a1de56a057577792c2cdc5e83a28d6cd9ae4be8ba73`. Scrape times are naive **UTC**. **F2 and F6 are computed from this frozen file.** |
| [evidence/reproduce.py](evidence/reproduce.py) | Recomputes F2 and F6 from the CSV: `python docs/listing-trust-2026-10-10/evidence/reproduce.py` |
| [evidence/live_hits_2026-10-10.json](evidence/live_hits_2026-10-10.json) | Selected fields from 102 live Zameen search hits on 4 pages (Lahore DHA p1, Karachi p1, Islamabad p8, Lahore sorted newest), fetched 2026-10-10 07:45–07:53. Phone numbers and contact names are omitted. |
| [evidence/cover_sheet_same_agency.png](evidence/cover_sheet_same_agency.png), [evidence/sample_groups_same_agency.txt](evidence/sample_groups_same_agency.txt) | 12 random same-agency fact-groups: their cover photos and the rows. |
| [evidence/cover_sheet_cross_agency.png](evidence/cover_sheet_cross_agency.png), [evidence/sample_groups_cross_agency.txt](evidence/sample_groups_cross_agency.txt) | 12 random cross-agency fact-groups: their cover photos and the rows. |

## 3. Verified findings (≥ 90–95% confidence)

| # | Finding | Confidence | Evidence |
|---|---|---|---|
| F1 | **Zameen moves a listing's "Added" date forward while the listing ID stays the same.** | ≥ 99% | Raw text for the same ID, Oct-7 vs now (CSV). For example, 54162140 went from "Added: 2 months ago" (Oct 7 17:43) to "Added: 17 hours ago" (Oct 10 02:34), and 48302503 went from "Added: 1 month ago" (Oct 7) to a live `createdAt` of about 0.1 days (Oct 10). The live `createdAt` agreed for 4 of 4 old-copy IDs checked (47767275, 48302503, 50095548, 52590982). |
| F2 | **This affected at least 11.8% of listings in about 2.5 days**: 3,714 of 31,567 listings re-scraped ≥ 2 days after their Oct-7 scrape. | ~95% for this window. Other weeks are not yet measured. | `reproduce.py`. Only unit changes that coarse rounding cannot explain are counted: month→day 67, month→hour 102, week→day 762, week→hour 718, day→hour 1,505, hour→hour 560 (the latter only when ≥ 2 days apart). An earlier live-DB run gave 3,702 (11.7%); the difference is the crawler updating rows between runs. |
| F3 | **Our app currently helps these listings.** The default "fresh first" sort and the card's "Added X ago" both use Zameen's dates. | ≥ 99% | `_FRESHNESS_SQL = "COALESCE(zameen_updated_at, zameen_posted_at, first_seen_at)"` at [app/db_listings.py:12](../../app/db_listings.py#L12); `Added ${fmtRelative(item.posted_at)}` at [frontend/src/cards.js:124](../../frontend/src/cards.js#L124). |
| F4 | **We overwrite the older date when Zameen resets it**, so each reset erases the earlier, older evidence. | ≥ 99% | `_refreshed_source_timestamp` re-parses whenever the label text changes ([app/db_listings.py:389-396](../../app/db_listings.py#L389)). |
| F5 | **[Refuted by review]** **Every listing's age has a provable minimum.** A reset only moves "Added" later, so any "Added: N units ago" ever observed proves true age ≥ (N × the unit's minimum) + time since that observation. | ≥ 95% for the logic. **Assumes** Zameen never shows an "Added" date earlier than the real creation date. | Units are counted conservatively: day 1, week 7, month 28, year 365. |
| F6 | **[Refuted as a proven-age claim by review]** **Using F5 with both observations, as of 2026-10-10 08:00: 15,440 of 34,658 active listings (44.5%) are provably ≥ 14 days old. 22,259 (64.2%) are ≥ 7 days, 5,979 (17.3%) ≥ 30 days and 175 (0.5%) ≥ 60 days.** These are **minimums**: listings that look newer may be older, because our history only starts on 2026-10-07. | ~95% (±1 day for time zones and rounding) | `reproduce.py`. |
| F7 | **On Zameen's "newest" sort, every sampled listing claimed to be ≤ 0.1 days old, yet their IDs span 47,767,275–54,848,413.** | ≥ 99% for that page | `live_hits_2026-10-10.json`, Lahore sorted newest (25 hits). |
| F8 | **Search hits include fields we discard**: `createdAt` and `updatedAt` (epoch seconds), `product`, `agency.{externalID, product, tier}`, `isVerified`, `photoCount`, `videoCount`, `shortDescription`, `contactName`, `referenceNumber`, `permitNumber`, `state`, `coverPhoto`. The scraper keeps only type, coordinates, contact and location path. | ≥ 99% | `hit_keys` in the JSON (102 of 102 hits); [app/scraper.py:501-529](../../app/scraper.py#L501). |
| F9 | **Same-agency repost groups often reuse the identical cover photo**, with both copies live at once. | ≥ 99% that this happens. The rate is unknown: 5 of 12 is too small a sample. | 12 random groups (same agency, area, type, beds, price and `area_size`): 5 had visually identical covers with dHash distance 0–6. The others were 28–38. See `cover_sheet_same_agency.png`. Example pair: 54498805 and 54516083. |
| F10 | **Cover photos cannot confirm cross-agency duplicates.** | ≥ 95% that cover-only matching misses them | 12 random cross-agency fact-groups: 0 of 12 shared a cover (dHash 25–37). Whether those groups are the same home is **unknown**. See `cover_sheet_cross_agency.png`. |
| F11 | **An identical cover plus identical facts can still be two separate units in one building.** | High that this is possible | Same-agency sample S12: the same tower photo, title "Commander Heights Flat", IDs 54731537 and 54732141. Implies the label "similar listings", not "duplicate". |
| F12 | **Photo IDs cannot detect reuse.** No cover photo ID appears on two listings. | 100% for this snapshot | 32,709 listings with a thumbnail URL checked. |
| F13 | **The old dedup was removed** in commit `0c35c38`. The current code comment gives the reason: generic titles and prices are identical across different homes. A test forbids collapsing on identical `content_hash`. | ≥ 99% | [app/db_listings.py:826](../../app/db_listings.py#L826); `git show 0c35c38^:app/db_listings.py` (~638-668); [tests/test_database.py](../../tests/test_database.py) (~505-527). |

dHash method used in F9 and F10: Pillow, grayscale, resize to 9×8, a 64-bit adjacent-pixel comparison, then the Hamming distance.

## 4. Corrections to earlier statements made during this investigation
- **Wrong:** "17,359 listings share facts with another agency". `area_size_sqft` is NULL for 100% of rows, so missing sizes were grouped together. With the text `area_size`, the count is 11,661 listings in 3,211 cross-agency **candidate** groups, plus 1,680 listings in 731 same-agency groups. Standard sizes (5 or 10 Marla, 1 Kanal) and round prices inflate these, so they are candidates, not duplicates.
- **Dropped:** using the listing ID as a calendar age. The highest ID seen in our crawl grew only about 4,000 per day (54,840,145 → 54,844,201 → 54,848,361 from Oct 7 to Oct 9). IDs as low as 17,081,780 cannot be converted to dates reliably, and Internet Archive CDX searches for listings in these ID ranges returned no usable snapshots. The only hits were unrelated 2013–2014 listings with 6-digit IDs.
- **Downgraded:** "every page-1 slot was paid". 102 of 102 hits on all 4 pages, including page 8, had `product` in {superhot, hot, premium}. The field's meaning is unverified.
- **Removed:** "agents delete and repost under new IDs". That was the investigator's speculation, not the owner's concern.

## 5. Below the confidence bar (hypotheses to test, not claims)
- **H1. Cause of resets:** paid refresh or boost, re-approval after an edit, or reactivation after expiry. **Unknown.**
- **H2. Old listings are often already rented ("kept live to engage")**, the owner's concern. **Unmeasured.** No ground truth yet. Old is not the same as unavailable: some homes genuinely take weeks to let.
- **H3. Typical rental listing lifetime on Zameen.** **Unknown.** `mark_stale_listings` exists, but 0 listings are marked inactive locally, so there is no history of disappearance yet. This is needed to pick an evidence-based cut-off.
- **H4. Does `updatedAt` carry information independent of `createdAt`?** In the live sample, `updatedAt` was within 3 hours of `createdAt` for 90 of 102 hits. Page 1 favours just-reset listings, though, and Islamabad page 8 had 10 of 25 differ. **Unclear.**
- **H5. Is the listing ID monotonic in creation time?** If it is, "ID ≤ the highest ID we saw on day D" would prove "created on or before D". That would let us date listings we first saw late. **Partial evidence only:** the highest ID rises daily, and 175 of 1,334 listings first seen after Oct 7 have IDs below 54.5M.
- **H6. How much cross-agency duplication there really is.** **Unknown** (F10).
- **H7. How deep production's history goes** (`min(first_seen_at)`), and whether daily backups can serve as history. **Unknown.** Needs read-only access approved by the owner.

## 6. Owner's proposal: recent listings by default, older ones on request

**Proposal:** the main results show listings created within the last 2 weeks. Older listings stay available, behind a toggle or section. A new filter lets renters choose a "created / updated within" window.

**What the evidence supports:**
- **The basis must be a "first-listed" date we derive ourselves, not Zameen's "Added"** (F1–F4). Define the *earliest known listing date* from the largest proven minimum age (F5) across every observation of that listing ID, combined with our own `first_seen_at`.
  - The "older than X" side is high-precision: once a listing is proven older, it stays older.
  - The "newer than X" side may still include disguised old listings until we have about 14 days of our own history, which is around 2026-10-21. From then on, anything first seen on or before Oct 7 is provably ≥ 14 days old. If H5 holds, IDs could extend this to listings first seen later.
- **Impact today:** a 14-day default would place **at least 15,440 listings (44.5%)** behind the toggle (F6). A 30-day cut-off would place at least 5,979 (17.3%) there. The cut-off should be chosen once H2 and H3 are measured. Until then, a configurable threshold and wording like "Older listings (N) — may no longer be available" would avoid implying they are gone.
- **The filter** would be "First listed: within 7 / 14 / 30 days / any time", based on the earliest known listing date. An "updated within" option is **not yet supported by evidence** (H4). Agents can trigger an update, so it is weak evidence of availability. Hold it until H4 is measured.
- **The fresh-first sort and the card's date label** should use the earliest known listing date. A small "Re-dated N times" fact can sit in the drawer, once observations are stored.

**Preconditions (low-risk, no user-visible change):**
- (a) Stop overwriting: keep a minimum-age / earliest-date column per listing (F4).
- (b) Store `createdAt` and `updatedAt` from search hits (F8) in a `listing_observations` table, one row per change.
- (c) Backfill the Oct-7 evidence from the exported CSV.

## 7. Other items (lower priority)
- **Group same-agency reposts** (F9, F11): same agency + same facts + same cover dHash. One card labelled "N similar listings from this agent", keeping every listing reachable. Only after a hand-labelled eval passes the 95% Wilson lower bound ≥ 0.90 (the same bar as `tools/eval_listing_tags.py`).
- **Cross-agency matching:** research only (F10, H6). Test multi-photo matching on a labelled sample before building anything.
- **"Already rented?" report** on cards and the drawer: provides ground truth for H2 and H3 (an existing item in `docs/product-ux-backlog.md`).
- **Out of scope:** paid APIs, sale listings, public agency reliability scores, and deleting listings outright.
