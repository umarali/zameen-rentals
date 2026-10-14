# Credit operations

## Current release boundary

Search is free. Each eligible new browser receives 10 starter credits. Each offered action uses one credit. The planned pack is 50 credits for Rs 500. Production checkout stays disabled until a merchant account and real-provider verification are complete.

The credit ledger records feature refunds. It does not yet implement provider cash refunds, partial-purchase refund reservations, or chargeback handling. Do not enable live sales until those flows are implemented and tested against the selected provider. A clean local ledger audit alone is insufficient.

## Starter credits

New wallet claims are limited to ten wallets per IPv4 address or IPv6 /64 network per UTC day. Only credit and paid-feature routes register a claim; free routes do not. This limits repeated browser resets without reducing an existing wallet's balance. A denied claim can retry on a later UTC day. Shared networks can reach the limit through legitimate visitors; free search, saved homes and existing credits still work. Distributed abuse is not prevented.

Before deploying this PR, pin the explicit proxy flags and verify two real client addresses through Caddy as described below. The server uses the connection address after the trusted proxy has handled forwarding, not a raw browser-supplied header. Keep uvicorn bound to localhost and trust only the local reverse proxy. The database stores a keyed fingerprint of the network and UTC date, never a raw address in the starter-claim table. Fingerprints and their per-day keys older than two days are cleared on the first new claim of each UTC day. Claim outcomes and ledger entries remain. Same-day declined claims use a read-only fast path. Monitor daily declined-claim counts for legitimate visitors sharing a carrier address.

## AI budget and repeated requests

The shared ranker reserves estimated cost in SQLite before a provider call. Concurrent web/crawler calls see the same reservations. Success replaces its reservation with reported token usage in one transaction. Definite API rejection responses and local argument TypeErrors release the reservation. Other response errors retain the reservation because billing may be ambiguous. If the provider times out, a connection failure is ambiguous, usage is absent or recording fails, the reservation stays against that UTC day's budget. Do not delete current-day reservations merely to unblock traffic: an uncertain call may have been billed.

The allowance is a conservative application estimate, not an invoice guarantee. The model price table uses standard global API pricing checked on 14 October 2026 at https://platform.claude.com/docs/en/about-claude/pricing. Sonnet 5.5 cache reads are $0.10 per million tokens. Requests are capped below the Haiku long-context threshold by a byte-based allowance plus protocol overhead. Reconcile token estimates with the provider invoice before relying on margin calculations. The existing natural-language search parser has separate accounting; this budget does not cover every use of the API key.

Starter and request claims use separate short-lived database connections to avoid committing or nesting another task's transaction. Request claims in SQLite prevent two workers from charging for the same active request or retry key. Completed results are reused for 15 minutes. A stale claim expires after the work deadline plus ten seconds. Process termination after a spend can still leave an undelivered charge; inspect interrupted jobs and refund the identified spend reference using `credits.refund`, which is idempotent. Normal exceptions, timeouts and cancellation return the credit. Keep the current one-worker deployment until broader multi-worker load testing has been completed.

Shortlist windows record a timestamp and match-ID boundary. Matches arriving during ranking are left for the next window, including arrivals in the same second. The candidate window remains the last 24 hours, as the UI states. Delayed or skipped runs can miss older matches; a daily shortlist is not a complete alert history. Old shortlist rows without a boundary use their timestamp as a migration fallback; a historical exact-boundary match can be reconsidered once. Failed shortlist storage returns the charge and a retry uses a deterministic attempt reference. An interrupted unrefunded retry reuses its charge, or returns it if its candidates have disappeared. Delivery means the shortlist is saved for viewing; a failed push does not erase the saved result.

## Read-only reconciliation

Run as an operator with database read access:

```sh
python tools/audit_credits.py /opt/zameenrentals/data/zameenrentals.db
```

The command opens a read-only SQLite snapshot, including WAL data. It checks payment/grant pairing, amounts, owners, orphan purchases, negative balances and spend refunds. It makes no network requests and never edits balances. Exit 0 means local records agree, 1 means discrepancies, and 2 means the database/schema could not be read.

For an unpaid payment with a provider reference, look up that exact transaction in the provider dashboard. Do not grant credits from a screenshot, return URL or browser status. Confirm the merchant account, transaction ID, PKR amount and final paid state. The application's verified webhook/status path must apply that confirmation. Pending, expired and failed local records can require reconciliation after a lost or delayed event.

## Cash refund procedure before sales

The approved consumer rule is unused purchased credits within seven days, valued at the price paid per credit. Starter credits have no cash value. The missing implementation must reserve the refundable unused credits before sending money, retain an idempotent provider refund reference, and either finalize the deduction after confirmed cash refund or release the reservation after confirmed failure. It must account for credits moved with restore codes and multiple purchases without refunding spent credits or paying twice after a retry. Never substitute an ordinary feature refund for a cash refund.

Safepay documents card refunds through its merchant dashboard within 90 days. Our seven-day consumer window is separate. See https://safepay.pk/legal/content/services-agreement and https://apidocs.getsafepay.com/. Actual supported methods, refund events and partial-refund behavior must be verified for the owner's merchant account. No live or sandbox credentials were available for this completion pass.

## Before enabling checkout

- Obtain the selected provider's merchant approval and sandbox credentials securely. Earlier preference was JazzCash/Easypaisa; the existing adapter is Safepay. Do not assume these are interchangeable.
- Verify hosted checkout, signed callbacks, wrong amount/currency, cancelled and expired payments, late success, status lookup and duplicate events in a real sandbox.
- Implement and verify the cash-refund reservation and settlement procedure above, including restored wallets, partial refunds and chargebacks.
- Check the provider's actual fees, tax treatment and measured AI usage against the Rs 500 pack. No margin claim is established by the token price table alone.
- Repair the pre-existing scheduled backup failure and complete a restore drill with the new credit tables.
- Resolve legal/operator-contact requirements before cash sales. No compliance or legal sign-off is claimed here.
- Remove the public top-up-unavailable notice only when checkout is actually ready. Change payment configuration as a separate reviewed release.

## Deployment gate for this follow-up

This is required before deploying the new starter limit, even while checkout is disabled.

1. Install the reviewed `deploy/credits-proxy.conf` as `/etc/systemd/system/zameenrentals-web.service.d/credits-proxy.conf`, run `systemctl daemon-reload`, and restart the web service during the authorized deployment. It preserves one worker and explicitly trusts forwarded headers only from `127.0.0.1`. Fresh hosts get the same flags from `deploy/user-data.sh`.
2. Send marked `/api/health` requests from two external networks, such as broadband and mobile data, through public HTTPS and inspect the corresponding uvicorn access-log client addresses. They must be non-loopback and map to distinct IPv4 /32 or IPv6 /64 buckets. Do not trust a TestClient or spoofed header test as proof of this production path.
3. Recheck the web command and both health endpoints after deployment. Do not deploy the starter limit if either real-client address collapses to the local proxy address.

Re-verify client addresses before enabling a CDN proxy such as Cloudflare. Configure the trusted proxy chain and real client address header first; CDN edge addresses must not become starter-credit buckets.

The completion pass verified two distinct buckets through the existing production Caddy path using this computer and a server-origin request through public HTTPS, before the proposed flag pinning. This is weaker than two external-network probes. Repeat after applying the drop-in. The drop-in has not been installed by this PR preparation.
