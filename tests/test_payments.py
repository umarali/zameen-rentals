"""Payments: verified confirmations, idempotent grants, restore codes, test-mode safety."""
import hashlib
import hmac
import json

import pytest
from fastapi import APIRouter, HTTPException, Request
from fastapi.testclient import TestClient

from app import app, credits, payments
from app.cache import limiter

CLIENT = "client-payments-aaaa"
OTHER = "client-payments-bbbb"
THIRD = "client-payments-cccc"
TEST_SECRET = "unit-test-secret"
SAFEPAY_WEBHOOK_SECRET = "c44e1b93160e1ccd34ea9c40e79f5f11ea276105b563c53d9ca59e4eb8477686"


@pytest.fixture(autouse=True)
def schema(fresh_db, monkeypatch):
    credits.init_credits_schema()
    payments.init_payments_schema()
    limiter.reset()
    monkeypatch.setenv("PAYMENTS_PROVIDER", "test")
    monkeypatch.setenv("ZR_ENV", "test")
    monkeypatch.setenv("PAYMENTS_TEST_SECRET", TEST_SECRET)
    yield
    limiter.reset()


@pytest.fixture
def client():
    return TestClient(app)


def H(client_id=CLIENT):
    return {"X-Client-Id": client_id}


def _checkout(client, pack_id="standard", client_id=CLIENT):
    resp = client.post("/api/credits/checkout", headers=H(client_id), json={"pack_id": pack_id})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _signed_test_event(payment_id, outcome="paid", amount=None, currency="PKR", event_id="evt_1"):
    payment = payments.get_payment(payment_id)
    body = json.dumps({
        "event_id": event_id, "payment_id": payment_id, "outcome": outcome,
        "amount": payment["amount_pkr"] * 100 if amount is None else amount, "currency": currency,
    }).encode()
    sig = hmac.new(TEST_SECRET.encode(), body, hashlib.sha256).hexdigest()
    return body, {"X-ZR-Test-Signature": sig, "Content-Type": "application/json"}


# ── Checkout ────────────────────────────────────────────────────────────────


def test_checkout_prices_come_from_server_packs(client):
    out = _checkout(client, "small")
    payment = payments.get_payment(out["payment_id"])
    assert payment["amount_pkr"] == credits.PACKS["small"]["price_pkr"]
    assert payment["credits"] == credits.PACKS["small"]["credits"]
    assert payment["status"] == "pending"


def test_checkout_ignores_browser_amounts(client):
    resp = client.post("/api/credits/checkout", headers=H(),
                       json={"pack_id": "large", "amount_pkr": 1, "credits": 99999})
    payment = payments.get_payment(resp.json()["payment_id"])
    assert (payment["amount_pkr"], payment["credits"]) == (999, 130)


def test_checkout_rejects_unknown_pack_and_missing_identity(client):
    assert client.post("/api/credits/checkout", headers=H(), json={"pack_id": "huge"}).status_code == 400
    assert client.post("/api/credits/checkout", json={"pack_id": "small"}).status_code == 400


def test_checkout_limits_open_payments_per_client(client):
    for _ in range(payments.MAX_OPEN_CHECKOUTS_PER_CLIENT):
        _checkout(client)
    assert client.post("/api/credits/checkout", headers=H(), json={"pack_id": "small"}).status_code == 429


def test_checkout_is_off_without_a_provider(client, monkeypatch):
    monkeypatch.delenv("PAYMENTS_PROVIDER")
    assert client.post("/api/credits/checkout", headers=H(), json={"pack_id": "small"}).status_code == 503
    assert client.get("/api/credits", headers=H()).json()["checkout_available"] is False


# ── Verified confirmations ─────────────────────────────────────────────────


