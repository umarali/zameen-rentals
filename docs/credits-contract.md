# Credits and paid features: shared contract

The integrated contract for credits and paid features. Historical branch ownership is retained below for context.

## Product rules

- Search, filters, maps, contacts, saved homes, comparisons and today's alerts stay free. A paid feature must add something; it must never make a free feature worse.
- No subscription and no renewal. People buy a credit pack once and spend credits on paid actions.
- Eligible new visitors get `STARTER_CREDITS` (10) free credits, subject to repeated-claim limits per network. One credit buys one use of any offered paid feature. Credits do not expire.
- Refund requests within seven days cover unused purchased credits at their actual purchase price, including partly used packs. Requests use Send feedback; real-provider cash-refund processing still needs verification before live sales.
- Packs and costs live only in `app/credits.py` (`PACKS`, `COSTS`). Read them from there or from `GET /api/credits`. Never hard-code numbers in copy or UI.

| Action key | Credits | Owner track |
|---|---|---|
| `tailored_list` | 1 | ai |
| `search_report` | 1 | ai |
| `daily_shortlist_day` | 1 per delivered day per saved search | alerts |
| `instant_alerts_day` | Not offered | retained for experiments and historical records |
| `listing_history` | 1 per listing | later, not in this round |

| Pack | Credits | PKR |
|---|---|---|
| standard | 50 | 500 |

## Backend interface (`app/credits.py`)

- `balance(client_id) -> int`. Starter credits require an accepted network claim; existing starter balances are preserved.
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

## Maintenance

The feature branches have been integrated. Credits, payments, AI and alert code now ship together; the old branch ownership split is historical. Edit source under `app/` and `frontend/`, and rebuild `static/` without committing generated assets.

See [Credit operations](credits-operations.md) for starter-claim limits, AI budget reservations, reconciliation and the remaining prerequisites for cash sales.

## Cross-track hook

- The ai track exports `app/ranking.py: rank_listings(criteria: dict, listings: list[dict], brief: str | None = None, limit: int = 10) -> list[dict]`. Each result has `zameen_id`, `reason` and `trade_off`, ordered best first.
- The alerts track's daily shortlist calls it through a lazy import with a simple fallback (newest and best price fit first) when it's missing.
