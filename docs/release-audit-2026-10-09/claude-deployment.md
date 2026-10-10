# Production deployment: furnishing fix, 2026-10-09

**Result: deployed and verified.** The fix is live at https://zameenrentals.emerssive.com. No rollback was needed. Automated cloud backups are still broken (see "Remaining blockers").

## Release

| Item | Value |
| --- | --- |
| PR | https://github.com/umarali/zameen-rentals/pull/26, merged 2026-10-09 13:37:24 UTC with a normal merge commit, no admin bypass. The ruleset requires a PR with 0 approvals and has no status checks; the PR was `CLEAN`/`MERGEABLE`. |
| Reviewed commit | `be3e2b5bfe3cf3c415a7916513de3b907f69b6a8` |
| Merged main SHA | `c8c247b066d3c88962d7472c6924efd95c1fc057` |
| Base | `6ad5b86` (origin/main did not move before merge) |
| Release checkout | Clean detached worktree at `c8c247b`. Its tree is byte-identical to `be3e2b5`. |

The user's dirty checkout was not used or modified.

## Commands

- `git fetch origin` confirmed `origin/main` was still `6ad5b86`.
- `git push -u origin fix/release-audit-followup-20261009`
- `gh pr create --base main --body-file /tmp/zr-release-audit-20261009/pr-body.md`
- `gh pr merge 26 --merge`
- `git worktree add --detach /tmp/zr-release-c8c247b c8c247b…`
- `ZR_DEPLOY_HOST=root@165.22.91.77 ZR_DEPLOY_KEY=~/.ssh/id_ed25519 bash deploy/deploy.sh` exited 0 (log: `deploy.log`). It:
  - rebuilt assets as `index-C5KYzyJ_.js` and `index-BUD4arsx.css`;
  - synced code, preserving `.env`, `.venv` and `data`;
  - restarted the web service (13:38:08 UTC) and the crawler (13:38:20 UTC);
  - re-checked the backup timer: active, next run 2026-10-10 03:01:46 UTC.

## Pre-deploy state

- Web, crawler and backup timer were active. Health was 200 with 34,416 listings; the crawler was fresh.
- Rollback artifacts in `/var/backups/zameenrentals-release-20261009/` matched their recorded SHA-256s:
  - code: `2dcad487…78be8`
  - DB: `7cf67501…102ec8`

  They were not modified.
- Baseline bug on Gulberg apartments: `furnished=false` returned 374 results, the same as no filter, including "Fully Furnished" titles. `furnished=true` returned 203.

## Verification after deploy

**Hashes**
- A content-checksum `rsync` dry-run of the release checkout against `/opt/zameenrentals` (deploy excludes; `.env`, `.venv` and `data` skipped) found 0 differences and no stray files.
- SHA-256 of `app/db_listings.py`, `parsing.py`, `personalization.py`, `routes.py`, `static/index.html` and both assets is identical locally, on disk, and as served over HTTPS (`/`, `/static/assets/index-C5KYzyJ_.js`, `/static/assets/index-BUD4arsx.css`).

**Health**
- `/api/health` returns 200 with 34,417 listings. `/api/health/crawler` returns 200; the newest listing was seen 4.2 minutes ago.
- Web, crawler and backup timer are active.
- No tracebacks or errors in the web or crawler journals since the restart.

**API semantics** (`prod-api-furnishing-ids.json`, `prod-semantics.json`)
- Gulberg apartments: Any 374, furnished 200 (was 203), unfurnished 10 (was 374).
- A read-only check of the live DB (`mode=ro`, as the service user, using the deployed code; only counts left the server) classified page-1 results:
  - `furnished=true`: 25 of 25 furnished.
  - `furnished=false`: 10 of 10 unfurnished.
  - Any: 11 furnished and 14 unknown, so unknown listings stay under Any.
- Across all active listings: 5,984 furnished, 404 unfurnished, 28,029 unknown or contradictory. The SQL and Python versions agree for both states.
- 0 listings with negative wording in the title match `furnished=true`.

**Headless browser on production, desktop 1440×900 and mobile 375×812** (`prod-furnishing-browser.cjs` / `.json`). All checks passed with 0 page errors:

| Step | Desktop and mobile result |
| --- | --- |
| "furnished apartment in Gulberg Lahore" | Parser `ai`, `furnished: true`; request `furnished=true`; 200 results, none with negative wording; Understood chip shows "Furnished". |
| "unfurnished apartment in Gulberg Lahore" | Parser `ai`, `furnished: false`; request `furnished=false`; 10 results, all with negative wording; chip shows "Unfurnished"; URL `furnished=0`; `localStorage` `furnishing=unfurnished`. |
| Reload | Exactly one listing request, `area=Gulberg&furnished=false`, so no partial request; More panel shows Unfurnished active. |
| Any | Request has no `furnished` param; 374 results; URL param removed. |
| Near Me with unfurnished (desktop only) | `furnished=false`; 11 results, all with negative wording. |

**Real AI parsing** (`prod-parse-checks.json`). All five came from the `ai` parser in 1.7–2.4 s:

| Query | `furnished` |
| --- | --- |
| Roman Urdu "Gulberg mein unfurnished flat 80 hazar tak" | `false` |
| Urdu "گلبرگ میں ان فرنشڈ فلیٹ" | `false` |
| "DHA mein furnished ghar 1 lakh tak" | `true` |
| "F-8 mein bina furniture 2 bed flat" | `false` |
| "2 bed flat in Clifton under 75k" | absent |

**Pre-deploy test evidence** (not repeated):
- Claude: 816 backend tests passed; 28 voice tests passed with 2 skipped; 464 Playwright passed with 20 skipped.
- Codex independently: 464 passed and 20 skipped on Playwright, plus 38/38 live parser queries.
- Earlier in this work, Codex (not the human user) stopped two long Claude CLI test runs in order to deliver review findings.

## Production state

- Production serves `c8c247b` code and assets.
- No changes were made to the model or provider key, the database, voice, tagging, credentials or infrastructure.

## Remaining blockers and risks

1. **Automated cloud backups are still broken.** Production has no backup credential or destination configured. The local default AWS credentials are invalid, and the valid named profile gets `AllAccessDisabled` on the documented bucket. The user has been asked where the current backup access is stored. The timer will keep firing and failing until that is configured. Do not copy unrelated broad AWS credentials to the server. The manually verified snapshot `pre-release.db.gz` (SHA-256 `7cf67501…102ec8`, integrity-checked, restore-tested) is the current recovery point.
2. **The unfurnished filter returns few listings.** Only 404 active listings (about 1.2%) say they are unfurnished; the other unknowns stay under Any. This is by design, but expect user feedback.
3. **Residual risks from `claude-findings.md` still apply:** substring evidence edge cases, semi-furnished counted as furnished, and the analytics `null` meaning for no preference.

## Rollback

No rollback was needed. To roll back, restore `/var/backups/zameenrentals-release-20261009/pre-release-code.tar.gz` into `/opt/zameenrentals`, keeping `.env`, `.venv` and `data`, then restart `zameenrentals-web` and `zameenrentals-crawler`. This is code-only: the release made no database change, so the DB snapshot is needed only for data loss.