def test_valid_webhook_grants_once_and_replays_change_nothing(client):
    pid = _checkout(client)["payment_id"]
    body, headers = _signed_test_event(pid)
    for _ in range(3):
        assert client.post("/api/payments/webhook/test", content=body, headers=headers).status_code == 200
    # A second, distinct paid event for the same payment is also a no-op.
    body2, headers2 = _signed_test_event(pid, event_id="evt_2")
    assert client.post("/api/payments/webhook/test", content=body2, headers=headers2).status_code == 200
    assert credits.balance(CLIENT) == credits.STARTER_CREDITS + 60
    status = client.get(f"/api/payments/{pid}", headers=H()).json()
    assert status["status"] == "paid" and status["balance"] == credits.STARTER_CREDITS + 60


def test_bad_signature_is_rejected_and_grants_nothing(client):
    pid = _checkout(client)["payment_id"]
    body, headers = _signed_test_event(pid)
    tampered = body.replace(b'"paid"', b'"paid" ')
    assert client.post("/api/payments/webhook/test", content=tampered, headers=headers).status_code == 400
    assert client.post("/api/payments/webhook/test", content=body,
                       headers={"X-ZR-Test-Signature": "0" * 64}).status_code == 400
    assert client.post("/api/payments/webhook/test", content=body).status_code == 400
    assert credits.balance(CLIENT) == credits.STARTER_CREDITS
    assert payments.get_payment(pid)["status"] == "pending"


def test_amount_mismatch_never_grants(client):
    pid = _checkout(client, "large")["payment_id"]
    body, headers = _signed_test_event(pid, amount=100)
    assert client.post("/api/payments/webhook/test", content=body, headers=headers).status_code == 200
    body, headers = _signed_test_event(pid, currency="USD", event_id="evt_usd")
    client.post("/api/payments/webhook/test", content=body, headers=headers)
    assert credits.balance(CLIENT) == credits.STARTER_CREDITS
    assert payments.get_payment(pid)["status"] == "pending"


def test_failed_then_paid_is_honoured_but_paid_never_downgrades(client):
    pid = _checkout(client)["payment_id"]
    body, headers = _signed_test_event(pid, outcome="failed", event_id="e1")
    client.post("/api/payments/webhook/test", content=body, headers=headers)
    assert payments.get_payment(pid)["status"] == "failed"
    body, headers = _signed_test_event(pid, outcome="paid", event_id="e2")
    client.post("/api/payments/webhook/test", content=body, headers=headers)
    body, headers = _signed_test_event(pid, outcome="failed", event_id="e3")
    client.post("/api/payments/webhook/test", content=body, headers=headers)
    assert payments.get_payment(pid)["status"] == "paid"
    assert credits.balance(CLIENT) == credits.STARTER_CREDITS + 60


def test_webhook_for_disabled_provider_is_404(client):
    pid = _checkout(client)["payment_id"]
    body, headers = _signed_test_event(pid)
    assert client.post("/api/payments/webhook/safepay", content=body, headers=headers).status_code == 404


def test_test_checkout_page_pay_and_cancel_use_verified_path(client):
    paid = _checkout(client)["payment_id"]
    page = client.get(f"/pay/test/{paid}")
    assert page.status_code == 200 and "Nothing renews" in page.text
    resp = client.post(f"/pay/test/{paid}", data={"action": "pay"}, follow_redirects=False)
    assert resp.status_code == 303 and resp.headers["location"] == f"/pay/return?payment={paid}"
    assert payments.get_payment(paid)["status"] == "paid"

    cancelled = _checkout(client, "small")["payment_id"]
    resp = client.post(f"/pay/test/{cancelled}", data={"action": "cancel"}, follow_redirects=False)
    assert "result=cancelled" in resp.headers["location"]
    assert payments.get_payment(cancelled)["status"] == "failed"
    assert credits.balance(CLIENT) == credits.STARTER_CREDITS + 60


def test_return_route_sends_renter_back_to_app(client):
    resp = client.get("/pay/return?payment=pay_abc123&result=cancelled", follow_redirects=False)
    assert resp.status_code == 303 and resp.headers["location"] == "/?payment=pay_abc123&result=cancelled"
    resp = client.get("/pay/return?payment=javascript:alert(1)", follow_redirects=False)
    assert resp.headers["location"] == "/"


