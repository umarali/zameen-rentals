# Release and Claude API audit, 2026-10-09

Follow-up: the user approved Claude access, the furnishing and saved-state fixes were merged and deployed, and credential availability was investigated further. Read the [current follow-up](followup.md). The original audit below records the state before those changes.

Haiku 5.5 is working through the application's real API integration. Production already has the merged release. Two confirmed problems prevent an unqualified production sign-off: cloud backups fail for missing credentials, and the frontend ignores an explicit unfurnished result after a furnished search.

## Improved execution prompt

Audit ZameenRentals and identify what remains before the next production release. Consult Claude about previous work and proposed Claude API use cases. Confirm the exact provider and model behind the integration. Test configuration, live API calls, English/Roman Urdu/Urdu parsing, failure handling, fallbacks, response times, and existing regressions. Preserve existing work. Report what works, what remains uncertain, and recommended next steps. Once release checks pass, ask Claude to deploy the tested changes to the existing production environment and verify deployed code and critical user flows. State any blocker explicitly.

## Release identity and production

- GitHub main: `6ad5b86271b161cdddf51e47156a22987a04c9db`. No open PRs; all integration, parser, Jev, accessibility, mobile, and Near Me PRs are merged. No GitHub Actions runs were returned.
- Production: https://zameenrentals.emerssive.com on the existing DigitalOcean server. The Heroku references in AGENTS.md and CLAUDE.md are stale.
- Compared SHA-256 hashes for 44 production Python, frontend, data-definition, and built asset files against a clean archive of main. All matched. The built JS/CSS filenames also matched.
- Web and crawler services were active. Health returned 34,367 active listings: Karachi 8,486; Lahore 13,687; Islamabad 12,194. Each city had recent crawler activity.
- Public API parsing succeeded in English, Urdu, and Roman Urdu. All three city searches returned HTTP 200 and listings. A repeated parse returned in 0.172 seconds, versus 4.531 seconds for the initial production request.
- Headless desktop and mobile production checks loaded 25 initial cards, parsed an explicit Clifton/Karachi query with AI, switched cities, returned two matches, and recorded no page JavaScript errors.
- No application code was changed, no PR was created, and no deployment was performed during this audit. Existing uncommitted work in the user's checkout was preserved. Tests used a separate main snapshot and temporary databases.

## Live Claude evidence

The default is `ZR_PARSE_MODEL=claude-haiku-5-5`, using Anthropic's async SDK through Instructor. Captured response metadata independently confirmed `claude-haiku-5-5`, rather than merely echoing the configured model name. Production's parser file is identical and its public endpoint returned `parser: ai`.

