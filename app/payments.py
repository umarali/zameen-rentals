"""Payments: one-time credit pack purchases and restore codes.

Flow
----
1. The browser asks for a pack (`POST /api/credits/checkout {pack_id}`). The
   server looks up the price and credit count in `credits.PACKS`, stores a
   `pending` row in `payments`, asks the active provider for a hosted checkout
   URL and returns it. The browser never sends an amount.
2. The renter pays on the provider's page and comes back to `/pay/return`.
3. Credits are granted only after a server-side confirmation is verified:
   either a webhook whose signature checks out (constant-time compare), or a
   server-to-server status lookup made with the merchant secret. The
   confirmed amount and currency must match the stored pack price.
4. The grant uses `credits.grant(..., ref=f"payment:{id}")`, which is unique
   in the ledger, so replayed or duplicate confirmations add nothing.

Providers
---------
`PAYMENTS_PROVIDER` picks one: `safepay`, `test`, or unset (checkout off).

- `test` runs a local checkout page with Pay and Cancel buttons. It signs its
  confirmation with HMAC-SHA256 and feeds it through the same verification
  path as a real webhook. It refuses to run unless `ZR_ENV` is explicitly a
  non-production value (development, dev, test, local, ci).
- `safepay` follows Safepay's Express Checkout guide and webhook docs. See
  SafepayProvider for the sources. Sandbox mode is refused when
  `ZR_ENV=production`, because sandbox test cards would mint real credits.

Restore codes
-------------
After a client's first paid purchase it gets a 16-character restore code
(80 bits, Crockford base32 alphabet, shown as XXXX-XXXX-XXXX-XXXX). Only the
SHA-256 of the normalised code is stored, and the plaintext is returned once.
Entering the code on another device moves the purchased part of the balance
(see `transferable_credits`) to that device with a `restore_out`/`restore_in`
pair written in one transaction, and the code then belongs to the new device.
Starter credits stay where they were granted, so codes can't be used to pool
free starter credits from many browsers.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import secrets
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable, Protocol
from urllib.parse import urlencode

from app import credits
from app.database import _get_conn

logger = logging.getLogger("zameenrentals")

STATUSES = ("pending", "paid", "failed", "expired")
# Safepay's hosted checkout token lasts one hour; nothing we create should
# stay payable for longer than that.
PENDING_TTL = timedelta(hours=1)
MAX_OPEN_CHECKOUTS_PER_CLIENT = 5
LOOKUP_MIN_INTERVAL = timedelta(seconds=4)
MAX_WEBHOOK_BYTES = 64 * 1024

# Values of ZR_ENV that allow the test provider. Anything else, including an
# unset ZR_ENV, refuses it.
NON_PRODUCTION_ENVS = {"development", "dev", "test", "local", "ci"}


class PaymentsError(Exception):
    """Base error; `status` is the HTTP status the route should use."""
    status = 400


class PaymentsUnavailable(PaymentsError):
    status = 503


class InvalidSignature(PaymentsError):
    status = 400


class UnknownPack(PaymentsError):
    status = 400


class TooManyCheckouts(PaymentsError):
    status = 429


# ── Environment ─────────────────────────────────────────────────────────────


def zr_env() -> str:
    return (os.getenv("ZR_ENV") or "").strip().lower()


def is_production() -> bool:
    return zr_env() == "production"


def test_mode_allowed() -> bool:
    return zr_env() in NON_PRODUCTION_ENVS


# ── Provider interface ──────────────────────────────────────────────────────


@dataclass
class Checkout:
    redirect_url: str
    provider_ref: str | None = None


@dataclass
class Confirmation:
    """A verified statement from a provider about one payment.

    outcome is one of: paid, failed, expired, pending, ignored.
    amount_minor is in paisa (PKR * 100) when the provider reports it.
    """
    outcome: str
    payment_id: str | None = None
    provider_ref: str | None = None
    amount_minor: int | None = None
    currency: str | None = None
    event: str | None = None
    extra: dict = field(default_factory=dict)


class Provider(Protocol):
    name: str

    def create_checkout(self, payment: dict, *, return_url: str, cancel_url: str) -> Checkout: ...

    def verify_webhook(self, headers: dict, raw_body: bytes) -> Confirmation:
        """Raise InvalidSignature unless the body is provably from the provider."""
        ...

    def lookup(self, payment: dict) -> Confirmation | None:
        """Server-to-server status check, or None if the provider has none."""
        ...


def _lower_headers(headers) -> dict:
    return {str(k).lower(): v for k, v in dict(headers).items()}


# ── Test provider ───────────────────────────────────────────────────────────


TEST_SIGNATURE_HEADER = "x-zr-test-signature"
_PROCESS_TEST_SECRET = secrets.token_hex(32)


def _test_secret() -> bytes:
    return (os.getenv("PAYMENTS_TEST_SECRET") or _PROCESS_TEST_SECRET).encode()


class TestProvider:
    """Local checkout for development and automated tests. Never production."""
    name = "test"

    def __init__(self):
        if not test_mode_allowed():
            raise PaymentsUnavailable(
                "Test payments need ZR_ENV set to a non-production value "
                f"({', '.join(sorted(NON_PRODUCTION_ENVS))})"
            )

    def create_checkout(self, payment: dict, *, return_url: str, cancel_url: str) -> Checkout:
        return Checkout(redirect_url=f"/pay/test/{payment['id']}", provider_ref=f"test_{payment['id']}")

    @staticmethod
    def sign(raw_body: bytes) -> str:
        return hmac.new(_test_secret(), raw_body, hashlib.sha256).hexdigest()

    def build_event(self, payment: dict, outcome: str) -> tuple[dict, bytes]:
        """The signed confirmation the test checkout page sends to itself."""
        body = json.dumps({
            "event_id": f"evt_{uuid.uuid4().hex}",
            "payment_id": payment["id"],
            "outcome": outcome,
            "amount": payment["amount_pkr"] * 100,
            "currency": "PKR",
        }, separators=(",", ":")).encode()
        return {TEST_SIGNATURE_HEADER: self.sign(body)}, body

    def verify_webhook(self, headers: dict, raw_body: bytes) -> Confirmation:
        sig = (_lower_headers(headers).get(TEST_SIGNATURE_HEADER) or "").strip().lower()
        if not sig or not hmac.compare_digest(self.sign(raw_body), sig):
            raise InvalidSignature("bad test signature")
        try:
            data = json.loads(raw_body)
        except ValueError as exc:
            raise InvalidSignature("unreadable body") from exc
        outcome = {"paid": "paid", "failed": "failed", "cancelled": "failed"}.get(data.get("outcome"), "ignored")
        return Confirmation(
            outcome=outcome,
            payment_id=data.get("payment_id"),
            amount_minor=_int_or_none(data.get("amount")),
            currency=data.get("currency"),
            event=data.get("event_id"),
        )

    def lookup(self, payment: dict) -> Confirmation | None:
        return None


# ── Safepay ─────────────────────────────────────────────────────────────────


HttpCall = Callable[[str, str, dict, dict | None], dict]


def _default_http(method: str, url: str, headers: dict, body: dict | None) -> dict:
    import httpx
    resp = httpx.request(method, url, headers=headers, json=body, timeout=15)
    resp.raise_for_status()
    return resp.json()


class SafepayProvider:
    """Safepay hosted checkout (cards; Raast where enabled on the account).

    Sources, checked 2026-10-11:
    - Express Checkout guide: create a tracker with POST /order/payments/v3/,
      get a time-based token from POST /client/passport/v1/token, send the
      shopper to the embedded checkout URL, read ?tracker= on return, confirm
      with GET /reporter/api/v1/payments/{tracker} (state TRACKER_ENDED).
      https://safepay-docs.netlify.app/build-your-integration/express-checkout/
    - Amounts are in the lowest denomination (paisa for PKR). Same guide.
    - Auth header X-SFPY-MERCHANT-SECRET: API Reference, "API Authentication".
      https://apidocs.getsafepay.com/
    - Checkout URL hosts and query parameters: official SDKs
      github.com/getsafepay/node-core src/Checkout.ts and
      github.com/getsafepay/sfpy-php lib/Checkout.php.
    - Webhooks: header X-SFPY-SIGNATURE = hex HMAC-SHA512 of the JSON payload
      with the endpoint's shared secret.
      https://safepay-docs.netlify.app/developers/webhooks/verify-hmac-signatures/
      and sfpy-php lib/WebhookSignature.php.
    - Event payloads (payment.succeeded / payment.failed, data.tracker,
      data.amount, data.currency, data.metadata):
      https://safepay-docs.netlify.app/developers/webhooks/webhook-types/
    """
    name = "safepay"

    API_BASE = {
        "sandbox": "https://sandbox.api.getsafepay.com",
        "production": "https://api.getsafepay.com",
    }
    CHECKOUT_BASE = {
        "sandbox": "https://sandbox.api.getsafepay.com/embedded/",
        "production": "https://getsafepay.com/embedded/",
    }
    SIGNATURE_HEADER = "x-sfpy-signature"

    def __init__(self, *, env: str, api_key: str, secret_key: str, webhook_secret: str,
                 http: HttpCall | None = None):
        if env not in self.API_BASE:
            raise PaymentsUnavailable("SAFEPAY_ENV must be sandbox or production")
        missing = [n for n, v in (("SAFEPAY_API_KEY", api_key), ("SAFEPAY_SECRET_KEY", secret_key),
                                  ("SAFEPAY_WEBHOOK_SECRET", webhook_secret)) if not v]
        if missing:
            raise PaymentsUnavailable(f"Safepay is missing {', '.join(missing)}")
        if env == "sandbox" and not test_mode_allowed():
            raise PaymentsUnavailable("Safepay sandbox needs an explicit non-production ZR_ENV")
        self.env = env
        self.api_key = api_key
        self._secret_key = secret_key
        self._webhook_secret = webhook_secret.encode()
        self._http = http or _default_http

    @classmethod
    def from_env(cls) -> "SafepayProvider":
        return cls(
            env=(os.getenv("SAFEPAY_ENV") or "").strip().lower(),
            api_key=(os.getenv("SAFEPAY_API_KEY") or "").strip(),
            secret_key=(os.getenv("SAFEPAY_SECRET_KEY") or "").strip(),
            webhook_secret=(os.getenv("SAFEPAY_WEBHOOK_SECRET") or "").strip(),
        )

    def _auth(self) -> dict:
        return {"X-SFPY-MERCHANT-SECRET": self._secret_key, "Content-Type": "application/json"}

    def create_checkout(self, payment: dict, *, return_url: str, cancel_url: str) -> Checkout:
        base = self.API_BASE[self.env]
        setup = self._http("POST", f"{base}/order/payments/v3/", self._auth(), {
            "merchant_api_key": self.api_key,
            "intent": "CYBERSOURCE",
            "mode": "payment",
            "entry_mode": "raw",
            "currency": "PKR",
            "amount": payment["amount_pkr"] * 100,
            "metadata": {"order_id": payment["id"]},
        })
        tracker = ((setup.get("data") or {}).get("tracker") or {}).get("token")
        if not tracker:
            raise PaymentsUnavailable("Safepay did not return a tracker")
        token = self._http("POST", f"{base}/client/passport/v1/token", self._auth(), None).get("data")
        if not token or not isinstance(token, str):
            raise PaymentsUnavailable("Safepay did not return a checkout token")
        query = urlencode({
            "environment": self.env,
            "tracker": tracker,
            "tbt": token,
            "source": "hosted",
            "redirect_url": return_url,
            "cancel_url": cancel_url,
        })
        return Checkout(redirect_url=f"{self.CHECKOUT_BASE[self.env]}?{query}", provider_ref=tracker)

    def _signature_matches(self, raw_body: bytes, signature: str) -> bool:
        # The docs sign "the JSON payload": the Node guide uses
        # JSON.stringify(body) and the PHP example re-encodes the parsed body
        # with json_encode(..., JSON_UNESCAPED_SLASHES). Accept the raw bytes
        # or either compact re-encoding of the same parsed body. Each candidate
        # is checked with the secret, so this widens nothing for a forger.
        candidates = [raw_body]
        try:
            parsed = json.loads(raw_body)
        except ValueError:
            parsed = None
        if parsed is not None:
            for ensure_ascii in (False, True):
                encoded = json.dumps(parsed, separators=(",", ":"), ensure_ascii=ensure_ascii).encode()
                if encoded not in candidates:
                    candidates.append(encoded)
        ok = False
        for candidate in candidates:
            expected = hmac.new(self._webhook_secret, candidate, hashlib.sha512).hexdigest()
            ok |= hmac.compare_digest(expected, signature)
        return ok

    def verify_webhook(self, headers: dict, raw_body: bytes) -> Confirmation:
        signature = (_lower_headers(headers).get(self.SIGNATURE_HEADER) or "").strip().lower()
        if not signature or not self._signature_matches(raw_body, signature):
            raise InvalidSignature("bad Safepay signature")
        try:
            event = json.loads(raw_body)
        except ValueError as exc:
            raise InvalidSignature("unreadable body") from exc
        data = event.get("data") or {}
        kind = event.get("type")
        outcome = {"payment.succeeded": "paid", "payment.failed": "failed"}.get(kind, "ignored")
        metadata = data.get("metadata") or {}
        order_id = metadata.get("order_id")
        if isinstance(order_id, dict):  # reporter-style metadata objects
            order_id = order_id.get("value")
        return Confirmation(
            outcome=outcome,
            payment_id=order_id if isinstance(order_id, str) else None,
            provider_ref=data.get("tracker"),
            amount_minor=_int_or_none(data.get("amount")),
            currency=data.get("currency"),
            event=f"{kind}:{event.get('token')}",
        )

    def lookup(self, payment: dict) -> Confirmation | None:
        tracker = payment.get("provider_ref")
        if not tracker:
            return None
        base = self.API_BASE[self.env]
        body = self._http("GET", f"{base}/reporter/api/v1/payments/{tracker}", self._auth(), None)
        data = body.get("data") or {}
        # The Express Checkout guide shows data.tracker.state; the Fetch
        # Tracker page shows data.state. Accept either.
        info = data.get("tracker") if isinstance(data.get("tracker"), dict) else data
        if info.get("token") and info.get("token") != tracker:
            return Confirmation(outcome="ignored", provider_ref=tracker, event="lookup:token-mismatch")
        state = info.get("state")
        totals = (info.get("purchase_totals") or {}).get("quote_amount") or {}
        outcome = {
            "TRACKER_ENDED": "paid",
            "TRACKER_CANCELLED": "failed",
            "TRACKER_EXPIRED": "expired",
        }.get(state, "pending")
        return Confirmation(
            outcome=outcome,
            provider_ref=tracker,
            amount_minor=_int_or_none(totals.get("amount")),
            currency=totals.get("currency"),
            event=f"lookup:{state}",
        )


# ── Provider selection ──────────────────────────────────────────────────────


def provider_name() -> str:
    return (os.getenv("PAYMENTS_PROVIDER") or "").strip().lower()


def get_provider(name: str | None = None) -> Provider:
    """The configured provider. Raises PaymentsUnavailable if none can run.

    Reads the environment on every call so a misconfiguration is refused
    at the point of use instead of at import time.
    """
    configured = provider_name()
    if name is not None and name != configured:
        raise PaymentsUnavailable(f"provider {name!r} is not enabled")
    if configured == "test":
        if not test_mode_allowed():
            logger.error("payments: PAYMENTS_PROVIDER=test refused (ZR_ENV=%r)", zr_env() or None)
        return TestProvider()
    if configured == "safepay":
        return SafepayProvider.from_env()
    raise PaymentsUnavailable("Payments are not set up")


def checkout_available() -> bool:
    try:
        get_provider()
        return True
    except PaymentsUnavailable:
        return False


# ── Schema ──────────────────────────────────────────────────────────────────


def init_payments_schema(conn=None):
    conn = conn or _get_conn()
    with conn:
        conn.executescript(f"""
            CREATE TABLE IF NOT EXISTS payments (
                id              TEXT PRIMARY KEY,
                client_id       TEXT NOT NULL,
                pack_id         TEXT NOT NULL,
                amount_pkr      INTEGER NOT NULL,
                credits         INTEGER NOT NULL,
                provider        TEXT NOT NULL,
                provider_ref    TEXT,
                status          TEXT NOT NULL DEFAULT 'pending'
                                CHECK (status IN ({", ".join(repr(s) for s in STATUSES)})),
                created_at      TEXT NOT NULL DEFAULT (datetime('now')),
                paid_at         TEXT,
                updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
                last_checked_at TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_payments_client ON payments(client_id, created_at);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_payments_provider_ref
                ON payments(provider, provider_ref) WHERE provider_ref IS NOT NULL;

            CREATE TABLE IF NOT EXISTS restore_codes (
                code_hash    TEXT PRIMARY KEY,
                client_id    TEXT NOT NULL UNIQUE,
                created_at   TEXT NOT NULL DEFAULT (datetime('now')),
                last_used_at TEXT
            );
        """)


# ── Payments ────────────────────────────────────────────────────────────────


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _ts(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _int_or_none(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _short(client_id: str) -> str:
    return (client_id or "")[:6] + "…"


def get_payment(payment_id: str) -> dict | None:
    row = _get_conn().execute("SELECT * FROM payments WHERE id = ?", (payment_id,)).fetchone()
    return dict(row) if row else None


def _payment_by_ref(provider: str, provider_ref: str) -> dict | None:
    row = _get_conn().execute(
        "SELECT * FROM payments WHERE provider = ? AND provider_ref = ?", (provider, provider_ref)
    ).fetchone()
    return dict(row) if row else None


def create_payment(client_id: str, pack_id: str, provider: Provider) -> dict:
    """Insert a pending payment priced from credits.PACKS (never from input)."""
    pack = credits.PACKS.get(pack_id)
    if not pack:
        raise UnknownPack("Unknown pack")
    conn = _get_conn()
    cutoff = _ts(_now() - PENDING_TTL)
    with conn:
        open_count = conn.execute(
            "SELECT COUNT(*) FROM payments WHERE client_id = ? AND status = 'pending' AND created_at > ?",
            (client_id, cutoff),
        ).fetchone()[0]
        if open_count >= MAX_OPEN_CHECKOUTS_PER_CLIENT:
            raise TooManyCheckouts("Too many open checkouts. Try again in an hour.")
        payment_id = f"pay_{secrets.token_hex(12)}"
        conn.execute(
            """INSERT INTO payments (id, client_id, pack_id, amount_pkr, credits, provider)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (payment_id, client_id, pack_id, int(pack["price_pkr"]), int(pack["credits"]), provider.name),
        )
    logger.info("payment created id=%s client=%s pack=%s provider=%s",
                payment_id, _short(client_id), pack_id, provider.name)
    return get_payment(payment_id)


