# Independent review of listing trust

Reviewed 2026-10-10. Repository HEAD `e9506fc6eb513173c412f4cd2631111aff3cd3ab`. Application code, databases and existing evidence were not changed. No paid APIs, application imports, commits, pushes, PRs, deployment, production SSH, messages to agents, or browser sessions were used. Production is DigitalOcean, per the owner's correction and commit history; the Heroku line in `CLAUDE.md` is stale.

## 1. Verdict

Preserve observation history now, but do not launch the proposed 14-day default or call the derived date "first listed." The same advertisement ID does acquire a later displayed date, and our sorting rewards that change. However, the proposed minimum-age formula is wrong: Zameen rounds ages, and an observed "3 weeks ago" can mean about 18.49 days. The frozen arithmetic reproduces, but its "provably old" interpretation does not. Applying the currently served formatter to the frozen evidence puts 10,025/34,658 listings beyond 14 days, conditionally, rather than 15,440/34,658. Neither figure measures rented homes. Photo reuse exists within and across agencies, but photographs and matching facts do not establish a unique rental unit. Keep all inventory accessible, separate dates observed by us from dates reported by Zameen, and measure availability before choosing a default cut-off.

## 2. Evidence scope and finding audit

Confidence below is reviewer confidence in the narrow verdict, not a calibrated probability of availability or an estimated market-wide rate. Deterministic counts have no sampling uncertainty within their stated files; they still have measurement and selection limitations. "Not established" means the evidence cannot meet the owner's 90–95% bar.

Sources used:

- Frozen CSV: 34,658 rows, all marked active, SHA-256 `8dfa412248a8d0a0a6175a1de56a057577792c2cdc5e83a28d6cd9ae4be8ba73`. Oct-7 observation times span 05:56:24–18:43:13 UTC. Current observations span Oct 7 05:56:24 through Oct 10 03:13:45.373781 UTC, or 08:13:45 PKT. An old row is absent for 1,382/34,658 IDs.
- Both databases still existed. I read each through a SQLite `file:...?mode=ro` URI, with a read transaction, and saved selected non-contact columns to scratch. At 03:41:50 UTC, 08:41:50 PKT, the current capture contained 34,660 listings, all active; the Oct-7 copy contained 33,276. All 33,276 exported old label/time records matched the old database. The current capture differed from the CSV in at least one label/time field for 8,632/34,658 IDs. Do not mix the two denominators.
- Original four saved HTML pages survived in the investigator's scratchpad. Their embedded hits and visible labels were inspected independently, alongside the exported JSON. The JSON has 102 hit occurrences but 100 distinct IDs.
- New requests: two search pages at 08:42 PKT and two fixed detail pages at 08:45 PKT, separated by three seconds; one JavaScript asset; bounded, sequential thumbnail downloads for the selected image sample. All downloads stayed under `/private/tmp/zameen-trust-review/`. No downloaded JavaScript was executed.
- Scripts and exact invocations appear in §8. Scratch artifacts are temporary, not durable repository evidence. Core counts, counterexamples, sample IDs and distances are recorded here so the conclusion does not depend on retaining raw downloads.

| Finding | Verdict | Confidence | Evidence command or query | Notes |
|---|---|---|---|---|
| F1: same-ID Added dates move forward | Confirmed for the displayed/source date | ≥99% for existence; cause unestablished | `python3 /private/tmp/zameen-trust-review/audit.py`; SQL join Q1 below; `python3 /private/tmp/zameen-trust-review/diff_hits.py` | CSV ID 54162140 changes from 2 months on Oct 7 17:43 UTC to 17 hours on Oct 10 02:34 UTC. Original live `createdAt` is later than the old observation for all four cited IDs. This proves a date discrepancy for an existing ID, not agent intent, original property creation, or unavailability. |
| F2: 3,714/31,567 reset | Partly confirmed | ≥99% arithmetic; ≥95% that many source dates changed; exact event count not established | `python3 docs/listing-trust-2026-10-10/evidence/reproduce.py`; independent `audit.py` with full-match parsing | Exactly 3,714/31,567 = 11.765451%, in paired intervals of 2.054021–2.720469 days. Six transition counts reproduce: 67, 102, 762, 718, 1,505, 560. Eight flagged hour→hour pairs have identical text, which can mean a reset or stale text. Excluding those gives 3,706/31,567 = 11.740108%, still not a verified causal-event rate. Live capture gives 3,725/31,568, separately. |
| F3: app rewards source dates | Confirmed, with scope correction | ≥99% | `sed -n '1,16p;389,423p;795,855p;1060,1095p' app/db_listings.py`; `sed -n '94,133p' frontend/src/cards.js`; `sed -n '210,221p' frontend/index.html` | Default non-map order uses source Updated, then Added, then first seen. Map focus can rank distance first. Card Added uses posted_at; desktop also shows Updated. Current sort copy is "Default" / "Newest First", not literally "Fresh first". "New" uses first_seen_at and means new to this visitor. |
| F4: earlier source date is overwritten | Confirmed, with scope correction | ≥99% | `sed -n '389,423p;514,595p' app/db_listings.py`; `sed -n '96,133p' tests/test_database.py` | Changed labels replace parsed timestamps even for unchanged content_hash. Earlier source-age evidence disappears from this row, but first_seen_at and an external backup can survive. Ordinary rounding changes also reparse; not every timestamp change is a reset. |
| F5: N×unit is a provable minimum | Refuted as written | ≥99% | `python3 /private/tmp/zameen-trust-review/html_audit.py`; `python3 /private/tmp/zameen-trust-review/validate_format.py`; formatter inspection Q4 | 54774171 says 3 weeks at 18.488240 days since createdAt; 54284282 says 3 days at 2.701561 days. Rounded labels can imply an earlier date than the underlying timestamp. Formatter uses round:true, not floor. Even corrected source bounds still assume a truthful source timestamp, consistent ID identity and no backdating/import bug. |
| F6: 15,440 are provably ≥14 days | Partly confirmed arithmetic; refuted as a proven-age claim | ≥99% in this distinction; revised age interpretation conditional | `reproduce.py`; `python3 /private/tmp/zameen-trust-review/rounding.py` | The reported 22,259 / 15,440 / 5,979 / 175 counts reproduce at the script's naive 08:00. Revised values and clock correction are in §3. No verified availability denominator exists. |
| F7: newest page all ≤0.1 days | Partly confirmed | ≥99% for ID range and revised calculation | `html_audit.py`; saved `lahore_newest.html` plus its mtime | IDs span exactly 47,767,275–54,848,413. At the saved page's 02:53:51.552795 UTC file time, age spans 0.006360565–0.113710102 days; only 19/25 are ≤0.1. All round to at most 0.1 at one decimal. The numerical claim was over-rounded; IDs alone are not a creation clock. |
| F8: useful hit fields discarded | Partly confirmed | ≥99% | `sed -n '384,405p;501,532p' app/scraper.py`; key count Q5 | createdAt/updatedAt and the other listed top-level keys except agency occur in 102/102 hit occurrences. agency is actually present in 95/102; export placeholders obscure the missing seven. The enrichment path keeps type, coordinates, contacts, agency name and location path, but not those timestamps or stable agency ID. Photos and other card fields also enter through HTML, so "discard" is specific to the state enrichment path. |
| F9: same-agency cover reuse | Confirmed existence; "repost" identity unproven | ≥99% for observed image reuse; no reliable population rate | `python3 /private/tmp/zameen-trust-review/photos.py --fetch`; `extra_photos.py`; visual inspection, §4 | Original sheet visibly has five matching-cover groups out of twelve. Independent 30-group sample and every selected cover were inspected. Image reuse establishes neither a unique home nor a delete/repost sequence. "Live" here means local active rows, not availability confirmed at source. |
| F10: covers cannot confirm cross-agency duplicates | Partly confirmed as a caution; detection/recall claim unsupported | ≥99% that covers alone do not prove unit identity; recall unmeasured | Same image audit, cross-agency groups | Original 0/12 cannot estimate missed duplicates without positive ground truth. New C28 has a reused cover across agencies, dHash 1. Cover matching can find candidates across agencies; its duplicate precision and recall remain unknown. |
| F11: same photo/facts can cover separate units | Partly confirmed | ≥95% as a failure mode; the cited pair's unit identity unestablished | Original S12 and new S14 inspected; sample manifest | 54731537/54732141 share a tower exterior and dHash 0. Nothing observed proves that these are different flats, or the same flat. Shared building photos cannot decide either way. New S12's titles describe different exact square-foot areas despite equal coarse area_size, further weakening fact identity. |
| F12: photo IDs cannot detect reuse | Partly confirmed | ≥99% for captured URL-ID uniqueness; universal claim refuted | `audit.py`, regex `/thumbnails/(\d+)-`; Q6 | Current capture has 32,710 thumbnail URLs and 32,710 unique extracted IDs, zero collisions, plus 1,950 other URLs. Original 32,709 was a different moving snapshot. Different IDs can reference matching pixels, as the sheets show. An equal asset ID could still help in future; this does not prove IDs can never be reused. |
| F13: old dedup removed | Confirmed | ≥99% | `git show 0c35c38 -- app/db_listings.py tests/test_database.py`; `git show 0c35c38^:app/db_listings.py` | GROUP BY/content_hash collapse and repost_count were removed; regression test requires both source IDs to survive. The frontend's old "same listing" repost badge remains, but normal current search does not supply the count. Do not revive that wording for similarity groups. |

