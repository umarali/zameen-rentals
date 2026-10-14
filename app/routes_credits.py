"""Credits API: balance, checkout, payment confirmation, restore codes.

Every route that changes money state is rate-limited per IP. Amounts and
credit counts come from `credits.PACKS` on the server; the browser only
names a pack. Credits are granted only by `payments.apply_confirmation`
after a verified webhook or a server-to-server status lookup.
"""
import html
import logging
import os
from urllib.parse import parse_qs, urlencode

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, RedirectResponse

from app import credits, payments
from app.cache import limiter
from app.routes import _require_credit_client_id as _require_client_id, _PERSONALIZATION_STEADY, _PLAYWRIGHT_SERVER

logger = logging.getLogger("zameenrentals")


def _startup():
    payments.init_payments_schema()


router = APIRouter(on_startup=[_startup])

_CHECKOUT_LIMIT = "60/minute" if _PLAYWRIGHT_SERVER else "10/minute"
_STATUS_LIMIT = "600/minute" if _PLAYWRIGHT_SERVER else "60/minute"
_WEBHOOK_LIMIT = "600/minute" if _PLAYWRIGHT_SERVER else "120/minute"
# Restore codes carry 80 bits of entropy, so guessing is hopeless even
# without limits; these keep it that way and keep the logs quiet.
_RESTORE_LIMIT = "60/minute" if _PLAYWRIGHT_SERVER else "5/minute;30/hour"
_CODE_ROTATE_LIMIT = "60/minute" if _PLAYWRIGHT_SERVER else "5/minute"


def _error(exc: payments.PaymentsError):
    return HTTPException(status_code=exc.status, detail=str(exc))


async def _json_body(request: Request) -> dict:
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Send a JSON body")
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Send a JSON object")
    return body


def _public_base(request: Request) -> str:
    """Absolute origin for provider return URLs. PUBLIC_BASE_URL wins in production."""
    base = (os.getenv("PUBLIC_BASE_URL") or "").strip().rstrip("/")
    return base or str(request.base_url).rstrip("/")


@router.get("/api/credits")
@limiter.limit(_PERSONALIZATION_STEADY)
async def get_credits(request: Request):
    client_id = _require_client_id(request)
    return {
        **credits.summary(client_id),
        "checkout_available": payments.checkout_available(),
        "has_restore_code": payments.has_restore_code(client_id),
        "can_issue_restore_code": payments.has_restore_code(client_id) or payments.has_purchases(client_id),
    }


@router.post("/api/credits/checkout")
@limiter.limit(_CHECKOUT_LIMIT)
async def credits_checkout(request: Request):
    client_id = _require_client_id(request)
    body = await _json_body(request)
    pack_id = body.get("pack_id")
    if not isinstance(pack_id, str) or pack_id not in credits.PACKS:
        raise HTTPException(status_code=400, detail="Unknown pack")
    try:
        provider = payments.get_provider()
        payment = payments.create_payment(client_id, pack_id, provider)
    except payments.PaymentsError as exc:
        raise _error(exc)
    base = _public_base(request)
    return_url = f"{base}/pay/return?{urlencode({'payment': payment['id']})}"
    cancel_url = f"{base}/pay/return?{urlencode({'payment': payment['id'], 'result': 'cancelled'})}"
    try:
        checkout = await run_in_threadpool(
            provider.create_checkout, payment, return_url=return_url, cancel_url=cancel_url
        )
    except Exception:
        logger.exception("checkout creation failed id=%s provider=%s", payment["id"], provider.name)
        payments.mark_failed_to_start(payment["id"])
        raise HTTPException(status_code=502, detail="Could not start checkout. Try again in a minute.")
    payments.attach_provider_ref(payment["id"], checkout.provider_ref)
    return {"payment_id": payment["id"], "checkout_url": checkout.redirect_url}


@router.post("/api/payments/webhook/{provider_name}")
@limiter.limit(_WEBHOOK_LIMIT)
async def payments_webhook(request: Request, provider_name: str):
    raw = await request.body()
    try:
        # Verification is CPU-only; keep the database work on this thread.
        payments.handle_webhook(provider_name, dict(request.headers), raw)
    except payments.PaymentsUnavailable:
        raise HTTPException(status_code=404, detail="Not found")
    except payments.InvalidSignature:
        raise HTTPException(status_code=400, detail="Invalid signature")
    # A verified event is acknowledged even when it changes nothing (unknown
    # payment, amount mismatch, replay), so the provider stops retrying.
    return {"received": True}


@router.get("/api/payments/{payment_id}")
@limiter.limit(_STATUS_LIMIT)
async def payment_status(request: Request, payment_id: str, response: Response):
    response.headers["Cache-Control"] = "no-store"
    client_id = _require_client_id(request)
    payment = payments.get_payment(payment_id)
    if not payment or payment["client_id"] != client_id:
        raise HTTPException(status_code=404, detail="Payment not found")
    payment = await payments.refresh_payment(payment)
    result = {**payments.public_payment(payment), "balance": credits.balance(client_id)}
    if payment["status"] == "paid" and not payments.has_restore_code(client_id):
        # Shown once. Only its hash is stored.
        result["restore_code"] = payments.issue_restore_code(client_id)
    result["has_restore_code"] = payments.has_restore_code(client_id)
    return result