def attach_provider_ref(payment_id: str, provider_ref: str | None):
    if not provider_ref:
        return
    conn = _get_conn()
    with conn:
        conn.execute(
            "UPDATE payments SET provider_ref = ?, updated_at = datetime('now') WHERE id = ? AND provider_ref IS NULL",
            (provider_ref, payment_id),
        )


def mark_failed_to_start(payment_id: str):
    conn = _get_conn()
    with conn:
        conn.execute(
            "UPDATE payments SET status = 'failed', updated_at = datetime('now') WHERE id = ? AND status = 'pending'",
            (payment_id,),
        )


def apply_confirmation(provider: Provider, conf: Confirmation) -> dict | None:
    """Apply a verified confirmation. Returns the payment row after the update.

    Paid confirmations grant credits only when the amount and currency match
    the stored pack price. A paid payment is never moved back to failed.
    """
    payment = None
    if conf.provider_ref:
        payment = _payment_by_ref(provider.name, conf.provider_ref)
    if payment is None and conf.payment_id:
        payment = get_payment(conf.payment_id)
        if payment and conf.provider_ref and payment.get("provider_ref") not in (None, conf.provider_ref):
            payment = None
    if payment is None or payment["provider"] != provider.name:
        logger.warning("payment event for unknown payment provider=%s event=%s", provider.name, conf.event)
        return None

    pid = payment["id"]
    if conf.outcome == "paid":
        expected = payment["amount_pkr"] * 100
        if conf.amount_minor != expected or (conf.currency or "").upper() != "PKR":
            logger.error("payment amount mismatch id=%s provider=%s expected=%s got=%s %s event=%s",
                         pid, provider.name, expected, conf.amount_minor, conf.currency, conf.event)
            return payment
        granted = credits.grant(payment["client_id"], payment["credits"], kind="purchase", ref=f"payment:{pid}")
        conn = _get_conn()
        with conn:
            conn.execute(
                """UPDATE payments SET status = 'paid', paid_at = COALESCE(paid_at, datetime('now')),
                       provider_ref = COALESCE(provider_ref, ?), updated_at = datetime('now')
                   WHERE id = ?""",
                (conf.provider_ref, pid),
            )
        logger.info("payment paid id=%s client=%s credits=%s granted=%s event=%s",
                    pid, _short(payment["client_id"]), payment["credits"], granted, conf.event)
    elif conf.outcome in ("failed", "expired"):
        conn = _get_conn()
        with conn:
            conn.execute(
                "UPDATE payments SET status = ?, updated_at = datetime('now') WHERE id = ? AND status != 'paid'",
                (conf.outcome, pid),
            )
        logger.info("payment %s id=%s event=%s", conf.outcome, pid, conf.event)
    else:
        logger.info("payment event ignored id=%s outcome=%s event=%s", pid, conf.outcome, conf.event)
    return get_payment(pid)


