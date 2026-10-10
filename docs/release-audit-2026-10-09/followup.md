# Claude review and production follow-up

The user approved Claude's repository access after the initial audit. Claude Opus 5.5 reviewed the findings, implemented the furnishing fix, incorporated Codex's independent review findings, and merged [PR #26](https://github.com/umarali/zameen-rentals/pull/26).

- Reviewed implementation commit: `be3e2b5`.
- Merged and deployed commit: `c8c247b066d3c88962d7472c6924efd95c1fc057`.
- Clean release checkout: `/tmp/zr-release-c8c247b`.
- The user's original dirty checkout was preserved.

## What changed

- Any, Furnished, and Unfurnished are distinct settings across the frontend, URLs, saved searches, ordinary/map/nearby requests, and alerts.
- An explicit negative query now clears a previous furnished requirement and sends `furnished=false`.
- Unfurnished results require explicit negative listing evidence. Missing or contradictory furnishing information remains available under Any, without being asserted as unfurnished.
- Common negative wording and structured values such as `Furnished: No` are handled consistently by database search and alert matching.
- Unfurnished queries cannot fall back to an upstream scraper that cannot enforce the filter.
- Regex fallback supports negative furnishing requests. The parser cache version was bumped.
- Restoring saved filters no longer sends a premature request containing only the area.

Codex rejected the first implementation's assumption that missing furnishing information meant unfurnished. Independent reproductions also caught `not furnished` being classified positively and the partially restored initial request. Claude corrected both before release. Codex paused the intermediate CLI runs to deliver those findings; the human user did not stop the tests.

## Verification

| Check | Result |
| --- | --- |
| Backend suite, voice separately | 816 + 28 passed; 2 full-model voice tests intentionally skipped |
| Complete headless browser suite | 464 passed; 20 intentional skips, in both Claude's run and Codex's independent run |
| Additional live Haiku route checks | 38/38 labelled cases passed; all returned model `claude-haiku-5-5`, with no fallback |
| Listing classifier consistency | SQL and Python agreed across the 34,402-row snapshot |
| Production source and built assets | Codex compared 44 file hashes to the merged release; zero mismatches |
| Public web/database and crawler health | Both returned healthy after deployment; all three cities had recent crawler activity |

The live-query run had median latency 1.53 seconds, p95 1.73 seconds, and estimated cost $0.00543. See [summary](furnishing-live-summary.json) and [per-query results](furnishing-live-results.jsonl). These controlled tests do not establish universal accuracy. The earlier area-selection limitations in the initial audit were not changed by this release.

The public Gulberg apartment search provides a concrete before/after check: before deployment, `furnished=false` returned the same 374 results as Any, including furnished listings. After deployment it returned 10 listings with explicit negative furnishing evidence. Furnished results fell from 203 to 200 after incorrect negative matches were removed.

Final production checks passed on desktop and mobile: furnished → unfurnished → Any, URL and saved-state persistence, and a reload that sent exactly one correctly filtered request. The desktop nearby check returned 11 explicitly unfurnished listings. Both browser runs recorded zero page errors. Five additional live multilingual queries used the AI parser and returned the expected furnishing values. See [Claude’s deployment report](claude-deployment.md) and [production browser results](prod-furnishing-browser.json).

## Credential clarification and backups

The earlier statement about missing credentials was too broad. The Claude API key is present and works. AWS credentials also exist on the Mac. The backup service specifically lacks usable access:

- Its configured environment file has no backup credentials or destination overrides, and no default credential file was present for the root or service accounts checked on the DigitalOcean server.
- The local default and `propel-deploy` profiles returned `InvalidClientTokenId`.
- The `albir-deploy` profile authenticated, but the documented `zameenrentals` bucket returned `AllAccessDisabled`. That error does not establish why access was disabled.
- The previous backup design used an EC2 instance role. Such a role does not automatically supply credentials to a DigitalOcean server.

No unrelated deployment credentials were copied to production, no new bucket or credential was created, and automated cloud backups have **not** been repaired. The intended current backup profile or secret-store location is still needed. A question requesting that location, not secret values, was sent to the user.

For this code-only release, Codex created separate private database and application rollback archives on the server. The database archive was also copied to the user's Mac, decompressed into an isolated database, and passed both integrity checking and a writable transaction/rollback test. It contained 34,402 listing rows. See the [verification receipt](release-backup-verification.json).

- Server archives: `/var/backups/zameenrentals-release-20261009/pre-release.db.gz` and `pre-release-code.tar.gz`.
- Database archive SHA-256: `7cf6750152fc89b18cbf49140234d9e0b31e582a0a252fbd8cc7d6e7e6102ec8`.
- Code archive SHA-256: `2dcad487581b8f0f2533bef99686c5370fcc6adf1c8000175b1856a33bd78be8`.

These manual recovery copies protected this release. They do not replace a functioning recurring off-site backup job. The live database was never replaced.

## Next work

Restore automated backup access first. Claude and Codex agree that the next bounded Claude API feature should be a compare explainer using existing listing facts, followed by evaluated bilingual listing summaries. Treat unknown furnishing as unknown in either feature. Jev tag population and voice enablement remain separate rollout tasks; neither was activated by this release.

Only about 1.2% of snapshot listings explicitly stated they were unfurnished. Fewer results for that filter are expected. Classification remains based on listing text and structured values, not a physical verification of the property.
