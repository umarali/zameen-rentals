# Credits and paid features: shared contract

This is a local working agreement for the parallel tracks building paid features. Every track branches from `feat/credits-base` and must keep to this contract so the branches merge cleanly.

## Product rules

- Search, filters, maps, contacts, saved homes, comparisons and today's alerts stay free. A paid feature must add something; it must never make a free feature worse.
- No subscription and no renewal. People buy a credit pack once and spend credits on paid actions.
- New visitors get `STARTER_CREDITS` (10) free credits.
- Packs and costs live only in `app/credits.py` (`PACKS`, `COSTS`). Read them from there or from `GET /api/credits`. Never hard-code numbers in copy or UI.

| Action key | Credits | Owner track |
|---|---|---|
| `tailored_list` | 5 | ai |
| `search_report` | 5 | ai |
| `daily_shortlist_day` | 2 per day | alerts |
| `instant_alerts_day` | 1 per day | alerts |
| `listing_history` | 1 per listing | later, not in this round |

| Pack | Credits | PKR |
|---|---|---|
| small | 20 | 199 |
| standard | 60 | 499 |
| large | 130 | 999 |

## Backend interface (`app/credits.py`)

- `balance(client_id) -> int`. The first call grants starter credits.
- `spend(client_id, action, ref=...) -> int`. Raises `InsufficientCredits`. Idempotent on `ref`.
- `refund(spend_ref) -> bool`. Call it when the paid work fails after the spend.
- `grant(client_id, credits, kind="purchase"|"restore_in"|"adjust", ref=...) -> bool`. Idempotent on `ref`. Only the payments track grants.
- `new_spend_ref(action)`, `history(client_id)`, `summary(client_id)`.
- Paid route pattern: spend first, do the work, refund on failure. On `InsufficientCredits`, respond `raise HTTPException(status_code=402, detail=exc.as_detail())`.
- Identity: `_require_client_id(request)` from `app/routes.py` (the `X-Client-Id` header).

## Frontend interface

- `frontend/src/credits-gate.js` → `paidFetch(url, options)`. Use it for every paid call.
  - On 402 it fires `window` event `zr:insufficient-credits` with `{code, action, balance, cost}` and throws an error with `.insufficientCredits = true`. Feature UI should show a short inline message; the payments track listens for the event and opens the top-up sheet.
  - On success it fires `zr:credits-changed`.
- The payments track owns `frontend/src/credits.js` (balance display, top-up sheet, restore). Other tracks don't edit it.

## File ownership (to avoid merge conflicts)

| Track | Branch | Owns |
|---|---|---|
| payments | `feat/credits-payments` | `app/payments.py`, `app/routes_credits.py`, `frontend/src/credits.js`, credits section in the My rentals panel, test checkout page |
| ai | `feat/ai-credits-features` | `app/ranking.py`, `app/tailored.py`, `app/report.py`, `app/routes_ai.py`, `frontend/src/tailored.js`, `frontend/src/report.js` |
| alerts | `feat/paid-alerts` | alert sections of `app/personalization.py`, `app/notify.py`, `app/alert_upgrades.py`, `app/routes_alerts_paid.py`, alert UI in `frontend/src/personalization-ui.js` |
| legal | `feat/legal-pages` | `frontend/public/{pricing,faq,privacy,terms}.html`, `site-info.css`, `sitemap.xml`, the `_PUBLIC_PAGES` map in `app/routes.py`, menu/footer links in `frontend/index.html` and `frontend/src/site-menu.js` |

Shared files:
- `app/__init__.py`: add one `include_router` line for your router module.
- `frontend/src/main.js`: add at most one import and one init call.
- `frontend/src/style.css`: append only, inside a block commented with your track name.
- `frontend/index.html`: avoid edits; build DOM from your JS module. The legal track may edit the menu and footer.
- Don't commit `static/`. It is build output; the integrator rebuilds it.

## Cross-track hook

- The ai track exports `app/ranking.py: rank_listings(criteria: dict, listings: list[dict], brief: str | None = None, limit: int = 10) -> list[dict]`. Each result has `zameen_id`, `reason` and `trade_off`, ordered best first.
- The alerts track's daily shortlist calls it through a lazy import with a simple fallback (newest and best price fit first) when it's missing.

## Working rules for every track

- Work only in your own worktree and branch. Commit locally. **Never push, open a PR or deploy.**
- Don't touch other worktrees, the shared checkout at `/Users/umarali/Workspace/MVPs/zameenrental`, or production. Never stop processes you didn't start.
- Browsers run headless only. Don't run `npx playwright install`. Use Node 22: `PATH="$HOME/.nvm/versions/node/v22.13.0/bin:$PATH"`. Use your track's Playwright port: payments 8220, ai 8230, alerts 8240, legal 8250 (`PLAYWRIGHT_PORT=<port>`).
- Python: `/Users/umarali/Workspace/MVPs/zameenrental-ci/.venv/bin/python -m pytest`.
- Mock Claude in automated tests. A handful of live Claude calls for a manual check is fine.
- Copy follows `docs/content-style.md`: sentence case, plain words, no promises without evidence.