def handle_webhook(provider_name_: str, headers: dict, raw_body: bytes) -> dict | None:
    """Verify and apply a provider confirmation. Raises InvalidSignature."""
    provider = get_provider(provider_name_)
    if len(raw_body) > MAX_WEBHOOK_BYTES:
        raise InvalidSignature("body too large")
    try:
        conf = provider.verify_webhook(headers, raw_body)
    except InvalidSignature:
        logger.warning("payment webhook rejected provider=%s reason=signature bytes=%d",
                       provider.name, len(raw_body))
        raise
    return apply_confirmation(provider, conf)


async def refresh_payment(payment: dict) -> dict:
    """For a pending payment: ask the provider (throttled), then expire if stale.

    Only the provider's network call runs in a worker thread. Every database
    read and write stays on the caller's (event loop) thread, because the app
    shares one SQLite connection and restore() relies on its transaction not
    being interleaved with writes from another thread.
    """
    from fastapi.concurrency import run_in_threadpool

    if payment["status"] != "pending":
        return payment
    now = _now()
    last = payment.get("last_checked_at")
    due = not last or now - datetime.strptime(last, "%Y-%m-%d %H:%M:%S") >= LOOKUP_MIN_INTERVAL
    if due and payment.get("provider_ref"):
        try:
            provider = get_provider(payment["provider"])
            conn = _get_conn()
            with conn:
                conn.execute("UPDATE payments SET last_checked_at = ? WHERE id = ?", (_ts(now), payment["id"]))
            conf = await run_in_threadpool(provider.lookup, dict(payment))
            if conf is not None:
                conf.provider_ref = conf.provider_ref or payment["provider_ref"]
                payment = apply_confirmation(provider, conf) or get_payment(payment["id"])
        except PaymentsUnavailable:
            pass
        except Exception:
            logger.exception("payment lookup failed id=%s", payment["id"])
    created = datetime.strptime(payment["created_at"], "%Y-%m-%d %H:%M:%S")
    if payment["status"] == "pending" and now - created > PENDING_TTL:
        conn = _get_conn()
        with conn:
            conn.execute(
                "UPDATE payments SET status = 'expired', updated_at = datetime('now') WHERE id = ? AND status = 'pending'",
                (payment["id"],),
            )
        payment = get_payment(payment["id"])
    return payment