def test_payment_status_is_owner_only(client):
    pid = _checkout(client)["payment_id"]
    assert client.get(f"/api/payments/{pid}", headers=H(OTHER)).status_code == 404
    assert client.get(f"/api/payments/{pid}").status_code == 400
    assert client.get(f"/api/payments/{pid}", headers=H()).json()["status"] == "pending"


def test_stale_pending_payment_expires(client):
    pid = _checkout(client)["payment_id"]
    conn = payments._get_conn()
    with conn:
        conn.execute("UPDATE payments SET created_at = datetime('now', '-2 hours') WHERE id = ?", (pid,))
    assert client.get(f"/api/payments/{pid}", headers=H()).json()["status"] == "expired"


# ── Test mode safety ───────────────────────────────────────────────────────


@pytest.mark.parametrize("env", ["production", "", "staging", "PRODUCTION"])
def test_test_provider_refuses_outside_non_production_envs(client, monkeypatch, env):
    pid = _checkout(client)["payment_id"]
    body, headers = _signed_test_event(pid)
    if env:
        monkeypatch.setenv("ZR_ENV", env)
    else:
        monkeypatch.delenv("ZR_ENV")
    with pytest.raises(payments.PaymentsUnavailable):
        payments.get_provider()
    assert client.post("/api/credits/checkout", headers=H(), json={"pack_id": "small"}).status_code == 503
    assert client.get(f"/pay/test/{pid}").status_code == 404
    assert client.post(f"/pay/test/{pid}", data={"action": "pay"}).status_code == 404
    assert client.post("/api/payments/webhook/test", content=body, headers=headers).status_code == 404
    assert credits.balance(CLIENT) == credits.STARTER_CREDITS


def test_safepay_sandbox_refused_in_production(monkeypatch):
    monkeypatch.setenv("ZR_ENV", "production")
    with pytest.raises(payments.PaymentsUnavailable):
        payments.SafepayProvider(env="sandbox", api_key="sec_x", secret_key="s", webhook_secret="w")
    payments.SafepayProvider(env="production", api_key="sec_x", secret_key="s", webhook_secret="w")


def test_safepay_needs_all_secrets(monkeypatch):
    monkeypatch.setenv("PAYMENTS_PROVIDER", "safepay")
    monkeypatch.setenv("SAFEPAY_API_KEY", "sec_x")
    with pytest.raises(payments.PaymentsUnavailable):
        payments.get_provider()


# ── Restore codes ──────────────────────────────────────────────────────────


def _buy(client, pack_id="standard", client_id=CLIENT):
    pid = _checkout(client, pack_id, client_id)["payment_id"]
    client.post(f"/pay/test/{pid}", data={"action": "pay"}, follow_redirects=False)
    return client.get(f"/api/payments/{pid}", headers=H(client_id)).json()


def test_restore_code_shown_once_and_only_hash_stored(client):
    status = _buy(client)
    code = status["restore_code"]
    assert len(code.replace("-", "")) == payments.CODE_LENGTH
    again = client.get(f"/api/payments/{status['payment_id']}", headers=H()).json()
    assert "restore_code" not in again and again["has_restore_code"] is True
    rows = payments._get_conn().execute("SELECT * FROM restore_codes").fetchall()
    stored = " ".join(str(v) for r in rows for v in dict(r).values())
    assert code.replace("-", "") not in stored and code not in stored


def test_restore_moves_purchased_credits_and_is_idempotent(client):
    code = _buy(client)["restore_code"]
    spend_ref = credits.new_spend_ref("search_report")
    credits.spend(CLIENT, "search_report", ref=spend_ref)  # 70 -> 65

    resp = client.post("/api/credits/restore", headers=H(OTHER), json={"code": code.lower().replace("-", " ")})
    assert resp.status_code == 200
    assert resp.json()["moved"] == 60
    assert credits.balance(OTHER) == credits.STARTER_CREDITS + 60
    assert credits.balance(CLIENT) == 5  # what's left of the starter credits stays

    replay = client.post("/api/credits/restore", headers=H(OTHER), json={"code": code}).json()
    assert replay == {"moved": 0, "same_device": True, "balance": credits.STARTER_CREDITS + 60}
    kinds = [h["kind"] for h in credits.history(OTHER)]
    assert kinds.count("restore_in") == 1
    assert [h["kind"] for h in credits.history(CLIENT)].count("restore_out") == 1


