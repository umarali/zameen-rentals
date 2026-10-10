# Review of the relaunch baseline

Historical review of the October 7 baseline. The findings below describe that revision, not the current release. For the later production audit and remaining work, see the [October 9 follow-up](release-audit-2026-10-09/followup.md).

Reviewed `0c35c38`, merged as `edf3742`, on 2026-10-07. I asked Claude for a handoff by resuming a fork of session `zameenrental-c4` with tools disabled. The commit combines that session's work with earlier sessions' changes. The findings below concern the combined change, not individual attribution.

Three issues merit follow-up.

## P1: Stop every database user before restoring

`deploy/backup/README.md:50-52` stops only the crawler, then copies a snapshot over the live database. The web service retains an open SQLite connection and can write search history, favorites and alerts. Its WAL also belongs to the database being replaced.

I reproduced the failure with disposable SQLite files: keep a WAL connection open, copy a valid snapshot containing different data over the main file, then query through both the existing and a new connection. Both return the old data. After closing and reopening all connections, the old data remains. A valid snapshot and successful copy therefore do not prove a successful restore.

Please align this recipe with the DigitalOcean runbook's stop-both-services approach. Also stop the backup timer and any active backup job during replacement, preserve the old database and sidecars together for recovery, and install the verified snapshot only after all connections close. Check the restored contents before restarting services. Do not delete recovery files while a process might still use them.

## P1: Start the backup timer after deployment is ready

`deploy/user-data.sh:194` enables `zameenrentals-backup.timer` but never starts it. The deploy script restarts only the web and crawler services. The DigitalOcean verification step starts the backup service once, which does not activate its timer. Following the documented flow without a reboot can therefore produce one successful backup and no scheduled backups afterward.

Please start the timer explicitly after dependencies, credentials and the database are ready, and verify that it is active with a next trigger time. Avoid starting all application units during bootstrap before their code exists. This follows the distinction between enabling and starting units in the [systemd manual](https://github.com/systemd/systemd/blob/main/man/systemctl.xml). This finding is based on the scripts and documented semantics; I did not provision a Droplet.

## P2: Use one string for all multi-area match offsets

`app/parsing.py:277-290` records Urdu spans against original `q`, but English spans and the joiner check use `ql`. Earlier bedroom, size and furnished parsing shortens `ql`, so those offsets no longer describe the same text.

Reproduced directly against `parse_natural_query`, city `karachi`:

```text
کلفٹن or گلشن اقبال
  area=Clifton, areas=[Clifton, Gulshan-e-Iqbal]

2 bed کلفٹن or گلشن اقبال
  bedrooms=2, area=Gulshan-e-Iqbal, no areas field

کلفٹن or DHA
  area=Clifton, areas=[Clifton, DHA Defence]

2 bed کلفٹن or DHA
  bedrooms=2, area=Clifton, no areas field
```

Please collect every span and inspect joiners against one unchanged string, or preserve offsets when removing filter text. Add regression cases with bedroom, furnished and size prefixes before Urdu and mixed-script alternatives. The frontend's acknowledged lack of multi-area support is separate from this parser defect.

## Validation and scope

- `python3 -m pytest -q`: 337 passed. These findings are gaps beyond that passing suite.
- `git diff --quiet 0c35c38 edf3742`: identical trees.
- The existing location-path tests exercise parent/child inclusion, sibling exclusion, preservation across crawl order, and applying the path before alert matching. Sharing the SQL area predicate between search and alerts is a sound choice.
- Current exact-name self-matching passed for all 1,133 entries in the three city dictionaries. Claude cautioned that its earlier historical mismatch count came from an intermediate implementation; I have not treated that historical claim as evidence.
- I did not rerun browser tests. Claude reported 402 passed and 20 skipped before the commit; that is its report, not my independent validation. No live AI call, production restore, deployment or crawler operation was performed.
- Frontend work in `../zameenrental-design` and the uncommitted verification helper were still in progress and are outside this completed-baseline review. Application code was not changed.

Security review found no additional confirmed issue in the changed paths; this is not a security certification. I did not benchmark performance. Correctness follow-up is limited to the three findings above; no style or general refactoring requests.

Claude reviewed these findings and agreed with all three. It reported that the summaries and this file's path were accepted and queued for `zameenrental-99` and `zameenrental-c4`. Neither recipient had replied at completion; delivery is not evidence that they have read or fixed the issues.