def public_payment(payment: dict) -> dict:
    return {
        "payment_id": payment["id"],
        "status": payment["status"],
        "pack_id": payment["pack_id"],
        "credits": payment["credits"],
        "amount_pkr": payment["amount_pkr"],
        "created_at": payment["created_at"],
        "paid_at": payment["paid_at"],
    }


def has_purchases(client_id: str) -> bool:
    return _get_conn().execute(
        "SELECT 1 FROM payments WHERE client_id = ? AND status = 'paid' LIMIT 1", (client_id,)
    ).fetchone() is not None


# ── Restore codes ───────────────────────────────────────────────────────────

# Crockford base32: no I, L, O or U, so codes read aloud or copied by hand
# are hard to get wrong. 16 symbols * 5 bits = 80 bits of entropy.
CODE_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
CODE_LENGTH = 16
_CODE_FIXUPS = str.maketrans({"O": "0", "I": "1", "L": "1"})


def _new_code() -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))


def format_code(code: str) -> str:
    return "-".join(code[i:i + 4] for i in range(0, len(code), 4))


def normalize_code(raw: str) -> str | None:
    if not isinstance(raw, str):
        return None
    code = "".join(ch for ch in raw.upper() if ch.isalnum()).translate(_CODE_FIXUPS)
    if len(code) != CODE_LENGTH or any(ch not in CODE_ALPHABET for ch in code):
        return None
    return code