def test_restore_code_follows_credits_and_cannot_pool_starter_credits(client):
    code = _buy(client)["restore_code"]
    client.post("/api/credits/restore", headers=H(OTHER), json={"code": code})
    client.post("/api/credits/restore", headers=H(THIRD), json={"code": code})
    assert credits.balance(THIRD) == credits.STARTER_CREDITS + 60
    assert credits.balance(OTHER) == credits.STARTER_CREDITS
    assert client.post("/api/credits/restore", headers=H(CLIENT), json={"code": code}).json()["moved"] == 60
    assert credits.balance(CLIENT) == credits.STARTER_CREDITS + 60


def test_restore_rejects_bad_codes(client):
    _buy(client)
    assert client.post("/api/credits/restore", headers=H(OTHER), json={"code": "AAAA-BBBB-CCCC-DDDD"}).status_code == 404
    assert client.post("/api/credits/restore", headers=H(OTHER), json={"code": "short"}).status_code == 404
    assert client.post("/api/credits/restore", headers=H(OTHER), json={"code": 123}).status_code == 404
    assert credits.balance(OTHER) == credits.STARTER_CREDITS


def test_restore_is_rate_limited(client):
    codes = [client.post("/api/credits/restore", headers=H(OTHER), json={"code": "AAAA-BBBB-CCCC-DDDD"}).status_code
             for _ in range(7)]
    assert 429 in codes


def test_new_restore_code_replaces_the_old_one(client):
    old = _buy(client)["restore_code"]
    new = client.post("/api/credits/restore-code", headers=H()).json()["restore_code"]
    assert new != old
    assert client.post("/api/credits/restore", headers=H(OTHER), json={"code": old}).status_code == 404
    assert client.post("/api/credits/restore", headers=H(OTHER), json={"code": new}).json()["moved"] == 60
    assert client.post("/api/credits/restore-code", headers=H(THIRD)).status_code == 404


# ── 402 contract for paid routes ───────────────────────────────────────────


def test_paid_route_pattern_returns_402_detail_the_frontend_expects(client):
    router = APIRouter()

    @router.post("/api/_test_paid_action")
    async def paid_action(request: Request):
        client_id = request.headers["X-Client-Id"]
        ref = credits.new_spend_ref("tailored_list")
        try:
            credits.spend(client_id, "tailored_list", ref=ref)
        except credits.InsufficientCredits as exc:
            raise HTTPException(status_code=402, detail=exc.as_detail())
        return {"ok": True}

    app.include_router(router)
    try:
        assert client.post("/api/_test_paid_action", headers=H()).status_code == 200
        assert client.post("/api/_test_paid_action", headers=H()).status_code == 200
        resp = client.post("/api/_test_paid_action", headers=H())
        assert resp.status_code == 402
        assert resp.json()["detail"] == {"code": "insufficient_credits", "action": "tailored_list",
                                         "balance": 0, "cost": credits.COSTS["tailored_list"]}
        # Topping up clears the 402.
        _buy(client, "small")
        assert client.post("/api/_test_paid_action", headers=H()).status_code == 200
    finally:
        app.router.routes[:] = [r for r in app.router.routes if getattr(r, "path", "") != "/api/_test_paid_action"]


# ── Safepay adapter against the documented formats ──────────────────────────