[Anthropic's current pricing](https://platform.claude.com/docs/en/about-claude/pricing) lists $0.10 input, $0.50 output, $0.125 five-minute cache writes, and $0.01 cache reads per million tokens for this prompt size. Those match the application's cost table. Costs below are token-based estimates, not invoice reconciliation.

The completed run exercised the actual `/api/parse-query` route through ASGI and made uncached live Anthropic calls. It used the existing 150 labelled queries plus 30 newly authored queries. The holdout's expected Islamabad area spelling was corrected from `F-8` to the database's canonical `F 8`; no product code was tuned to these results.

| Measure | Observed result |
| --- | --- |
| Labelled-filter correctness | 178/180, 98.9% |
| Existing set | 148/150 |
| Additional set | 30/30 |
| AI responses / HTTP 200 responses | 180/180 for both |
| Silent wrong areas | 0 |
| Wrong areas with approximate-match warnings | 2 |
| Unnecessary approximate-match warnings | 7 |
| Median / p95 / maximum route latency | 1.322s / 1.542s / 4.341s |
| Estimated cost for completed pass | $0.0222902 |
| Estimated average cost | $0.00012383 per query, about $0.124 per 1,000 with this cache pattern |

The scorer checks only labelled fields and accepts correct areas that carry unnecessary warnings. Therefore 178/180 does not mean every response was perfect. These synthetic cases are not a random sample of production queries, and the existing set has informed earlier parser changes.

The two mismatches were:

1. `flat in north karachi buffer zone` selected North Karachi instead of North Buffer Zone, with an approximate warning.
2. `flat near liberty market` selected Gulberg Main Market instead of Gulberg, with an approximate warning.

An earlier live run stopped at `lhr-031` after a provider failure around the configured six-second timeout and returned regex fallback. The later complete pass succeeded on that query in 4.341 seconds. Do not interpret the completed pass's zero failures as proof that provider outages or timeouts never occur. The initial sandboxed attempt also failed for network restrictions and is not an API-quality measurement.

The application uses a six-second SDK timeout, disables SDK retries, and bounds route work at eight seconds. Existing tests cover cancellation, missing keys, provider errors, malformed/reversed model output, cache reuse and invalidation, and daily-spend fallback. The $1/day default is a best-effort threshold, not a strict concurrent reservation: in-flight requests can cross it, unknown model prices are not accounted for, and usage for unsuccessful calls may not be captured.

## Regression checks

- Main production build passed. Existing warnings remain about the roughly 512 KB JS bundle and a dynamic import that cannot split a statically imported module.
- Main backend full run: 777 passed, six failures from missing local audio dependencies, two intentionally skipped real speech-model tests. After installing `av` and NumPy in a temporary environment, all 28 voice tests passed with the same two skips. This verifies all 783 non-skipped backend cases across the full run and focused rerun.
- Full headless Playwright suite: 452 passed, 20 intentional skips, desktop and mobile.
- The browser fixture server deliberately uses regex parsing. The separate live route pass and public production checks supply the AI evidence.
- No sustained load test, full speech-model execution, cloud-backup restore drill, or listing-tag accuracy benchmark was performed here.

## Confirmed remaining work

1. **Repair backups before another release.** The backup timer is active, but both October 8 and October 9 jobs exited with `Unable to locate credentials`. The service reads `/etc/zameenrentals/backup.env`; configure the intended S3-compatible destination and scoped credentials there, run a backup, verify the uploaded object, and restore it into an isolated database. Never restore over the live DB for a verification drill. The next scheduled run does not prove backups work.
2. **Fix explicit negative furnishing end to end.** In production, search `furnished apartment in Gulberg Lahore`, then `unfurnished apartment in Gulberg Lahore`. Haiku correctly returns `furnished: false` for the second query; the browser still requests `furnished=true`. `frontend/src/main.js` applies furnishing only when truthy and serializes only true. A proper fix must distinguish no preference, furnished, and unfurnished through state, requests, persistence, and chips; simply unchecking the toggle would still fail to request unfurnished-only results. Add a sequential browser regression before deployment. See `furnished-bug-reproduction.json`.
3. **Finish or hide the Jev rollout.** Code is deployed, but `listing_tags` has zero rows and the inspected production `.env` has no TypeSafe key. Strict tag filters therefore have no populated inventory to match. Jev is a separate provider from the Claude search parser. Start with a bounded, evaluated tagging batch before bulk processing.
4. **Decide whether to enable voice.** The production voice-status endpoint reports disabled. The code is present, but the full model and its resource requirements were not validated in this audit.
5. **Improve parser visibility and evaluation.** Track fallback reasons and latency, reduce the seven unnecessary area warnings, investigate the two ambiguous-area misses, retain partial benchmark results when the stock evaluator aborts, and add cross-city and sequential-search cases. Add CI and a deployed commit identifier so future release verification is simpler.
6. **Update stale documentation.** Agent guides still describe a single-file frontend and Heroku. Parts of nlp-parsing.md still describe an MD5/five-minute parse cache, while current code uses a versioned SHA-256 key and seven-day persistent cache.

## Claude API use cases and recommendation

The previous proposal is in [the product review](../product-review-2026-10.md). It includes conversational search, cached listing summaries and information checks, compare explanations, alert digests, landlord message drafts, and area guides. These were proposals, not all delivered features. The implemented Claude feature verified here is query-to-filter parsing, with candidate-area prompts, prompt/result caching, spending counters, and fallbacks. Existing comparison and alert UI should not be mistaken for AI-written explanations or digests.

After backups and furnishing are fixed, build a small compare explainer using the existing structured facts. Require every numerical claim to come from supplied listing data. Then evaluate cached bilingual listing summaries that preserve missing information and negation. Message drafts are another bounded option; show the draft to the renter and let them send it. Defer a broad conversational assistant until search-state transitions and monitoring are reliable. Price-anomaly claims and area guides need separate data-quality checks; scraped listings do not establish safety or fraud.

## Claude consultation and deployment handoff

The installed Claude CLI was found. Its sandboxed invocation returned `Not logged in`. The subsequent network-enabled consultation request was rejected by automatic approval review because it could disclose private repository source and documentation to Anthropic. Explicit approval was requested in chat and had not been received when this report was written. No live Claude review or Claude deployment is claimed. Reading the existing product proposal is not a substitute for that consultation.

Once that approval is provided, ask Claude to review this report and the concrete evidence, resolve the furnishing issue on current main, and verify backup configuration. Only then deploy any newly tested changes using the established production target. Current production already matches main; do not deploy the user's older dirty checkout or restart services merely to claim a deployment. Preserve credentials and data, establish rollback evidence, and repeat the public API/browser and backup checks after an actual release.

## Evidence files

- [Per-query live results](live-parser-results.jsonl) and [summary](live-parser-summary.json)
- [Additional labelled queries](holdout-queries.jsonl)
- [Production API checks](production-api-checks.json)
- [Production desktop/mobile checks](production-browser-checks.json)
- [Furnishing bug reproduction](furnished-bug-reproduction.json)

Temporary build/test logs and audit scripts are in `/tmp/zr-release-audit-20261009`. The evidence files stored alongside this report contain synthetic queries and test results, not credentials or private user query history.