def _hash_code(code: str) -> str:
    return hashlib.sha256(f"zr-restore:{code}".encode()).hexdigest()


def has_restore_code(client_id: str) -> bool:
    return _get_conn().execute(
        "SELECT 1 FROM restore_codes WHERE client_id = ?", (client_id,)
    ).fetchone() is not None


def issue_restore_code(client_id: str, *, replace: bool = False) -> str | None:
    """Create (or with replace=True, rotate) the client's code. Returns plaintext once.

    Returns None when the client already has a code and replace is False.
    """
    code = _new_code()
    conn = _get_conn()
    with conn:
        if replace:
            conn.execute("DELETE FROM restore_codes WHERE client_id = ?", (client_id,))
        cur = conn.execute(
            "INSERT OR IGNORE INTO restore_codes (code_hash, client_id) VALUES (?, ?)",
            (_hash_code(code), client_id),
        )
    if cur.rowcount != 1:
        return None
    logger.info("restore code %s client=%s", "rotated" if replace else "issued", _short(client_id))
    return format_code(code)


def transferable_credits(conn, client_id: str) -> int:
    """Purchased credits still on this client: min(balance, purchases + restores in - restores out)."""
    row = conn.execute(
        """SELECT COALESCE(SUM(delta), 0) AS balance,
                  COALESCE(SUM(CASE WHEN kind IN ('purchase', 'restore_in', 'restore_out') THEN delta END), 0) AS paid
           FROM credit_ledger WHERE client_id = ?""",
        (client_id,),
    ).fetchone()
    return max(0, min(int(row["balance"]), int(row["paid"])))