# Shape from https://safepay-docs.netlify.app/developers/webhooks/webhook-types/
SAFEPAY_SUCCEEDED = {
    "token": "evt_64b3218e-f65c-45a9-96b0-fe4e293bb879",
    "version": "2.0.0",
    "merchant_api_key": "sec_edeade52-46aa-483b-b87d-009d3ce41554",
    "type": "payment.succeeded",
    "endpoint": "http://example.com",
    "data": {
        "tracker": "track_06ee38cb-981d-4158-819f-7231f28314e4",
        "intent": "CYBERSOURCE", "state": "TRACKER_ENDED",
        "net": 48425, "fee": 1475, "customer_email": "hzee@gmail.com",
        "amount": 49900, "currency": "PKR",
        "metadata": {"order_id": "pay_placeholder", "source": "shopify"},
        "charged_at": {"seconds": 1698754230, "nanos": 752997627},
    },
    "created_at": {"seconds": 1698754230, "nanos": 912705711},
}


def _safepay(monkeypatch, http=None):
    monkeypatch.setenv("PAYMENTS_PROVIDER", "safepay")
    monkeypatch.setenv("SAFEPAY_ENV", "sandbox")
    monkeypatch.setenv("SAFEPAY_API_KEY", "sec_test_key")
    monkeypatch.setenv("SAFEPAY_SECRET_KEY", "merchant-secret")
    monkeypatch.setenv("SAFEPAY_WEBHOOK_SECRET", SAFEPAY_WEBHOOK_SECRET)
    calls = []

    def fake_http(method, url, headers, body):
        calls.append((method, url, headers, body))
        if url.endswith("/order/payments/v3/"):
            return {"data": {"tracker": {"token": "track_06ee38cb-981d-4158-819f-7231f28314e4",
                                         "state": "TRACKER_STARTED"}}}
        if url.endswith("/client/passport/v1/token"):
            return {"data": "tbt-token=="}
        return (http or (lambda *a: {}))(method, url, headers, body)

    monkeypatch.setattr(payments, "_default_http", fake_http)
    return calls


def _sfpy_sign(payload_bytes: bytes) -> str:
    # HMAC-SHA512 hex over the JSON payload, as in sfpy-php WebhookSignature.
    return hmac.new(SAFEPAY_WEBHOOK_SECRET.encode(), payload_bytes, hashlib.sha512).hexdigest()


def test_safepay_checkout_follows_documented_flow(client, monkeypatch):
    calls = _safepay(monkeypatch)
    out = _checkout(client, "standard")
    setup = calls[0]
    assert setup[0] == "POST" and setup[1] == "https://sandbox.api.getsafepay.com/order/payments/v3/"
    assert setup[2]["X-SFPY-MERCHANT-SECRET"] == "merchant-secret"
    assert setup[3]["amount"] == 49900 and setup[3]["currency"] == "PKR"
    assert setup[3]["metadata"] == {"order_id": out["payment_id"]}
    assert calls[1][1] == "https://sandbox.api.getsafepay.com/client/passport/v1/token"
    url = out["checkout_url"]
    assert url.startswith("https://sandbox.api.getsafepay.com/embedded/?environment=sandbox&tracker=track_")
    assert "tbt=tbt-token%3D%3D" in url and "redirect_url=" in url and "cancel_url=" in url
    assert payments.get_payment(out["payment_id"])["provider_ref"] == "track_06ee38cb-981d-4158-819f-7231f28314e4"


@pytest.mark.parametrize("encoding", ["raw-pretty", "compact", "compact-ascii"])
def test_safepay_webhook_signature_verifies_and_grants(client, monkeypatch, encoding):
    _safepay(monkeypatch)
    pid = _checkout(client, "standard")["payment_id"]
    event = json.loads(json.dumps(SAFEPAY_SUCCEEDED))
    event["data"]["metadata"]["order_id"] = pid
    event["data"]["customer_email"] = "zainab@exämple.pk"
    raw = json.dumps(event, indent=2, ensure_ascii=False).encode()
    signed = {
        "raw-pretty": raw,
        "compact": json.dumps(event, separators=(",", ":"), ensure_ascii=False).encode(),
        "compact-ascii": json.dumps(event, separators=(",", ":")).encode(),
    }[encoding]
    resp = client.post("/api/payments/webhook/safepay", content=raw,
                       headers={"X-SFPY-SIGNATURE": _sfpy_sign(signed), "Content-Type": "application/json"})
    assert resp.status_code == 200
    assert payments.get_payment(pid)["status"] == "paid"
    assert credits.balance(CLIENT) == credits.STARTER_CREDITS + 60