## 3. New findings and attempts to falsify the interpretation

### Rounded dates change the proposed decision rule

The [served Zameen desktop bundle](https://www.zameen.com/assets/main.desktop.6977e9b1c94e25b4.js), SHA-256 `6407eeba3a6981a9871e1efbeddb1b43f0748c389a3942a16863b6e78c660337`, renders card ages with `largest:1`, units `mo,w,d,h,m`, and `round:true`. Its unit measures include 2,629,800,000 ms per month, 604,800,000 per week and 86,400,000 per day. It rounds and carries lower units, so simply subtracting half a unit is not exact either. I transcribed the numeric formatter into scratch Python and checked all 102 saved visible card labels against their embedded createdAt values and file times: 102/102 matched. This establishes the observed formatter, not every historic Zameen client or a contractual guarantee about timestamps.

Examples of derived lower boundaries under that formatter:

| Label | Original assumed minimum | Formatter's lower boundary in days |
|---|---:|---:|
| 1 day | 1 | 0.9788194444444445 |
| 2 weeks | 14 | 10.478819444444445 |
| 3 weeks | 21 | 17.478819444444447 |
| 4 weeks | 28 | 24.478819444444447 |
| 1 month | 28 | 30.436875 |
| 2 months | 56 | 47.91569444444445 |

The month rule is therefore not uniformly conservative. This is a multi-day issue, not ±1 day noise. An honest minimum-age derivation must retain a source-dependent interval and its method/version. Do not freeze a bad lower bound forever in a minimum-date column.

### The evidence mixes clock conventions

`upsert_listing` uses `datetime.utcnow()` and SQLite first_seen_at uses `datetime('now')`, both UTC without an offset. `reproduce.py` describes these as local times. Its naive 08:00 calculation is equivalent to 13:00 PKT when applied to these UTC values, beyond this review's initial capture. If the intended reference was 08:00 PKT, it should be 03:00 UTC, but 7,515/34,658 current observations occur after that reference. Using them is look-ahead. For an internally consistent comparison, use the final CSV observation time, Oct 10 03:13:45.373781 UTC, or 08:13:45 PKT.

The following are counts of listings conditionally classified as old by labels, not verified original creation dates or rented inventory. Each denominator is 34,658 active CSV rows. All original and current labels parse under a strict full-match grammar, 33,276/33,276 old labels and 34,658/34,658 current labels. No combined Added/Updated strings or unparseable labels were found.

| Cut-off | Original algorithm at naive 08:00 | Corrected formatter at the same 08:00 UTC, isolating rounding | Corrected at final CSV observation time | Inventory remaining at final CSV time |
|---|---:|---:|---:|---:|
| ≥7 days | 22,259 | 21,154 | 18,909/34,658 = 54.558832% | 15,749/34,658 |
| ≥14 days | 15,440 | 10,025 | 10,025/34,658 = 28.925501% | 24,633/34,658 |
| ≥30 days | 5,979 | 4,709 | 4,709/34,658 = 13.587051% | 29,949/34,658 |
| ≥60 days | 175 | 175 | 175/34,658 = 0.504934% | 34,483/34,658 |

At the final CSV time, 14-day conditional counts by city are Karachi 2,853/8,537, Lahore 3,430/13,850 and Islamabad 3,742/12,271. Seven-day counts are 4,915, 6,913 and 7,081 respectively; 30-day counts are 1,352, 1,399 and 1,958. Local first_seen_at alone proves none of these rows was observed by this crawler ≥7 days earlier: 0/34,658 at every cut-off in the table. The crawler's history is only about three days long. Thus even the corrected table relies on source labels and must not be presented as independently proven creation ages.

The corrected calculation is a sensitivity estimate. Applying the current formatter retroactively assumes the Oct-7 pages used the same formatter. Their raw HTML was not available for every CSV row, nor are per-label observation timestamps retained. The mathematical boundaries are reproducible; historical measurement validity is not established at 95% for every row.

### Source dates can differ by page type and by meaning

The same bundle has a detail-page absolute-date renderer using `reactivatedAt || createdAt`, a relative creation-date renderer using createdAt, and a last-updated renderer using the greater of updatedAt and reactivatedAt. Those are different semantics, even before our parser intervenes. Two live detail responses exposed this omitted field:

| ID | createdAt, UTC | updatedAt, UTC | reactivatedAt, UTC | Visible relative Added |
|---|---|---|---|---|
| 54162140 | 2026-10-09 09:11:19 | 2026-10-09 09:11:22 | 2026-05-04 05:55:41 | 19 hours at 03:45 UTC |
| 48302503 | 2026-10-10 00:10:51 | 2026-10-10 00:10:51 | 2023-12-12 04:31:11 | 4 hours at 03:45 UTC |

These are source-reported epochs, not verified original publication dates. In particular, reactivatedAt being older than createdAt in both cases makes "last reactivation" an unsafe interpretation from the field name alone. Store the raw field and page type; investigate its lifecycle. Do not replace the existing guessed creation date with another guessed creation date. The absolute renderer's existence is code evidence; I did not observe an absolute date displayed in these two fetched detail pages.

### Innocent explanations that remain viable

| Explanation | What this review can test | Consequence for the proposal |
|---|---|---|
| Added means current marketing/activation episode, not original advertisement | Consistent with old IDs and recent createdAt, but mechanism not proven | Call it "Zameen's Added date". Keep first observation separately. Treat a verified new vacancy as a new availability episode without erasing ID history. |
| The home was rented and later became vacant again | No tenancy outcomes or episode history | Permanent age demotion could hide a genuinely fresh rental. A first-ever date cannot substitute for an availability date. |
| Edit, renewal, approval, migration or import changed timestamps | No before/after write audit; old source dates survive in backups | Record state/product/content changes and exact epochs. Say "source date changed," not "agent re-dated N times" or fraud. |
| Stale cached HTML, different page types, or missing Added in a later scrape | Code explicitly preserves old added_text while advancing card_scraped_at when Added is absent | The CSV can attach an old label to a newer observation clock. Capture per-field observed_at and source URL. F2's exact event incidence remains provisional. |
| Rounding or timezone alone | Can explain small apparent movements, and invalidates F5/F6 | Cannot explain the large month→hour examples or an epoch later than an already observed ID. F1 survives. |
| An ID was repurposed for another home | Not ruled out by fact or source-ID matching | Evidence applies first to the advertisement ID. Track content revisions and do not claim continuous identity of a home without validation. |

There is also a recency drift issue without deliberate resets. An unchanged relative label preserves an old parsed timestamp, while a changed label reparses against now. The stored posted_at can be stale in one case and shift due to rounding in another. A source-epoch change is a better event signal than a change in human-readable label.

### Other code and evidence issues

- Timezone display bug: `fmtRelative` calls `Date.parse` on the naive UTC timestamps. In a Pakistan browser, `2026-10-10T00:10:51` means local time, five hours earlier than `2026-10-10T00:10:51Z`. I reproduced this with Node under `TZ=Asia/Karachi`. It can make listings look five hours older. Normalize UTC serialization before adding another date label.
- Staleness SQL compares ISO strings containing `T` against SQLite strings containing a space. On the cut-off date, this can defer expiry until the next day. Read-only counterexample: text comparison returns 0 while datetime comparison returns 1, Q7. This does not explain the current zero inactive count: all 34,660 captured rows are younger than the seven-day observation threshold.
- `mark_stale_listings` is a seven-day crawl-absence heuristic, not a rental outcome. It runs in the full crawl cleanup path. Interrupted/incomplete coverage, ranking changes, errors, or restricted crawl depth can all create censoring. Disappearing from one page is not disappearing from Zameen.
- The prior backlog still calls content_hash groups "~28% reposts" and recommends collapsing them. That conflicts with the removed dedup logic and this evidence. Treat those entries and their old production counts as superseded hypotheses, not implementation authority. Do not make freshness/grouping a frontend-only filter: page totals, map counts and pagination must use the same server predicate.
- `listing_tags` is useful as a side-table/join pattern, but its update trigger deletes tags when source content changes. Observation history must survive edits. Copying its invalidation behavior would destroy the evidence this proposal needs.
- In the fixed read capture, 6,001/34,660 stored posted_at values are later than first_seen_at. This confirms source-date/observation divergence at scale, but parser rounding and crawl timing also contribute; it is not 6,001 proven reset events.

## 4. Independent photo sample

I sampled 30 groups from each of two mutually exclusive pools in the frozen 03:41:50 UTC read capture. A fact key is city, area_name, property_type, bedrooms, price and text area_size, with no missing key or agency name. Same-agency groups have one distinct agency name; cross-agency groups have at least two. Pools are 735 same-agency groups containing 1,689 rows, and 3,215 cross-agency groups containing 11,671 rows. The difference from the original 731/3,211 counts is snapshot/eligibility drift, not evidence of a duplicate rate. All 34,660 captured area_size_sqft values are NULL, confirming the earlier correction.

For repeatability, sort group keys by their Python repr, then use `random.Random(20261010).sample(groups, 30)` separately for each pool. Inspect every cover in each selected group. This yielded 72 same-agency rows and 106 cross-agency rows, 178/178 images inspected, with no failed downloads. I computed 59 within-group same-agency distances and 363 cross-agency distances. For the latter, pairs with equal agency names are excluded. Agency names are an imperfect substitute for stable IDs, so these are name-based categories.

Hash method: Pillow grayscale, BICUBIC resize to 9×8, compare adjacent pixels with `left > right`, then Hamming distance over 64 bits. This pins the resize method missing from the original description. Hash distance is a screening measure, not a probability that two homes are identical.

Four of 30 same-agency groups contain a visually reused cover at distance ≤6: S14, S20, S22, S25. Two use building exteriors/entrances, and two use interiors. One of 30 cross-agency groups, C28, contains a reused interior cover, distance 1: 54718515 from Madina Associates and 54736589 from AL AHAD REALTOR Real Estate Consultant. Every other cross-agency pair has a distance above 6. Some different photos plausibly show another view of the same property, including S18's facade. That possibility cannot be counted as a confirmed same-unit match.

These fractions describe selected fact-groups with reused covers, not duplicate homes. For reference only, unweighted two-sided 95% Wilson intervals are about 5.31–29.68% for 4/30 and 0.59–16.67% for 1/30. They ignore correlated agencies and the construction of candidate groups, and do not estimate market-wide duplication. The initial first-pair-only inspection found 3/30 same-agency matches; inspecting all group members added S25. Reporting only one pair would have understated group-level reuse.

S12 deserves a separate negative example. IDs 53634520 and 53634549 have dHash 10 and similarly finished rooms, but their titles say 1,743 versus 1,728 square feet. Identical coarse area_size and price are not identical unit facts. C19 also contains two identical map placeholders from the same agency; maps must never count as evidence of the same home.

The manifest below records every selected ID. "Range" includes all evaluated distances in the group; cross-agency ranges exclude within-agency pairs. "Different views" means no reused cover established, not that the homes are different.

| Group | Listing IDs inspected | First sampled pair dHash | All eligible pair distances, min–max | Visual assessment |
|---|---|---:|---:|---|
| S01 | 53832437, 53832461 | 29 | 29–29 | Different views |
| S02 | 54611334, 54611358 | 30 | 30–30 | Different views |
| S03 | 45114480, 45129011, 45625682, 45647546, 45895798 | 32 | 24–40 | Different views |
| S04 | 54137028, 54349643 | 30 | 30–30 | Different views |
| S05 | 54575235, 54834790 | 28 | 28–28 | Different views |
| S06 | 54592227, 54713554 | 32 | 32–32 | Different views |
| S07 | 53564985, 53692262, 53859359 | 27 | 27–34 | Different views |
| S08 | 54778268, 54778398 | 28 | 28–28 | Different views |
| S09 | 43951744, 45352711 | 32 | 32–32 | Different views |
| S10 | 53408409, 54205647 | 25 | 25–25 | Different views |
| S11 | 54732016, 54780497 | 35 | 35–35 | Different views |
| S12 | 53634520, 53634549 | 10 | 10–10 | Similar rooms; titles state different exact sizes |
| S13 | 54813785, 54843820 | 26 | 26–26 | Different views |
| S14 | 54731537, 54732141 | 0 | 0–0 | Reused building exterior/entrance |
| S15 | 26231625, 26231871 | 38 | 38–38 | Different views |
| S16 | 53674968, 54611548, 54840407 | 28 | 26–32 | Different views |
| S17 | 52590982, 53894740, 54635244 | 34 | 26–34 | Different views |
| S18 | 52579063, 52590720 | 24 | 24–24 | Similar facade, different shots; same unit unverified |
| S19 | 54486272, 54486338, 54486349 | 29 | 22–29 | Different views |
| S20 | 54742442, 54842316 | 0 | 0–0 | Reused interior cover |
| S21 | 54643284, 54704002 | 28 | 28–28 | Different views |
| S22 | 54662453, 54846821 | 4 | 4–4 | Reused interior cover |
| S23 | 54738350, 54754032 | 36 | 36–36 | Different views |
| S24 | 54730483, 54730496 | 21 | 21–21 | Different views |
| S25 | 47918324, 49535739, 54571541, 54571689 | 35 | 0–35 | Reused building exterior/entrance |
| S26 | 52762338, 54340279, 54596207, 54622086 | 32 | 22–35 | Different views |
| S27 | 54669751, 54672329, 54673132 | 22 | 12–22 | Different views |
| S28 | 48518618, 50025027 | 25 | 25–25 | Different views |
| S29 | 54457118, 54707334 | 34 | 34–34 | Different views |
| S30 | 54817456, 54834840 | 29 | 29–29 | Different views |
| C01 | 54376192, 54650566, 54754390 | 29 | 29–38 | Different views |
| C02 | 53593629, 54702290 | 32 | 32–32 | Different views |
| C03 | 54515928, 54528499, 54724896, 54725618, 54732170, 54788362, 54824419 | 30 | 20–40 | Different views |
| C04 | 53365930, 54437265, 54736712 | 34 | 26–34 | Different views |
| C05 | 45712831, 54662536 | 34 | 34–34 | Different views |
| C06 | 54728616, 54846721 | 38 | 38–38 | Different views |
| C07 | 54613574, 54646937 | 39 | 39–39 | Different views |
| C08 | 54701091, 54741329 | 24 | 24–24 | Different views |
| C09 | 54193485, 54410735, 54452153, 54458959, 54757437 | 20 | 20–43 | Different views |
| C10 | 51369489, 54845937 | 27 | 27–27 | Different views |
| C11 | 54684494, 54804699 | 39 | 39–39 | Different views |
| C12 | 54687777, 54750074, 54754397, 54792448, 54822993 | 33 | 30–44 | Different views |
| C13 | 54733409, 54800024, 54816468 | 35 | 31–35 | Different views |
| C14 | 54531708, 54831390 | 28 | 28–28 | Different views |
| C15 | 54591259, 54619420 | 35 | 35–35 | Different views |
| C16 | 53585694, 54763869 | 35 | 35–35 | Different views |
| C17 | 51435601, 54643177, 54846198 | 38 | 28–38 | Different views |
| C18 | 54126665, 54601874 | 39 | 39–39 | Different views |
| C19 | 53321718, 54715259, 54805433, 54805444 | 28 | 28–37 | Includes identical same-agency maps; not property evidence |
| C20 | 54594731, 54794905 | 30 | 30–30 | Different views |
| C21 | 53650649, 53985925, 54019711, 54709041 | 35 | 29–36 | Different views |
| C22 | 54834829, 54845345 | 31 | 31–31 | Different views |
| C23 | 52659373, 52746933, 53760289, 54339485 | 35 | 31–36 | Different views |
| C24 | 50743121, 51250651, 51377811, 51884142, 54310375, 54311278, 54327702, 54403859, 54473155, 54537304, 54544943, 54552471, 54598009, 54637653, 54668970, 54677607, 54680875, 54700654, 54722991, 54740808, 54746169, 54746513, 54806860, 54809723, 54839430 | 26 | 19–43 | Different views |
| C25 | 52619047, 53891531, 54839647 | 33 | 25–33 | Different views |
| C26 | 53410401, 53953971 | 29 | 29–29 | Different views |
| C27 | 54813013, 54813372 | 25 | 25–25 | Different views |
| C28 | 54718515, 54736589, 54743916 | 1 | 1–37 | Reused interior across agency names |
| C29 | 45336320, 54758370 | 34 | 34–34 | Different views |
| C30 | 53391905, 54631821 | 33 | 33–33 | Different views |

## 5. H1–H7: progress and remaining confidence

| Hypothesis | What I learned | Updated confidence and next cheap test |
|---|---|---|
| H1: cause of resets | New evidence of reactivatedAt and different date renderers, but no observed reset with a causal event. Re-fetching Islamabad p8 about 48.71 minutes after the old capture retained 14/25 old IDs; all 14 had unchanged createdAt, updatedAt, product, state, price, rooms, title, photoCount, videoCount, coverPhoto and agency. Lahore newest retained 0/25 after about 48.70 minutes. This is page turnover, not 25 deletions. Fixed ID 48302503 retained its original sampled createdAt on its detail page about 51 minutes later. | ≥99% that the extra field/renderers exist; confidence in any specific reset cause remains below the bar and not quantifiable from this sample. Follow fixed IDs, not page positions. At 0, 24 and 48 hours retain exact epochs, reactivatedAt, state/product/agency tier and hashes of title/price/photos, on the same page type. Compare both page types for any reset and treat a missing page hit as unobserved. No 24–48 hour series was completed here. |
| H2: old ads are already rented | Zero independently confirmed rental outcomes. Reports, active state and source dates cannot supply those labels. | Not established; no defensible percentage. Draw a random, city-stratified sample across <7, 7–13, 14–29, ≥30 days and unknown age. With owner-approved follow-up, record available / rented / withdrawn / uncertain and confirmation time, including nonresponse. Compare rates with intervals. Do not contact advertisers without separate authorization. |
| H3: typical rental lifetime | Rebuild history begins Oct 7 05:56 UTC. At capture, 0/34,660 inactive and 0/34,660 last seen more than seven days ago. This is expected for a three-day history, not evidence that stale marking is broken. | Not established. Confidence ≥99% in this local coverage fact, no lifetime estimate. Track repeated successful complete crawls; distinguish withdrawal, missed crawl and rented. Existing ads enter with unknown age and active ads are right-censored. Estimate separate source-visibility and availability durations rather than averaging first/last observations. |
| H4: updatedAt independent of createdAt | Original 90/102 hit occurrences differ by ≤3 hours, 12/102 by >3 hours; page breakdown 26/27, 24/25, 15/25 and 25/25 within three hours. New Islamabad page has 10/25 beyond three hours, newest Lahore 0/25. | ≥99% that the fields sometimes differ; no evidence either predicts availability. Keep "updated within" out of availability filtering. Next, measure update-only events across fixed IDs, then compare their confirmed availability with matched controls. Correlation between two dates is not validation of either. |
| H5: IDs monotonic in original creation | Current first-seen cohorts: Oct 7, 33,324 IDs, maximum 54,840,145; Oct 8, 695 IDs, maximum 54,844,201, with 180/695 at or below the previous maximum; Oct 9, 630 IDs, maximum 54,848,361, with 203/630 at or below the previous maximum; Oct 10 through capture, 11 IDs, maximum 54,848,464, with 5/11 at or below the previous maximum. | ≥99% that first discovery is not monotonic in ID. This does not refute monotonic allocation: delayed discovery explains lower IDs arriving later. Allocation monotonicity remains unestablished, so no ID-based calendar inference. A high ID seen on D only dates that ID; dating every lower ID needs proof against reserved ranges, imports, reassignment and delayed publication. A small observation sample cannot certify that universal rule. |
| H6: cross-agency duplication | One sampled cross-agency group has visually reused property imagery; the other groups lack unit-identity truth. Equal covers can also be generic building or stock images. | ≥99% cover reuse occurs; same-home duplicate prevalence and matching precision/recall remain unmeasured. Collect full galleries for a small labelled subset with clear negative cases from the same building, plus price-change and differing-size cases. Keep uncertain labels separate. |
| H7: production history and backups | Both local review sources start Oct 7. A read-only attempt on `data/zameenrentals.db` failed with "unable to open database file"; that path is not usable evidence of production. Local deployment/backup files establish intended setup, not successful retention. | Production depth remains unverified. Need an owner-approved read-only export of count/min(first_seen_at)/max(last_seen_at) by city, dated backup inventory, and at least one restored backup checked read-only. No SSH, cloud backup access, or production queries were attempted. |

The new sample advances H1/H4 but does not cross a reset over a day boundary. A practical next panel is the four previously checked reset IDs, 47767275, 48302503, 50095548 and 52590982, plus a few non-reset controls. Reuse the saved detail URLs where known; do not infer that an absent search hit is unavailable. Log actual HTTP UTC time, cache headers and response hashes. Three planned observations are a protocol, not a result or an active scheduled job.

## 6. Review of the owner's proposal

| Proposal element | Decision | Acceptance threshold and reasoning |
|---|---|---|
| "Earliest known listing date" from max minimum age | Change | Keep earliest verified observation of the source ID as an exact fact, and source-reported history as separately attributed evidence with uncertainty. A minimum age means creation occurred **on or before** a bound; it does not identify the creation date. First seen is also on-or-before evidence, not proof of recency. Validate any parser/interval rule against raw labels plus epochs; use a held-out sample with 95% Wilson lower precision bound ≥0.90 before it determines exclusion. Every displayed exact first-observation date must have a traceable record. |
| Created within two weeks by default | Drop for now | No cut-off among 7, 14 and 30 days is supported by availability outcomes. They would conditionally hide 54.558832%, 28.925501% and 13.587051% at final CSV time under the corrected model, while neither proving the rest recent nor proving the hidden homes unavailable. Keep all results reachable and start with optional date filtering. Before an availability-based default, require an independently labelled, representative evaluation; if the rule purports to remove unavailable homes at 90% precision, its two-sided 95% Wilson lower bound must reach 0.90. Also measure available homes hidden and results lost by city/area. |
| Older-listing toggle | Change | If an age preference is offered, use a single control and precise counts under current filters. Say "Include listings first seen more than 14 days ago" for first_seen semantics, not "may no longer be available" attached only to older ads. For all ages, drawer copy can say "Availability has not been confirmed." Unknown age must remain visible by default; not known old does not mean known new. |
| Created/updated-within filter | Change | Offer "First seen by ZameenRentals" with 7 / 14 / 30 days / any time, if users find that useful. All 34,658 frozen rows satisfy the first 7 days today, so this is initially a discovery filter with little selectivity. Do not relabel source estimates "created within". A genuinely verified-original-age filter needs unknowns and interval overlap handled explicitly. |
| Updated within | Hold | H4 establishes different fields, not availability. A future explicitly labelled "Zameen updated" preference could be honest, but cannot carry the trust promise without outcome validation. No availability threshold can be derived from the current 102 hits. |
| Fresh-first sort and card date | Change | Stop calling reset-prone dates genuine new listings. Prefer "Recently found" for first-observation order, and "First seen by us 7 Oct" on cards. Explain in the drawer that the ad may be older. Keep newest-to-us distinct from rental availability. Evaluate ordering with renters and preserve location/price sorts; a code-factual date does not by itself establish the best default ranking. |
| "Re-dated N times" drawer fact | Change | Say "Zameen's Added date changed" with observation dates and source timestamps. Count only observed transitions, never inferred lifetime totals, and do not count rounding changes as reset events. One event needs raw before/after evidence; no classifier percentage can replace that audit trail. |
| Minimum-date column | Change | A materialized derived bound can speed reads, but cannot be the sole evidence. Keep exact first observation separately; keep versioned, recomputable source bounds. Corrections must be able to retract a bad bound. Do not permanently punish a renewed vacancy for old source metadata. |
| listing_observations side table | Keep, broaden | Store UTC with offsets/epochs, source ID, URL/page type, observed_at, raw age text, createdAt, updatedAt, optional reactivatedAt and meaningful content/state changes. Retain per-field observation time. Keep successful seen-again observations or last_seen per unchanged version: one row only per change cannot measure crawl coverage or continued visibility. Keep failed-fetch/coverage evidence separately. Avoid storing unnecessary contacts or using paid tag APIs. |
| Backfill Oct-7 CSV | Keep with provenance | Idempotent import, exact source rows and original observation times, provenance/hash and parser version; no synthetic events between two snapshots. Preserve a durable raw copy before scratch backups disappear. Validate counts, ID joins, UTC handling and no overwritten first observation. Do not claim retrospectively observed exact creation dates. |

The proposed Oct 21 milestone needs qualification. A listing first seen Oct 7 at 18:43 UTC becomes observed-for-14-days at Oct 21 18:43 UTC, not at the start of Oct 21. Older listings newly discovered after that date remain possible indefinitely. Two weeks of crawler history never makes every later first discovery genuinely newly listed. Reactivated vacancies create a separate problem even when ad-ID history is complete.

Fit the UI into what already exists:

- Replace the existing card date line rather than adding another badge. The current New badge is a visit/discovery signal; clarify that meaning in its accessible text and drawer. Do not pile an age, freshness and reset badge onto the same photo.
- Put the date control in the existing More Filters panel beside sort, with one active chip when used. Use one state value for the chosen window and inclusion choice so toggle and filter cannot contradict each other. Clear/reset, saved searches, URLs and city switching need defined behavior.
- If a recent-only preference is selected, show the older count and an inline "Show older listings" action next to the results count. Avoid a second permanent section or warning banner. Add keyboard focus and text labels, and verify copy with Urdu/Roman Urdu users rather than assuming a terse English phrase communicates creation versus discovery.
- Apply the same filter before server pagination and to map pins, area counts and result totals. A frontend-only hide would create empty pages, inconsistent maps and incorrect counts. Similarity groups must preserve every source ID and any different contact option.

## 7. Other items, acceptance gates and revised order

| §7 item | Decision | Acceptance threshold | Riskiest assumption and cheap test |
|---|---|---|---|
| Same-agency grouping | Change: candidate links first; defer collapsed cards | For an automatic grouping claim, held-out group-level precision with two-sided 95% Wilson lower bound ≥0.90, agency/building-separated train/eval split, and no lost source IDs or contact options. If product requires 95% precision, use ≥0.95 instead. Evaluate complete groups, not only pairwise accuracy. | Shared photos identify the same rentable unit. Include tower exteriors, maps, stock imagery, same-floorplan flats, different exact areas and reused interiors in negative controls. Label unit identity independently; photo-reuse labels cannot validate a same-unit claim. Avoid transitive chains where A resembles B and B resembles C but A differs from C. |
| Cross-agency matching | Keep research-only, correct F10 rationale | Same precision gate before a public same-unit claim, plus measured recall on known positives. No public grouping based on this 30-group sample. | Different covers imply different homes, or matching covers prove the same home. Compare multi-photo matches against a small independently verified identity set; deduplicate agency aliases and preserve each contact. |
| "Already rented?" reporting | Keep, change its evidentiary status | Reports start as dated unverified assertions, not availability ground truth. No automatic hiding from one report. Before automated suppression, independently adjudicated suppression precision must meet the same Wilson gate, with recovery/appeal behavior tested. | Users report the wrong ad, repeat hearsay, or competitors abuse reporting. Ask what was learned and when; distinguish agent confirmed rented, unreachable, withdrawn and uncertain. Manually verify a small random sample of reported and unreported ads with owner-approved contact. |
| Paid APIs | Keep excluded | Zero paid/API-model calls in this work and proposed evidence pipeline | A cheap model score is treated as ground truth. Use recorded evidence and a labelled eval; no model is required for the current checks. |
| Sale listings | Keep excluded | Every imported observation retains purpose; samples and filters must be for-rent | Mixed-purpose imports contaminate age/availability rules. Check raw purpose in a small stratified sample and reject unknown purpose from rental-specific outcome evaluation. |
| Public agency reliability scores | Keep excluded | No release without identity resolution, outcome evidence and a separate review; no gate is met today | Shared stock, agency aliases and nonresponse become accusations. Keep any diagnostic agency aggregates private and evidence-linked. |
| Deleting listings outright | Keep excluded | Preserve source records/history; any future status decision must be reversible | Crawl absence is treated as proof the property is gone. Test a known active panel against missed-page/error scenarios. |

The `tools/eval_listing_tags.py` Wilson function uses z=1.96. Even 30/30 correct independent predicted-positive decisions has a lower bound of only 0.886483. With zero errors, 35/35 reaches 0.901096; 73/73 reaches 0.950006. These are mathematical minima, not sufficient sampling plans. Agency clustering, tuned thresholds, uncertain labels and weighted sampling reduce effective evidence. Our four same-agency image-reuse groups do not supply even four confirmed duplicate-unit labels. The grouping gate is not passed.

Revised order:

1. Preserve the existing raw evidence and fix the evidence model: UTC, source provenance, rounded-age intervals and immutable observations. Revise the stale backlog claims before another agent implements them. Do not import the listing_tags deletion trigger into history.
2. Check production crawl health and restore/read a backup, with approval for that access. Measure coverage failures and timestamp formats before releasing "seen today" UI. Keep this operational verification distinct from availability.
3. Make the existing card/drawer date language truthful, after timezone handling is corrected. Preserve all inventory and source IDs. A first-seen sort/filter can be tested as a discovery preference with honest wording.
4. Run the fixed-ID 24–48 hour panel and a small stratified availability study. Start structured reports as leads for investigation, with manual corroboration. Measure age-related availability and available inventory lost before choosing any default age cut-off.
5. Evaluate similarity links and only then collapsed groups. Cross-agency multi-photo research follows if it beats the labelled baseline. Do not use the original 12-group samples as acceptance evidence.

## 8. Commands, reproducibility and limits

The scripts below are analysis scratch files, not application changes. They use selected local data and public responses only. Exact invocations used:

```sh
python3 docs/listing-trust-2026-10-10/evidence/reproduce.py
python3 /private/tmp/zameen-trust-review/audit.py
python3 /private/tmp/zameen-trust-review/html_audit.py
python3 /private/tmp/zameen-trust-review/validate_format.py
python3 /private/tmp/zameen-trust-review/rounding.py
python3 /private/tmp/zameen-trust-review/diff_hits.py
python3 /private/tmp/zameen-trust-review/photos.py --fetch
python3 /private/tmp/zameen-trust-review/extra_photos.py
```

`audit.py` independently full-matches each age label, computes F2 transitions/elapsed times and F6 maxima, reads both databases in read-only transactions, checks the old export row-by-row, checks thumbnail URL IDs and groups first-discovery IDs by UTC date. Its saved read capture is `db_rows.json`, SHA-256 `c0d50b702a6210b06fca7796784138f36b5c3581a2fa64b5d1687e2fdbc52e10`. Re-running it against a moving database changes live counts. The immutable CSV results should not change.

`html_audit.py` JSON-decodes window.state as data and compares card labels with createdAt. `validate_format.py` compares the independently transcribed formatter to all 102 saved cards. `diff_hits.py` joins old/new search hits by externalID and compares the named fields. `photos.py` selects the reproducible sample and `extra_photos.py` evaluates all covers in the chosen groups. `full_photo_sample.json` contains every pairwise distance and raw sampled metadata; the complete group manifest and ranges are retained above. Contact sheets are `same_1.png` through `same_3.png`, `cross_1.png` through `cross_3.png`, and `extra_1.png` through `extra_3.png` in scratch.

Q1, direct old/current read-only join used in addition to the independently joined Python captures:

```sh
sqlite3 'file:data/rebuild/zameenrentals.db?mode=ro' "ATTACH DATABASE 'file:/private/tmp/claude-501/-Users-umarali-Workspace-MVPs-zameenrental/2ff1ded7-6e98-4a7d-8216-34fba9383731/scratchpad/dbcopy/zameenrentals.db?mode=ro' AS oct7; SELECT o.zameen_id,o.added_text,o.card_scraped_at,c.added_text,c.card_scraped_at FROM oct7.listings o JOIN main.listings c USING(zameen_id) WHERE o.zameen_id IN ('54162140','48302503','47767275','50095548','52590982');"
```

Q2, source and history inspection:

```sh
sed -n '1,80p;350,595p;785,855p;1060,1095p;1182,1195p' app/db_listings.py
sed -n '384,405p;501,532p;590,605p' app/scraper.py
sed -n '94,133p' frontend/src/cards.js
sed -n '23,40p' frontend/src/utils.js
sed -n '195,225p' frontend/index.html
rg -n 'sort|Fresh|Recent' frontend/src/filters.js frontend/index.html frontend/src/map.js frontend/src/state.js
sed -n '96,133p' tests/test_database.py
sed -n '110,134p' app/listing_tags.py
sed -n '376,410p' tools/eval_listing_tags.py
sed -n '620,650p' app/crawler.py
git show 0c35c38 -- app/db_listings.py tests/test_database.py
git show 0c35c38^:app/db_listings.py
```

Q3, read-only population/coverage query, separately from the 34,660-row capture. The later running DB had already reached 34,662 rows; inactive and >7-day counts remained zero:

```sh
sqlite3 'file:data/rebuild/zameenrentals.db?mode=ro' "SELECT count(*),min(first_seen_at),max(last_seen_at),sum(is_active=0),sum(last_seen_at < datetime('now','-7 days')),sum(datetime(last_seen_at) < datetime('now','-7 days')) FROM listings;"
```

Q4/Q5/Q6/Q7, inspect only text/data, not execute downloaded code:

```sh
python3 - <<'PY'
import json,re
from pathlib import Path
s=Path('/private/tmp/zameen-trust-review/main_asset.js').read_text()
for term in ['reactivatedAt','unitMeasures','largest:1','round:!0']:
    for m in list(re.finditer(re.escape(term),s))[:8]:
        print(term,s[max(0,m.start()-230):m.end()+230])
p=json.load(open('docs/listing-trust-2026-10-10/evidence/live_hits_2026-10-10.json'))
h=[x for page in p['pages'] for x in page['hits']]
for k in ['agency','createdAt','updatedAt','coverPhoto','product','isVerified']:
    print(k,sum(k in x['hit_keys'] for x in h),len(h))
rows=json.load(open('/private/tmp/zameen-trust-review/db_rows.json'))
ids=[m[1] for r in rows if (m:=re.search(r'/thumbnails/(\d+)-',r['image_url'] or ''))]
print('thumbnail rows, distinct IDs',len(ids),len(set(ids)))
PY
TZ=Asia/Karachi node -e 'console.log(new Date("2026-10-10T00:10:51").toISOString()); console.log(new Date("2026-10-10T00:10:51Z").toISOString())'
sqlite3 'file:data/rebuild/zameenrentals.db?mode=ro' "SELECT '2026-10-03T00:00:00' < '2026-10-03 03:00:00' AS text_comparison, datetime('2026-10-03T00:00:00') < datetime('2026-10-03 03:00:00') AS time_comparison;"
```

Some displayed commands combine the same ranges read in separate calls for convenient rerunning; the scratch-script invocations and Q1/Q3/Q7 are the executed commands. For durable reproduction without scratch, the corrected CSV calculation is embedded below. It uses the same decomposition/round/carry sequence inspected in the bundle, without executing that bundle. Its use on historical observations remains conditional as explained above.

```python
import csv,collections,json,math
from datetime import datetime
from pathlib import Path
rs=list(csv.DictReader(open('docs/listing-trust-2026-10-10/evidence/added_text_oct7_vs_current.csv')))
units=['month','week','day','hour','minute'];measures=[2629800000,604800000,86400000,3600000,60000]
def human(days):
 days*=86400000
 counts=[]
 for i,v in enumerate(measures):
  c=days/v if i==4 else math.floor(days/v);counts.append(c);days-=c*v
 m=next((i for i,c in enumerate(counts) if c),len(counts))
 for i in range(4,-1,-1):
  counts[i]=math.floor(counts[i]+0.5)
  if i==0:break
  s=measures[i-1]/measures[i]
  if counts[i]%s==0 or i>m:counts[i-1]+=counts[i]/s;counts[i]=0
 return next(((int(c),units[i]) for i,c in enumerate(counts) if c),(0,'minute'))
import re
def parse(s):
 m=re.fullmatch(r'Added: (\d+) (\w+?)s? ago',s);return (int(m[1]),m[2]) if m else None
labels={parse(r[k]) for r in rs for k in ['cur_added_text','oct7_added_text'] if r[k]};bounds={}
for p in labels:
 v=measures[units.index(p[1])]/86400000;lo=0;hi=(p[0]+2)*v
 target=p[0]*v
 for _ in range(65):
  mid=(lo+hi)/2;n,u=human(mid)
  if n*measures[units.index(u)]/86400000>=target:hi=mid
  else:lo=mid
 bounds[p]=hi
print('bounds days', sorted((str(k),v) for k,v in bounds.items()))
print('current max',max(r['cur_card_scraped_at'] for r in rs))
for now in [datetime(2026,10,10,8),datetime(2026,10,10,3,13),datetime.fromisoformat(max(r['cur_card_scraped_at'] for r in rs))]:
 counts=collections.Counter();city=collections.defaultdict(collections.Counter);pure=collections.Counter();future=0
 for r in rs:
  a=[]
  for prefix in ['oct7','cur']:
   text=r[prefix+'_added_text'];t=r[prefix+'_card_scraped_at']
   if not text or not t:continue
   t=datetime.fromisoformat(t)
   if t>now:future+=1;continue
   a.append(bounds[parse(text)]+(now-t).total_seconds()/86400)
  if r['cur_first_seen_at']:a.append((now-datetime.fromisoformat(r['cur_first_seen_at'])).total_seconds()/86400)
  for n in [7,14,30,60]:counts[n]+=max(a)>=n;city[r['city']][n]+=max(a)>=n;pure[n]+=(now-datetime.fromisoformat(r['cur_first_seen_at'])).total_seconds()/86400>=n
 print('corrected',now.isoformat(),'future_excluded',future,'counts',dict(counts),'city',dict(city),'firstseenonly',dict(pure))
```

Independent frozen F2 reproduction, without importing reproduce.py or the application:

```python
import csv, re
from datetime import datetime
from collections import Counter
rows = list(csv.DictReader(open('docs/listing-trust-2026-10-10/evidence/added_text_oct7_vs_current.csv')))
pairs = {('month','day'), ('month','hour'), ('week','day'),
         ('week','hour'), ('day','hour'), ('hour','hour')}
counts = Counter()
for r in rows:
    labels = [re.fullmatch(r'Added: (\d+) (minute|hour|day|week|month|year)s? ago',
                          r[p+'_added_text']) for p in ['oct7','cur']]
    if not all(labels) or not all(r[p+'_card_scraped_at'] for p in ['oct7','cur']):
        continue
    old, new = [datetime.fromisoformat(r[p+'_card_scraped_at']) for p in ['oct7','cur']]
    if (new-old).total_seconds() < 2*86400:
        continue
    units = tuple('hour' if m[2]=='minute' else m[2] for m in labels)
    counts[units] += 1
print(sum(counts[p] for p in pairs), sum(counts.values()), counts)
```

### Explicitly unverified

1. Production's first-observation depth, crawler health, inactive inventory and restorable backup retention. Need owner-approved read-only access or exported aggregate queries and a backup copy. This review neither requested nor assumed production access.
2. Any mechanism linking payment, product tier, edits, expiry or reactivation to the observed date changes. Need fixed-ID before/after evidence across a reset and authoritative lifecycle documentation or an owner-controlled test listing. Product labels alone do not prove a paid refresh.
3. A completed 24–48 hour panel. Only the supplied Oct-7/Oct-10 snapshots and short same-morning page comparisons exist here. No scheduler or long-running job was created; no future observations are implied.
4. Whether an old ad's home is rented, vacant, newly vacant again, withdrawn, or being advertised as bait. There are zero verified outcomes, so H2/H3 and an availability-driven 7/14/30-day cut-off remain unresolved.
5. Zameen's original timestamp contract, whether historical clients rounded identically, whether old timestamps can be imported/backdated, whether IDs can be reused, and the lifecycle meaning of reactivatedAt. The current formatter and two live examples are direct evidence; universal source guarantees are not.
6. Every CSV row's page type, raw response and exact time that Added was last observed. Current storage can retain a stale label with a later card_scraped_at. The direct epoch examples strengthen F1, but do not certify all 3,714 counted rows as fresh reset observations.
7. Original creation dates from numeric ID order. First-discovery maxima do not validate allocation order or public publication dates.
8. Identity of rental units in the photo groups, whether both ads were simultaneously available, or deletion/repost history. All 178 covers in the 60 selected groups were inspected, but no full-gallery/address/availability truth was collected. The original 32,709-photo snapshot cannot be exactly reconstructed from a CSV that contains no image URLs.
9. Grouping precision, recall, cluster purity and user cost. No held-out unit-identity eval passes the Wilson gate. The sample is not large or independent enough to establish the true duplicate rate.
10. UX comprehension, task success, search conversion or performance of a proposed feature. This was a source/evidence review, not a UI implementation or usability study. No application or browser test suites were run because application code was unchanged.

The only repository file written for this review is `docs/listing-trust-2026-10-10/review.md`. Keep the proposed implementation separate from this audit until the evidence and wording decisions above are resolved.