class RestoreFailed(PaymentsError):
    status = 404


def restore(raw_code: str, to_client: str) -> dict:
    """Move purchased credits held under `raw_code` to `to_client`.

    Atomic: both ledger rows and the code's new owner are written in one
    IMMEDIATE transaction. Replaying the same request from the same device
    finds the code already there and changes nothing.
    """
    code = normalize_code(raw_code)
    if code is None:
        raise RestoreFailed("That code doesn't look right")
    credits.balance(to_client)  # make sure the destination has its starter row
    conn = _get_conn()
    moved = 0
    if conn.in_transaction:
        conn.commit()
    conn.execute("BEGIN IMMEDIATE")
    try:
        row = conn.execute("SELECT client_id FROM restore_codes WHERE code_hash = ?", (_hash_code(code),)).fetchone()
        if row is None:
            conn.rollback()
            logger.info("restore code not found to=%s", _short(to_client))
            raise RestoreFailed("That code didn't match")
        from_client = row["client_id"]
        if from_client != to_client:
            moved = transferable_credits(conn, from_client)
            if moved > 0:
                ref = uuid.uuid4().hex
                conn.execute(
                    "INSERT INTO credit_ledger (client_id, delta, kind, ref) VALUES (?, ?, 'restore_out', ?)",
                    (from_client, -moved, f"restore_out:{ref}"),
                )
                conn.execute(
                    "INSERT INTO credit_ledger (client_id, delta, kind, ref) VALUES (?, ?, 'restore_in', ?)",
                    (to_client, moved, f"restore_in:{ref}"),
                )
            # One code per client: the destination's own code (if any) is
            # replaced by the one that now carries its purchased credits.
            conn.execute("DELETE FROM restore_codes WHERE client_id = ?", (to_client,))
            conn.execute(
                "UPDATE restore_codes SET client_id = ?, last_used_at = datetime('now') WHERE code_hash = ?",
                (to_client, _hash_code(code)),
            )
        conn.commit()
    except RestoreFailed:
        raise
    except Exception:
        conn.rollback()
        raise
    if from_client != to_client:
        logger.info("restore moved=%d from=%s to=%s", moved, _short(from_client), _short(to_client))
    return {"moved": moved, "same_device": from_client == to_client, "balance": credits.balance(to_client)}