def test_safepay_webhook_rejects_wrong_secret_and_tampering(client, monkeypatch):
    _safepay(monkeypatch)
    pid = _checkout(client, "standard")["payment_id"]
    event = json.loads(json.dumps(SAFEPAY_SUCCEEDED))
    event["data"]["metadata"]["order_id"] = pid
    raw = json.dumps(event).encode()
    wrong = hmac.new(b"not-the-secret", raw, hashlib.sha512).hexdigest()
    assert client.post("/api/payments/webhook/safepay", content=raw,
                       headers={"X-SFPY-SIGNATURE": wrong}).status_code == 400
    event["data"]["amount"] = 4990000
    tampered = json.dumps(event).encode()
    assert client.post("/api/payments/webhook/safepay", content=tampered,
                       headers={"X-SFPY-SIGNATURE": _sfpy_sign(raw)}).status_code == 400
    assert client.post("/api/payments/webhook/safepay", content=raw).status_code == 400
    assert credits.balance(CLIENT) == credits.STARTER_CREDITS


def test_safepay_webhook_amount_mismatch_does_not_grant(client, monkeypatch):
    _safepay(monkeypatch)
    pid = _checkout(client, "standard")["payment_id"]
    event = json.loads(json.dumps(SAFEPAY_SUCCEEDED))
    event["data"]["metadata"]["order_id"] = pid
    event["data"]["amount"] = 499  # rupees instead of paisa
    raw = json.dumps(event).encode()
    assert client.post("/api/payments/webhook/safepay", content=raw,
                       headers={"X-SFPY-SIGNATURE": _sfpy_sign(raw)}).status_code == 200
    assert credits.balance(CLIENT) == credits.STARTER_CREDITS


@pytest.mark.parametrize("nested", [True, False])
def test_safepay_status_lookup_confirms_on_return(client, monkeypatch, nested):
    tracker = "track_06ee38cb-981d-4158-819f-7231f28314e4"
    info = {"token": tracker, "state": "TRACKER_ENDED",
            "purchase_totals": {"quote_amount": {"currency": "PKR", "amount": 49900}}}

    def reporter(method, url, headers, body):
        assert method == "GET" and url.endswith(f"/reporter/api/v1/payments/{tracker}")
        assert headers["X-SFPY-MERCHANT-SECRET"] == "merchant-secret"
        return {"data": {"tracker": info}} if nested else {"ok": True, "data": info}

    _safepay(monkeypatch, reporter)
    pid = _checkout(client, "standard")["payment_id"]
    status = client.get(f"/api/payments/{pid}", headers=H()).json()
    assert status["status"] == "paid" and status["balance"] == credits.STARTER_CREDITS + 60
    assert status["restore_code"]


def test_safepay_lookup_with_wrong_amount_stays_pending(client, monkeypatch):
    def reporter(method, url, headers, body):
        return {"data": {"state": "TRACKER_ENDED",
                         "purchase_totals": {"quote_amount": {"currency": "PKR", "amount": 100}}}}
    _safepay(monkeypatch, reporter)
    pid = _checkout(client, "standard")["payment_id"]
    assert client.get(f"/api/payments/{pid}", headers=H()).json()["status"] == "pending"
    assert credits.balance(CLIENT) == credits.STARTER_CREDITS


def test_get_credits_reports_checkout_and_restore_state(client):
    data = client.get("/api/credits", headers=H()).json()
    assert data["checkout_available"] is True and data["has_restore_code"] is False
    assert {p["id"] for p in data["packs"]} == set(credits.PACKS)
