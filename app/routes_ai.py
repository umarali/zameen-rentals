"""Paid AI actions: tailored list and search report.

Pattern for both (docs/credits-contract.md): validate and do the free work
first, so nothing is charged when there's nothing to rank or report on; then
spend, do the paid work, and refund on any failure.

Retries never double-charge:
- The client may send an ``Idempotency-Key`` header. The spend ref is derived
  from it, so replaying the request reuses the same charge. After a refund the
  next attempt gets a fresh ref, so a refunded attempt can't be replayed free.
- Results are cached for ``RESULT_TTL_SECONDS`` under the request (same
  client, same brief / same activity) and under the idempotency key. A cached
  hit is returned without charging again.
"""
import asyncio
import hashlib
import json
import logging
import os
import re
import time

from fastapi import APIRouter, HTTPException, Request

from app import credits, ranking, report, tailored
from app.cache import limiter
from app.database import _get_conn
from app.routes import _require_client_id, _PERSONALIZATION_STEADY

logger = logging.getLogger("zameenrentals")
router = APIRouter()

_PLAYWRIGHT_SERVER = os.getenv("ZAMEENRENTALS_PLAYWRIGHT") == "1"
_AI_RATE_LIMIT = "10000/minute" if _PLAYWRIGHT_SERVER else "6/minute"
RESULT_TTL_SECONDS = float(os.environ.get("ZR_AI_RESULT_TTL_SECONDS", "900"))
WORK_TIMEOUT_SECONDS = float(os.environ.get("ZR_AI_WORK_TIMEOUT_SECONDS", "60"))
_IDEMPOTENCY_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")

_locks: dict[str, asyncio.Lock] = {}


# ── Result cache ─────────────────────────────────────────────────────────────

def _db():
    conn = _get_conn()
    conn.execute("""CREATE TABLE IF NOT EXISTS ai_results (
        cache_key TEXT PRIMARY KEY, client_id TEXT NOT NULL, action TEXT NOT NULL,
        result_json TEXT NOT NULL, created_at REAL NOT NULL)""")
    return conn


def _key(*parts) -> str:
    return hashlib.sha256("\x1f".join(str(p) for p in parts).encode()).hexdigest()


def _cache_get(keys):
    conn = _db()
    for k in keys:
        row = conn.execute("SELECT result_json, created_at FROM ai_results WHERE cache_key = ?", (k,)).fetchone()
        if row and time.time() - row["created_at"] < RESULT_TTL_SECONDS:
            return json.loads(row["result_json"])
    return None


def _cache_set(keys, client_id, action, result):
    conn = _db()
    now = time.time()
    with conn:
        conn.execute("DELETE FROM ai_results WHERE created_at < ?", (now - RESULT_TTL_SECONDS,))
        for k in keys:
            conn.execute("INSERT OR REPLACE INTO ai_results VALUES (?, ?, ?, ?, ?)",
                         (k, client_id, action, json.dumps(result), now))


# ── Charging ─────────────────────────────────────────────────────────────────

def _idempotency_key(request: Request, body: dict) -> str | None:
    key = (request.headers.get("Idempotency-Key") or body.get("idempotency_key") or "").strip()
    if not key:
        return None
    if not _IDEMPOTENCY_RE.match(key):
        raise HTTPException(status_code=400, detail="Invalid idempotency key")
    return key


def _spend_ref(client_id: str, action: str, idem: str | None) -> str:
    """A ref that is stable across retries but never reuses a refunded spend."""
    if not idem:
        return credits.new_spend_ref(action)
    base = f"spend:{action}:{_key(client_id, idem)[:32]}"
    conn = _get_conn()
    for n in range(50):
        ref = base if n == 0 else f"{base}:{n}"
        if not conn.execute("SELECT 1 FROM credit_ledger WHERE ref = ?", (f"refund:{ref}",)).fetchone():
            return ref
    return credits.new_spend_ref(action)