@router.post("/api/credits/restore")
@limiter.limit(_RESTORE_LIMIT)
async def credits_restore(request: Request):
    client_id = _require_client_id(request)
    body = await _json_body(request)
    try:
        return payments.restore(body.get("code"), client_id)
    except payments.RestoreFailed as exc:
        raise _error(exc)


@router.post("/api/credits/restore-code")
@limiter.limit(_CODE_ROTATE_LIMIT)
async def credits_new_restore_code(request: Request, response: Response):
    """Replace this device's restore code. The old code stops working."""
    response.headers["Cache-Control"] = "no-store"
    client_id = _require_client_id(request)
    if not (payments.has_restore_code(client_id) or payments.has_purchases(client_id)):
        raise HTTPException(status_code=404, detail="Restore codes come with your first purchase")
    return {"restore_code": payments.issue_restore_code(client_id, replace=True)}


# ── Browser pages: provider return and the local test checkout ──────────────


@router.get("/pay/return")
@limiter.limit(_STATUS_LIMIT)
async def payment_return(request: Request):
    """Where providers send the renter back. The app then shows the verified result."""
    payment_id = request.query_params.get("payment", "")
    if not payment_id.startswith("pay_") or len(payment_id) > 64 or not payment_id[4:].isalnum():
        return RedirectResponse("/", status_code=303)
    params = {"payment": payment_id}
    if request.query_params.get("result") == "cancelled":
        params["result"] = "cancelled"
    return RedirectResponse(f"/?{urlencode(params)}", status_code=303)


def _test_provider_or_404() -> payments.TestProvider:
    try:
        return payments.get_provider("test")
    except payments.PaymentsUnavailable:
        raise HTTPException(status_code=404, detail="Not found")


_TEST_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>Test checkout</title>
<style>
  :root {{ color-scheme: light; font-family: system-ui, -apple-system, Segoe UI, sans-serif; }}
  body {{ margin: 0; background: #f3f4f6; color: #1f2937; }}
  main {{ max-width: 420px; margin: 0 auto; padding: 32px 16px; }}
  .card {{ background: #fff; border-radius: 16px; padding: 24px; box-shadow: 0 1px 3px rgba(0,0,0,.08); }}
  .tag {{ display: inline-block; font-size: 12px; font-weight: 600; background: #fef3c7; color: #92400e; padding: 2px 8px; border-radius: 999px; }}
  h1 {{ font-size: 20px; margin: 12px 0 4px; }}
  p {{ font-size: 14px; line-height: 1.5; color: #4b5563; }}
  .amount {{ font-size: 28px; font-weight: 700; color: #111827; margin: 16px 0 4px; }}
  form {{ display: flex; gap: 8px; margin-top: 20px; }}
  button {{ flex: 1; font: inherit; font-weight: 600; padding: 12px; border-radius: 10px; border: 1px solid #d1d5db; background: #fff; color: #1f2937; cursor: pointer; }}
  button[value=pay] {{ background: #047857; border-color: #047857; color: #fff; }}
  button:focus-visible {{ outline: 3px solid #93c5fd; outline-offset: 2px; }}
</style></head>
<body><main><div class="card">
  <span class="tag">Test mode: no real money</span>
  <h1>Test checkout</h1>
  <p>{credits} credits, paid once. Nothing renews.</p>
  <div class="amount">PKR {amount}</div>
  {state}
</div></main></body></html>"""


@router.get("/pay/test/{payment_id}", response_class=HTMLResponse)
@limiter.limit(_STATUS_LIMIT)
async def test_checkout_page(request: Request, payment_id: str):
    _test_provider_or_404()
    payment = payments.get_payment(payment_id)
    if not payment or payment["provider"] != "test":
        raise HTTPException(status_code=404, detail="Not found")
    if payment["status"] == "pending":
        state = (
            f'<form method="post" action="/pay/test/{html.escape(payment_id)}">'
            '<button type="submit" name="action" value="cancel">Cancel</button>'
            '<button type="submit" name="action" value="pay">Pay</button></form>'
        )
    else:
        state = f"<p>This payment is {html.escape(payment['status'])}.</p>"
    return HTMLResponse(_TEST_PAGE.format(
        credits=payment["credits"], amount=f"{payment['amount_pkr']:,}", state=state,
    ), headers={"Cache-Control": "no-store"})


@router.post("/pay/test/{payment_id}")
@limiter.limit(_CHECKOUT_LIMIT)
async def test_checkout_submit(request: Request, payment_id: str):
    """Pay or Cancel on the test page. Builds a signed confirmation and sends it
    through the same verification path as a provider webhook."""
    provider = _test_provider_or_404()
    payment = payments.get_payment(payment_id)
    if not payment or payment["provider"] != "test":
        raise HTTPException(status_code=404, detail="Not found")
    form = parse_qs((await request.body()).decode("utf-8", "replace"))
    paying = form.get("action", [""])[0] == "pay"
    headers, raw = provider.build_event(payment, "paid" if paying else "cancelled")
    payments.handle_webhook("test", headers, raw)
    params = {"payment": payment_id}
    if not paying:
        params["result"] = "cancelled"
    return RedirectResponse(f"/pay/return?{urlencode(params)}", status_code=303)
