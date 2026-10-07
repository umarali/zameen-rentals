# Vercel hosting assessment

Checked September 15, 2026. This is a deployment proposal, not a deployed setup.

## Feasibility

The frontend and FastAPI API can run on Vercel. The existing `main.py` exports
the supported `app` entrypoint. The current persistent SQLite file and continuous
crawler cannot be moved there unchanged.

Vercel's [FastAPI support](https://vercel.com/docs/frameworks/backend/fastapi)
includes Python functions and static assets. Its function storage is
[ephemeral](https://vercel.com/kb/guide/is-sqlite-supported-in-vercel), so a local
SQLite file cannot be the authoritative database for listings, favorites or alerts.
Putting the file in `/tmp` would not make writes durable or shared between instances.

The [Hobby plan](https://vercel.com/pricing) is free for personal, non-commercial
use. With Fluid compute, Python functions have a
[five-minute maximum duration on Hobby](https://vercel.com/docs/functions/limitations#max-duration).
[Hobby cron jobs run at most once daily per job](https://vercel.com/docs/cron-jobs/usage-and-pricing).
The continuous crawler needs a separate execution environment.

## Proposed free-tier setup

| Component | Location | Work required |
| --- | --- | --- |
| Frontend and API | Vercel Hobby | Configure Python entrypoint, frontend build, static paths and environment variables. |
| Listings and personalization | Hosted database, initially evaluate Turso/libSQL | Replace the local connection layer and verify transactions, row access, migrations, triggers and full-text search. |
| Crawler and alert dispatch | Scheduled GitHub Actions | Add bounded batches, resume through database crawl state, prevent overlapping runs and enforce time limits. |
| Push signing keys | Deployment and workflow secrets | Load the existing keypair from environment variables rather than generating keys on function startup. |
| Natural-language parsing | Existing regex fallback | Omit the optional Anthropic API key to avoid model charges. |

[Turso Free](https://turso.tech/pricing) currently includes 5 GB storage,
500 million monthly rows read and 10 million monthly rows written.
Its [Python SDK supports remote connections without a local file](https://docs.turso.tech/sdk/python/quickstart).
It is a candidate, not a verified drop-in replacement. This app uses SQLite FTS5,
while [the newer Turso engine uses a different full-text index](https://docs.turso.tech/sql-reference/extensions).
Verify the selected cloud engine and remote driver against our schema before
committing to it or importing data.

[GitHub Free includes 2,000 Actions minutes per month for private repositories](https://docs.github.com/en/billing/concepts/product-billing/github-actions).
For example, four capped ten-minute Linux jobs a day consume at most 1,240 runner
minutes in a 31-day month, before other workflows. This is a proposed budget,
not a claim that all 1,100+ areas can be refreshed in that time. The free setup
would prioritize selected areas and recent city feeds, with slower full coverage.

Free-tier eligibility and quotas apply independently to each service. Disable
paid overages and keep crawler runtime below the account's remaining allowance.

## Migration order

1. Confirm whether the priority is a fully free stack or the smallest migration.
2. Test a remote database connection against schema creation, search, FTS,
   favorites, alerts and concurrent crawler/API writes using disposable data.
3. Move migrations out of web startup. Run them once during release; function
   startup should initialize a connection, not backfill production tables.
4. Add environment-based push keys and a database-backed crawler budget.
5. Prepare the Vercel configuration and scheduled workflow, then run the existing
   backend and headless browser tests with the new database backend.
6. Restore a complete backup if available. If it is unavailable, start a fresh
   hosted database and repopulate listings through crawling; old personalization
   history cannot be recreated that way.
7. Deploy and check searches, writes, static assets, source freshness and push
   delivery. No service has been created or deployed during this assessment.

## Smallest-change alternative

Host only the frontend on Vercel and proxy `/api/*` to the existing backend.
Keep FastAPI, SQLite and the crawler together on a persistent server. This avoids
the database migration and preserves continuous crawling, but the backend's
hosting cost remains. Its address and availability still need verification.

## Current data status

The repository contains orphan WAL/SHM recovery files, not a full database.
S3 backup discovery failed with `InvalidAccessKeyId`. See the
[review report](review-2026-09-15.md) for details. A backup is needed to preserve
old data, but its absence does not prevent launching with a newly crawled dataset.