async def _run_paid(*, client_id, action, request_key, idem, work, empty=lambda r: False):
    """Spend, run `work` (sync, in a thread), refund on failure. Returns the response body."""
    keys = [request_key] + ([_key(client_id, action, "idem", idem)] if idem else [])
    lock = _locks.setdefault(keys[-1], asyncio.Lock())
    try:
        async with lock:
            cached = _cache_get(keys)
            if cached is not None:
                return {**cached, "cached": True, "charged": False, "balance": credits.balance(client_id)}
            ref = _spend_ref(client_id, action, idem)
            try:
                balance = credits.spend(client_id, action, ref=ref)
            except credits.InsufficientCredits as exc:
                raise HTTPException(status_code=402, detail=exc.as_detail())
            try:
                result = await asyncio.wait_for(asyncio.to_thread(work), WORK_TIMEOUT_SECONDS)
            except Exception as exc:
                credits.refund(ref)
                if isinstance(exc, ranking.RankingError):
                    public = exc.public
                elif isinstance(exc, asyncio.TimeoutError):
                    public = "That took too long."
                else:
                    public = "Something went wrong."
                if not isinstance(exc, (ranking.RankingError, asyncio.TimeoutError)):
                    logger.exception("Paid action %s failed", action)
                raise HTTPException(status_code=503, detail=f"{public} Your credits were not used.")
            if empty(result):
                credits.refund(ref)
                return {**result, "cached": False, "charged": False, "balance": credits.balance(client_id),
                        "cost": credits.COSTS[action]}
            _cache_set(keys, client_id, action, result)
            return {**result, "cached": False, "charged": True, "balance": balance,
                    "cost": credits.COSTS[action]}
    finally:
        if not lock.locked():
            _locks.pop(keys[-1], None)


async def _json_body(request: Request) -> dict:
    try:
        body = await request.json()
    except Exception:
        body = None
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Body must be a JSON object")
    return body


# ── Tailored list ────────────────────────────────────────────────────────────

@router.post("/api/ai/tailored")
@limiter.limit(_AI_RATE_LIMIT)
async def tailored_list(request: Request):
    client_id = _require_client_id(request)
    body = await _json_body(request)
    try:
        brief, city = tailored.validate_brief(body.get("brief"), body.get("city") or "lahore")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    idem = _idempotency_key(request, body)
    request_key = _key(client_id, "tailored_list", city, brief.lower())

    cached = _cache_get([request_key] + ([_key(client_id, "tailored_list", "idem", idem)] if idem else []))
    if cached is not None:
        return {**cached, "cached": True, "charged": False, "balance": credits.balance(client_id)}

    prepared = await tailored.prepare(brief, city, client_id)
    if not prepared.candidates:
        return {"results": [], "charged": False, "cached": False, "balance": credits.balance(client_id),
                "cost": credits.COSTS["tailored_list"],
                "understood": {"city": prepared.city, "filters": prepared.filters, "preferences": []},
                "relaxed": prepared.relaxed, "candidates_considered": 0, "source": "Zameen.com",
                "message": "No listings match the area and budget in your description yet. "
                           "You weren't charged. Try a wider area or budget."}

    result = await _run_paid(
        client_id=client_id, action="tailored_list", request_key=request_key, idem=idem,
        work=lambda: tailored.rank(prepared), empty=lambda r: not r["results"])
    if not result.get("charged") and not result.get("cached") and not result["results"]:
        result["message"] = ("None of the listings we found fit your description well. "
                             "You weren't charged. Try loosening one requirement.")
    return result


# ── Search report ────────────────────────────────────────────────────────────

@router.get("/api/ai/report/eligibility")
@limiter.limit(_PERSONALIZATION_STEADY)
async def report_eligibility(request: Request):
    """Free check before charging: is there enough of this client's activity?"""
    client_id = _require_client_id(request)
    act = report.activity(client_id)
    ok, reason = report.eligibility(act)
    return {"eligible": ok, "reason": reason, "activity": act["counts"],
            "cost": credits.COSTS["search_report"], "balance": credits.balance(client_id)}


@router.post("/api/ai/report")
@limiter.limit(_AI_RATE_LIMIT)
async def search_report(request: Request):
    client_id = _require_client_id(request)
    body = await _json_body(request)
    idem = _idempotency_key(request, body)
    try:
        prepared = report.prepare(client_id)
    except report.NotEnoughActivity as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    request_key = _key(client_id, "search_report", prepared["fingerprint"])
    return await _run_paid(
        client_id=client_id, action="search_report", request_key=request_key, idem=idem,
        work=lambda: report.generate(prepared))
