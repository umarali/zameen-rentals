"""Paid upgrades on a saved search (alert), paid with credits per day while on.

Two upgrades, keyed by their action name in ``app.credits.COSTS``:

``instant_alerts_day`` (shown to renters as "Priority check")
    Free alerts already match a listing the moment the crawler stores it and
    push right after each newest-listings refresh. What free alerts can miss
    is a listing that never reaches the city-wide newest feed: that feed reads
    the newest 3 pages (75 listings) per city per refresh, so a burst of new
    or bumped listings pushes older ones out and they wait for the 12-hour
    area sweep. With this upgrade the crawler also reads the first newest-first
    page of the alert's own Zameen search on every refresh tick, after the
    free alerts for that tick have been sent. It never delays free alerts.

``daily_shortlist_day``
    Once a day (from SHORTLIST_HOUR, Asia/Karachi), up to SHORTLIST_SIZE of
    the alert's matches from the last 24 hours, ranked with a short reason
    each. Ranking uses ``app.ranking.rank_listings`` when it is available and
    a deterministic fallback otherwise. Days with no new matches cost nothing.

Charging
    One charge per alert, per upgrade, per Asia/Karachi calendar day, with
    the ledger ref ``alertday:{alert_id}:{upgrade}:{YYYY-MM-DD}``. The ledger's
    unique ref makes every charge idempotent, so repeated cycles never charge
    twice. Priority check is currently unavailable. Daily shortlists charge on delivery.
    The crawler calls ``run_daily_jobs`` after each alert flush. Shortlists
    charge only when there are new matches since the previous delivery window.
    Legacy prepaid empty days are refunded. When a charge fails for lack of
    credits the upgrade is switched off and the renter gets an in-app notice.
    The balance can never go negative (``credits.spend`` checks atomically).
    Paused alerts are not charged and get neither upgrade until resumed.
"""
from __future__ import annotations

import inspect
import json
import logging
import os
import random
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from datetime import datetime, timedelta, timezone

from app import credits
from app.database import _get_conn

logger = logging.getLogger("zameenrentals")

INSTANT = "instant_alerts_day"
SHORTLIST = "daily_shortlist_day"
UPGRADES = (INSTANT, SHORTLIST)
# Priority check is withheld until its benefit over free alerts is measured.
PRIORITY_AVAILABLE = False


def offered_upgrades():
    return UPGRADES if PRIORITY_AVAILABLE else (SHORTLIST,)

SHORTLIST_HOUR = 9              # Local (Asia/Karachi) hour the shortlist becomes due
SHORTLIST_SIZE = 5
SHORTLIST_WINDOW_HOURS = 24
SHORTLIST_CANDIDATES = 100      # Most recent matches considered for ranking
MAX_SHORTLISTS_PER_RUN = 10     # Keep one crawler flush short; the rest wait for the next
MAX_PRIORITY_SEARCHES_PER_TICK = 20

try:
    from zoneinfo import ZoneInfo
    KARACHI_TZ = ZoneInfo("Asia/Karachi")
except Exception:  # pragma: no cover - tzdata missing; Pakistan has no DST
    KARACHI_TZ = timezone(timedelta(hours=5), "PKT")


# ── Time helpers ─────────────────────────────────────────────────────────────


def _utc_now(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(timezone.utc)
    if now.tzinfo is None:
        return now.replace(tzinfo=timezone.utc)
    return now.astimezone(timezone.utc)


def karachi_now(now: datetime | None = None) -> datetime:
    return _utc_now(now).astimezone(KARACHI_TZ)


def karachi_day(now: datetime | None = None) -> str:
    """The Asia/Karachi calendar day as YYYY-MM-DD."""
    return karachi_now(now).strftime("%Y-%m-%d")


def _sqlite_utc(dt: datetime) -> str:
    """Format like SQLite's datetime('now') so string comparisons work."""
    return _utc_now(dt).strftime("%Y-%m-%d %H:%M:%S")


def day_ref(alert_id: int, upgrade: str, day: str) -> str:
    return f"alertday:{alert_id}:{upgrade}:{day}"


# ── Schema ───────────────────────────────────────────────────────────────────


def init_alert_upgrades_schema(conn=None):
    """Create upgrade tables. Idempotent; safe on every boot (web and crawler)."""
    credits.init_credits_schema(conn)
    conn = conn or _get_conn()
    with conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS alert_upgrades (
                alert_id        INTEGER NOT NULL,
                upgrade         TEXT NOT NULL CHECK (upgrade IN ('instant_alerts_day', 'daily_shortlist_day')),
                client_id       TEXT NOT NULL,
                enabled         INTEGER NOT NULL DEFAULT 0,
                enabled_at      TEXT,
                disabled_at     TEXT,
                disabled_reason TEXT,
                settled_day     TEXT,
                last_checked_at TEXT,
                PRIMARY KEY (alert_id, upgrade)
            );
            CREATE INDEX IF NOT EXISTS idx_alert_upgrades_enabled
                ON alert_upgrades(enabled, upgrade);
            CREATE INDEX IF NOT EXISTS idx_alert_upgrades_client
                ON alert_upgrades(client_id);

            CREATE TABLE IF NOT EXISTS alert_shortlists (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                alert_id      INTEGER NOT NULL,
                client_id     TEXT NOT NULL,
                day           TEXT NOT NULL,
                status        TEXT NOT NULL CHECK (status IN ('delivered', 'empty', 'unpaid')),
                match_count   INTEGER NOT NULL DEFAULT 0,
                ranked_by     TEXT,
                items_json    TEXT,
                created_at    TEXT NOT NULL DEFAULT (datetime('now')),
                seen_at       TEXT,
                notified_push INTEGER NOT NULL DEFAULT 0,
                UNIQUE (alert_id, day)
            );
            CREATE INDEX IF NOT EXISTS idx_alert_shortlists_client
                ON alert_shortlists(client_id, created_at DESC);

            CREATE TABLE IF NOT EXISTS alert_upgrade_notices (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id  TEXT NOT NULL,
                alert_id   INTEGER NOT NULL,
                upgrade    TEXT NOT NULL,
                kind       TEXT NOT NULL,
                day        TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                seen_at    TEXT,
                UNIQUE (alert_id, upgrade, kind, day)
            );
            CREATE INDEX IF NOT EXISTS idx_alert_upgrade_notices_client
                ON alert_upgrade_notices(client_id, seen_at);
        """)
        for table in ("alert_upgrades", "alert_shortlists", "alert_upgrade_notices"):
            conn.execute(f"DELETE FROM {table} WHERE alert_id NOT IN (SELECT id FROM alerts)")


def delete_for_alert(conn, alert_id: int):
    """Remove upgrade state for a deleted alert. Ledger rows stay (they are history)."""
    for table in ("alert_upgrades", "alert_shortlists", "alert_upgrade_notices"):
        conn.execute(f"DELETE FROM {table} WHERE alert_id = ?", (alert_id,))


# ── Ledger helpers ───────────────────────────────────────────────────────────


def _ref_state(ref: str) -> str:
    """'paid', 'refunded' or 'none' for a day ref."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT 1 FROM credit_ledger WHERE ref = ? AND kind = 'spend'", (ref,)
    ).fetchone()
    if not row:
        return "none"
    refunded = conn.execute(
        "SELECT 1 FROM credit_ledger WHERE ref = ?", (f"refund:{ref}",)
    ).fetchone()
    return "refunded" if refunded else "paid"


# ── Reading state (API) ──────────────────────────────────────────────────────


def _alert_row(client_id: str, alert_id: int):
    return _get_conn().execute(
        "SELECT id, client_id, label, filters_json, paused, notify_push FROM alerts "
        "WHERE id = ? AND client_id = ?",
        (alert_id, client_id),
    ).fetchone()


def _upgrade_row(alert_id: int, upgrade: str):
    return _get_conn().execute(
        "SELECT * FROM alert_upgrades WHERE alert_id = ? AND upgrade = ?",
        (alert_id, upgrade),
    ).fetchone()


def _upgrade_view(alert_id: int, upgrade: str, row, day: str) -> dict:
    return {
        "enabled": bool(row and row["enabled"]),
        "cost_per_day": credits.COSTS[upgrade],
        "paid_today": _ref_state(day_ref(alert_id, upgrade, day)) == "paid",
        "disabled_reason": row["disabled_reason"] if row else None,
        "disabled_at": row["disabled_at"] if row else None,
    }


def daily_cost(client_id: str) -> int:
    rows = _get_conn().execute(
        """SELECT u.upgrade FROM alert_upgrades u JOIN alerts a ON a.id = u.alert_id
           WHERE u.client_id = ? AND u.enabled = 1 AND a.paused = 0""",
        (client_id,),
    ).fetchall()
    return sum(credits.COSTS[r["upgrade"]] for r in rows if r["upgrade"] in offered_upgrades())


def get_state(client_id: str, *, now: datetime | None = None) -> dict:
    """Everything the alert UI needs: balance, costs, per-alert upgrades, notices."""
    day = karachi_day(now)
    conn = _get_conn()
    balance = credits.balance(client_id)
    alerts = conn.execute(
        "SELECT id, paused FROM alerts WHERE client_id = ? ORDER BY id", (client_id,)
    ).fetchall()
    upgrades = {
        (r["alert_id"], r["upgrade"]): r
        for r in conn.execute("SELECT * FROM alert_upgrades WHERE client_id = ?", (client_id,))
    }
    latest = {
        r["alert_id"]: r
        for r in conn.execute(
            """SELECT s.alert_id, s.day, s.status, s.match_count, s.seen_at, s.items_json
               FROM alert_shortlists s
               WHERE s.client_id = ? AND s.status = 'delivered'
                 AND s.id = (SELECT MAX(id) FROM alert_shortlists t
                             WHERE t.alert_id = s.alert_id AND t.status = 'delivered')""",
            (client_id,),
        )
    }
    per_alert = {}
    for a in alerts:
        view = {u: _upgrade_view(a["id"], u, upgrades.get((a["id"], u)), day) for u in offered_upgrades()}
        sl = latest.get(a["id"])
        view["latest_shortlist"] = None if sl is None else {
            "day": sl["day"],
            "match_count": sl["match_count"],
            "count": len(json.loads(sl["items_json"] or "[]")),
            "seen": sl["seen_at"] is not None,
        }
        view["paused"] = bool(a["paused"])
        per_alert[str(a["id"])] = view
    cost = daily_cost(client_id)
    return {
        "balance": balance,
        "costs": {u: credits.COSTS[u] for u in offered_upgrades()},
        "shortlist_hour": SHORTLIST_HOUR,
        "shortlist_size": SHORTLIST_SIZE,
        "today": day,
        "daily_cost": cost,
        "days_covered": (balance // cost) if cost else None,
        "alerts": per_alert,
        "notices": list_notices(client_id),
    }


def list_notices(client_id: str) -> list[dict]:
    rows = _get_conn().execute(
        """SELECT n.id, n.alert_id, n.upgrade, n.kind, n.day, n.created_at, a.label AS alert_label
           FROM alert_upgrade_notices n LEFT JOIN alerts a ON a.id = n.alert_id
           WHERE n.client_id = ? AND n.seen_at IS NULL ORDER BY n.id DESC LIMIT 20""",
        (client_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def dismiss_notices(client_id: str, ids: list[int] | None = None) -> int:
    conn = _get_conn()
    with conn:
        if ids:
            marks = ",".join("?" * len(ids))
            cur = conn.execute(
                f"UPDATE alert_upgrade_notices SET seen_at = datetime('now') "
                f"WHERE client_id = ? AND seen_at IS NULL AND id IN ({marks})",
                [client_id, *[int(i) for i in ids]],
            )
        else:
            cur = conn.execute(
                "UPDATE alert_upgrade_notices SET seen_at = datetime('now') "
                "WHERE client_id = ? AND seen_at IS NULL",
                (client_id,),
            )
    return cur.rowcount


def list_shortlists(client_id: str, alert_id: int, *, limit: int = 7, mark_seen: bool = True) -> list[dict]:
    conn = _get_conn()
    rows = conn.execute(
        """SELECT id, day, status, match_count, ranked_by, items_json, created_at, seen_at
           FROM alert_shortlists WHERE client_id = ? AND alert_id = ? AND status = 'delivered'
           ORDER BY day DESC LIMIT ?""",
        (client_id, alert_id, limit),
    ).fetchall()
    out = []
    for r in rows:
        item = dict(r)
        item["items"] = json.loads(item.pop("items_json") or "[]")
        out.append(item)
    if mark_seen and out:
        with conn:
            conn.execute(
                "UPDATE alert_shortlists SET seen_at = datetime('now') "
                "WHERE client_id = ? AND alert_id = ? AND seen_at IS NULL",
                (client_id, alert_id),
            )
    return out


# ── Switching on and off ─────────────────────────────────────────────────────


def _save_upgrade(conn, alert_id, upgrade, client_id, *, enabled, reason=None, settled_day=None):
    now = _sqlite_utc(datetime.now(timezone.utc))
    conn.execute(
        """INSERT INTO alert_upgrades (alert_id, upgrade, client_id, enabled, enabled_at,
                                       disabled_at, disabled_reason, settled_day)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(alert_id, upgrade) DO UPDATE SET
               enabled = excluded.enabled,
               enabled_at = COALESCE(excluded.enabled_at, alert_upgrades.enabled_at),
               disabled_at = excluded.disabled_at,
               disabled_reason = excluded.disabled_reason,
               settled_day = COALESCE(excluded.settled_day, alert_upgrades.settled_day)""",
        (alert_id, upgrade, client_id, 1 if enabled else 0,
         now if enabled else None, None if enabled else now, reason, settled_day),
    )


def set_upgrade(client_id: str, alert_id: int, upgrade: str, enabled: bool,
                *, now: datetime | None = None) -> dict:
    """Enable daily shortlists, or turn an upgrade off. Shortlists charge on delivery.

    Raises LookupError for an unknown alert, ValueError for a bad upgrade or a
    paused alert, and credits.InsufficientCredits when today can't be paid.
    Switching off stops future deliveries; an already delivered shortlist is not refunded.
    """
    if upgrade not in UPGRADES or (enabled and upgrade not in offered_upgrades()):
        raise ValueError("This upgrade is not available.")
    alert = _alert_row(client_id, alert_id)
    if alert is None:
        raise LookupError("Alert not found")
    conn = _get_conn()
    day = karachi_day(now)
    if not enabled:
        with conn:
            _save_upgrade(conn, alert_id, upgrade, client_id, enabled=False, reason="user")
        return upgrade_state(client_id, alert_id, now=now)
    if alert["paused"]:
        raise ValueError("Resume this alert before switching this on.")

    today_row = None
    if upgrade == SHORTLIST:
        today_row = conn.execute(
            "SELECT status FROM alert_shortlists WHERE alert_id = ? AND day = ?",
            (alert_id, day),
        ).fetchone()
    # Enabling a shortlist checks affordability but does not reserve credits.
    if upgrade == SHORTLIST:
        # Charge only when a shortlist is produced. Enabling then stopping an
        # empty search must never consume credits.
        if credits.balance(client_id) < credits.COSTS[SHORTLIST]:
            raise credits.InsufficientCredits(SHORTLIST, credits.balance(client_id), credits.COSTS[SHORTLIST])
    elif not (today_row and today_row["status"] == "empty"):
        credits.spend(client_id, upgrade, ref=day_ref(alert_id, upgrade, day))
    with conn:
        if today_row and today_row["status"] == "unpaid":
            conn.execute("DELETE FROM alert_shortlists WHERE alert_id = ? AND day = ?",
                         (alert_id, day))
        _save_upgrade(conn, alert_id, upgrade, client_id, enabled=True, settled_day=day)
    return upgrade_state(client_id, alert_id, now=now)


def upgrade_state(client_id: str, alert_id: int, *, now: datetime | None = None) -> dict:
    day = karachi_day(now)
    balance = credits.balance(client_id)
    cost = daily_cost(client_id)
    return {
        "alert_id": alert_id,
        "upgrades": {u: _upgrade_view(alert_id, u, _upgrade_row(alert_id, u), day) for u in offered_upgrades()},
        "balance": balance,
        "daily_cost": cost,
        "days_covered": (balance // cost) if cost else None,
    }


def _switch_off_for_balance(conn, row, day):
    with conn:
        _save_upgrade(conn, row["alert_id"], row["upgrade"], row["client_id"],
                      enabled=False, reason="balance")
        conn.execute(
            """INSERT OR IGNORE INTO alert_upgrade_notices (client_id, alert_id, upgrade, kind, day)
               VALUES (?, ?, ?, 'balance_off', ?)""",
            (row["client_id"], row["alert_id"], row["upgrade"], day),
        )
    logger.info("[Paid alerts] %s switched off for alert %d: credits ran out",
                row["upgrade"], row["alert_id"])


# ── Daily jobs (run from the crawler after each alert flush) ─────────────────


def run_daily_jobs(*, now: datetime | None = None, dispatch: bool = True) -> dict:
    """Build due shortlists. Historical priority experiments run only when enabled. Idempotent.

    Cheap when there is nothing to do: one indexed query per upgrade.
    """
    summary = {"charged": 0, "switched_off": 0, "shortlists": 0, "empty": 0, "pushed": 0}
    conn = _get_conn()
    local = karachi_now(now)
    day = local.strftime("%Y-%m-%d")

    due_instant = conn.execute(
        """SELECT u.alert_id, u.upgrade, u.client_id FROM alert_upgrades u
           JOIN alerts a ON a.id = u.alert_id
           WHERE u.upgrade = ? AND u.enabled = 1 AND a.paused = 0
             AND (u.settled_day IS NULL OR u.settled_day <> ?)
           ORDER BY u.alert_id""",
        (INSTANT, day),
    ).fetchall() if PRIORITY_AVAILABLE else []
    for row in due_instant:
        try:
            credits.spend(row["client_id"], INSTANT, ref=day_ref(row["alert_id"], INSTANT, day))
        except credits.InsufficientCredits:
            _switch_off_for_balance(conn, row, day)
            summary["switched_off"] += 1
            continue
        with conn:
            conn.execute(
                "UPDATE alert_upgrades SET settled_day = ? WHERE alert_id = ? AND upgrade = ?",
                (day, row["alert_id"], INSTANT),
            )
        summary["charged"] += 1

    if local.hour < SHORTLIST_HOUR:
        return summary
    due_shortlists = conn.execute(
        """SELECT u.alert_id, u.upgrade, u.client_id, a.label, a.filters_json, a.notify_push
           FROM alert_upgrades u JOIN alerts a ON a.id = u.alert_id
           WHERE u.upgrade = ? AND u.enabled = 1 AND a.paused = 0
             AND NOT EXISTS (SELECT 1 FROM alert_shortlists s
                             WHERE s.alert_id = u.alert_id AND s.day = ?)
           ORDER BY u.alert_id LIMIT ?""",
        (SHORTLIST, day, MAX_SHORTLISTS_PER_RUN),
    ).fetchall()
    global _rank_deadline
    _rank_deadline = time.monotonic() + RANK_RUN_BUDGET_SECONDS
    try:
        for row in due_shortlists:
            try:
                result = _deliver_shortlist(row, day=day, now=now, dispatch=dispatch)
            except Exception:
                logger.exception("[Paid alerts] Shortlist failed for alert %d", row["alert_id"])
                continue
            summary[result["status_key"]] += 1
            summary["pushed"] += result.get("pushed", 0)
    finally:
        _rank_deadline = None
    return summary


def _recent_matches(alert_id: int, client_id: str, *, now: datetime | None) -> list[dict]:
    cutoff = _sqlite_utc(_utc_now(now) - timedelta(hours=SHORTLIST_WINDOW_HOURS))
    rows = _get_conn().execute(
        """SELECT m.id AS match_id, m.matched_at,
                  l.id AS listing_id, l.zameen_id, l.title, l.price, l.price_text,
                  l.bedrooms, l.bathrooms, l.area_size, l.area_name, l.location,
                  l.property_type, l.image_url, l.url, l.first_seen_at,
                  l.zameen_posted_at AS posted_at, l.zameen_updated_at AS updated_at
           FROM alert_matches m JOIN listings l ON l.id = m.listing_id
           WHERE m.alert_id = ? AND m.matched_at >= ? AND l.is_active = 1
             AND m.matched_at > COALESCE((SELECT MAX(created_at) FROM alert_shortlists
                 WHERE alert_id = m.alert_id AND status IN ('delivered', 'empty')), '')
             AND l.zameen_id NOT IN (SELECT zameen_id FROM hidden_listings WHERE client_id = ?)
           ORDER BY m.matched_at DESC, m.id DESC LIMIT ?""",
        (alert_id, cutoff, client_id, SHORTLIST_CANDIDATES),
    ).fetchall()
    return [dict(r) for r in rows]


def _deliver_shortlist(row, *, day: str, now: datetime | None, dispatch: bool) -> dict:
    # Freeze the window before ranking, so arrivals during ranking belong to the next window.
    now = _utc_now(now)
    conn = _get_conn()
    alert_id, client_id = row["alert_id"], row["client_id"]
    ref = day_ref(alert_id, SHORTLIST, day)
    candidates = _recent_matches(alert_id, client_id, now=now)

    if not candidates:
        # No new matches: today is free. Return a charge made when it was switched on.
        if _ref_state(ref) == "paid":
            credits.refund(ref)
        with conn:
            conn.execute(
                "INSERT OR IGNORE INTO alert_shortlists (alert_id, client_id, day, status, created_at) "
                "VALUES (?, ?, ?, 'empty', ?)",
                (alert_id, client_id, day, _sqlite_utc(_utc_now(now))),
            )
            conn.execute(
                "UPDATE alert_upgrades SET settled_day = ? WHERE alert_id = ? AND upgrade = ?",
                (day, alert_id, SHORTLIST),
            )
        return {"status_key": "empty"}

    if _ref_state(ref) != "refunded":
        try:
            credits.spend(client_id, SHORTLIST, ref=ref)
        except credits.InsufficientCredits:
            _switch_off_for_balance(conn, row, day)
            with conn:
                conn.execute(
                    "INSERT OR IGNORE INTO alert_shortlists (alert_id, client_id, day, status, match_count) "
                    "VALUES (?, ?, ?, 'unpaid', ?)",
                    (alert_id, client_id, day, len(candidates)),
                )
            return {"status_key": "switched_off"}

    try:
        filters = json.loads(row["filters_json"] or "{}")
    except json.JSONDecodeError:
        filters = {}
    picks, ranked_by = rank_matches(filters, candidates, limit=SHORTLIST_SIZE)
    with conn:
        cur = conn.execute(
            """INSERT OR IGNORE INTO alert_shortlists
                   (alert_id, client_id, day, status, match_count, ranked_by, items_json, created_at)
               VALUES (?, ?, ?, 'delivered', ?, ?, ?, ?)""",
            (alert_id, client_id, day, len(candidates), ranked_by, json.dumps(picks), _sqlite_utc(_utc_now(now))),
        )
        conn.execute(
            "UPDATE alert_upgrades SET settled_day = ? WHERE alert_id = ? AND upgrade = ?",
            (day, alert_id, SHORTLIST),
        )
    pushed = 0
    if dispatch and cur.rowcount == 1 and row["notify_push"]:
        pushed = _push_shortlist(row, day, picks, len(candidates))
    return {"status_key": "shortlists", "pushed": pushed}


def _push_shortlist(row, day: str, picks: list[dict], match_count: int) -> int:
    from app import personalization as pers

    subs = pers.list_push_subscriptions(row["client_id"])
    if not subs:
        return 0
    n = len(picks)
    payload = {
        "type": "alert_shortlist",
        "alert_id": row["alert_id"],
        "title": f"{row['label']}: today's shortlist",
        "body": (f"Top {n} of {match_count} new matches, with a reason for each."
                 if match_count > n else
                 f"{n} new match{'es' if n != 1 else ''}, with a reason for each."),
        "url": f"/?alerts=open&alert_id={row['alert_id']}&shortlist=1",
        "tag": f"shortlist-{row['alert_id']}-{day}",
        "count": n,
        "image": (picks[0] or {}).get("image_url") if picks else None,
    }
    sent = sum(1 for sub in subs if pers.send_push(sub, payload))
    if sent:
        conn = _get_conn()
        with conn:
            conn.execute(
                "UPDATE alert_shortlists SET notified_push = 1 WHERE alert_id = ? AND day = ?",
                (row["alert_id"], day),
            )
    return sent


# ── Ranking ──────────────────────────────────────────────────────────────────

_ITEM_FIELDS = (
    "zameen_id", "title", "price", "price_text", "bedrooms", "bathrooms", "area_size",
    "area_name", "location", "property_type", "image_url", "url", "matched_at",
)


def _fmt_pkr(n: int) -> str:
    return f"PKR {n:,}"


def _price_fit(filters: dict, price) -> float:
    """Lower is a better fit. Missing prices sort last."""
    if price is None:
        return float("inf")
    lo, hi = filters.get("price_min"), filters.get("price_max")
    if lo and hi:
        return abs(price - (lo + hi) / 2) / max(hi - lo, 1)
    if lo:
        return (price - lo) / max(lo, 1)
    # Only a ceiling, or no budget at all: cheaper is the better fit.
    return price / max(hi or 1, 1)


def _activity_day(listing: dict) -> str:
    return str(listing.get("updated_at") or listing.get("posted_at")
               or listing.get("first_seen_at") or listing.get("matched_at") or "")[:10]


def _day_ordinal(day: str) -> int:
    try:
        return datetime.strptime(day, "%Y-%m-%d").toordinal()
    except ValueError:
        return 0


def _fallback_reason(filters: dict, listing: dict, position: int) -> str:
    price = listing.get("price")
    hi, lo = filters.get("price_max"), filters.get("price_min")
    if price and hi and price <= hi:
        under = hi - price
        if under > 0:
            return f"{_fmt_pkr(price)} a month, {_fmt_pkr(under)} under your budget."
        return f"{_fmt_pkr(price)} a month, at your budget."
    if price and lo and not hi:
        return f"{_fmt_pkr(price)} a month, close to your minimum."
    if position == 0:
        return "The newest match for this alert."
    return "One of the newest matches for this alert."


def fallback_rank(filters: dict, listings: list[dict], limit: int = SHORTLIST_SIZE) -> list[dict]:
    """Deterministic ranking: newest day first, then best price fit, then newest row."""
    ordered = sorted(
        listings,
        key=lambda l: (
            # Newest source-activity day first: negate the date's ordinal.
            -_day_ordinal(_activity_day(l)),
            _price_fit(filters, l.get("price")),
            -(l.get("listing_id") or 0),
        ),
    )[:limit]
    return [
        {**{k: l.get(k) for k in _ITEM_FIELDS},
         "reason": _fallback_reason(filters, l, i), "trade_off": None}
        for i, l in enumerate(ordered)
    ]


# The crawler runs the daily jobs inline, so a slow Claude call must not hold
# it up. Each ranking gets a hard wall-clock limit and each run a total budget;
# past either, the shortlist uses the deterministic fallback. A timed-out call
# finishes in the background thread and its result is discarded.
RANK_CALL_TIMEOUT_SECONDS = float(os.environ.get("ZR_SHORTLIST_RANK_TIMEOUT", "20"))
RANK_RUN_BUDGET_SECONDS = float(os.environ.get("ZR_SHORTLIST_RANK_BUDGET", "60"))
_rank_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="shortlist-rank")
_rank_deadline: float | None = None


def rank_matches(filters: dict, listings: list[dict], *, limit: int = SHORTLIST_SIZE) -> tuple[list[dict], str]:
    """Rank with app.ranking when available; otherwise the deterministic fallback.

    Returns (items, ranked_by) where ranked_by is 'ranking' or 'fallback'.
    """
    try:
        from app.ranking import rank_listings
    except Exception:
        return fallback_rank(filters, listings, limit), "fallback"
    remaining = RANK_CALL_TIMEOUT_SECONDS
    if _rank_deadline is not None:
        remaining = min(remaining, _rank_deadline - time.monotonic())
    if remaining <= 0:
        return fallback_rank(filters, listings, limit), "fallback"
    try:
        future = _rank_pool.submit(rank_listings, filters, listings, brief=None, limit=limit)
        ranked = future.result(timeout=remaining)
        if inspect.isawaitable(ranked):
            # The contract is a plain function; don't block the crawler on a coroutine.
            getattr(ranked, "close", lambda: None)()
            raise TypeError("rank_listings returned an awaitable")
    except FutureTimeout:
        logger.warning("[Paid alerts] rank_listings took longer than %.0fs; using fallback ranking", remaining)
        return fallback_rank(filters, listings, limit), "fallback"
    except Exception:
        logger.exception("[Paid alerts] rank_listings failed; using fallback ranking")
        return fallback_rank(filters, listings, limit), "fallback"

    by_id = {str(l["zameen_id"]): l for l in listings}
    items, seen = [], set()
    for r in ranked or []:
        if not isinstance(r, dict):
            continue
        zid = str(r.get("zameen_id") or "")
        if zid not in by_id or zid in seen:
            continue
        seen.add(zid)
        listing = by_id[zid]
        items.append({
            **{k: listing.get(k) for k in _ITEM_FIELDS},
            "reason": str(r.get("reason") or "").strip() or None,
            "trade_off": str(r.get("trade_off") or "").strip() or None,
        })
        if len(items) >= limit:
            break
    if not items:
        return fallback_rank(filters, listings, limit), "fallback"
    return items, "ranking"


# ── Priority check (crawler side) ────────────────────────────────────────────


def priority_searches(*, now: datetime | None = None,
                      limit: int = MAX_PRIORITY_SEARCHES_PER_TICK) -> list[dict]:
    """Distinct Zameen search URLs for alerts with a paid priority check today.

    Least recently checked first, so with more searches than ``limit`` every
    search still gets its turn.
    """
    if not PRIORITY_AVAILABLE:
        return []

    from app.parsing import build_url, match_area
    from app.data import CITY_AREAS, PROPERTY_TYPES

    day = karachi_day(now)
    rows = _get_conn().execute(
        """SELECT u.alert_id, a.filters_json FROM alert_upgrades u
           JOIN alerts a ON a.id = u.alert_id
           WHERE u.upgrade = ? AND u.enabled = 1 AND a.paused = 0 AND u.settled_day = ?
           ORDER BY u.last_checked_at IS NOT NULL, u.last_checked_at, u.alert_id""",
        (INSTANT, day),
    ).fetchall()
    searches: dict[str, dict] = {}
    for r in rows:
        try:
            f = json.loads(r["filters_json"] or "{}")
        except json.JSONDecodeError:
            continue
        city = f.get("city") or "lahore"
        if city not in CITY_AREAS:
            continue
        area_name = match_area(f["area"], city=city) if f.get("area") else None
        area_info = CITY_AREAS[city].get(area_name) if area_name else None
        pt = (f.get("property_type") or "").lower()
        url = build_url(
            area=area_name, property_type=pt or None,
            bedrooms=f.get("bedrooms"), bedrooms_max=f.get("bedrooms_max"),
            price_min=f.get("price_min"), price_max=f.get("price_max"),
            furnished=f.get("furnished"), sort="newest", city=city,
        )
        entry = searches.get(url)
        if entry is None:
            if len(searches) >= limit:
                continue
            entry = searches[url] = {
                "url": url, "city": city, "alert_ids": [],
                "area_name": area_name,
                "area_slug": area_info[0] if area_info else None,
                "lat": area_info[2] if area_info else None,
                "lng": area_info[3] if area_info else None,
                "type_label": PROPERTY_TYPES[pt]["label"] if pt in PROPERTY_TYPES else None,
            }
        entry["alert_ids"].append(r["alert_id"])
    return list(searches.values())


async def check_priority_searches(client, session_headers, *, now: datetime | None = None,
                                  limit: int = MAX_PRIORITY_SEARCHES_PER_TICK,
                                  page_delay=(0.25, 0.75), sleep=None) -> dict:
    """Read page 1 (newest first) of each paid alert search and store the cards.

    Matching and push happen through the normal insert hook and the next
    alert flush. ``new`` counts listings this check found that the city-wide
    newest feed and earlier sweeps had not, which is the measure of what the
    paid check adds.
    """
    import asyncio
    from app.crawler_worker import _fetch, infer_area_from_location
    from app.db_listings import listing_write_batch, upsert_listing
    from app.scraper import enrich_from_search_state, extract_zameen_id, parse_listings

    sleep = sleep or asyncio.sleep
    summary = {"searches": 0, "pages": 0, "new": 0, "updated": 0}
    searches = priority_searches(now=now, limit=limit)
    conn = _get_conn()
    for i, s in enumerate(searches):
        if i:
            await sleep(random.uniform(*page_delay))
        html = await _fetch(s["url"], client, {**session_headers})
        summary["searches"] += 1
        checked = _sqlite_utc(_utc_now(now))
        marks = ",".join("?" * len(s["alert_ids"]))
        with conn:
            conn.execute(
                f"UPDATE alert_upgrades SET last_checked_at = ? "
                f"WHERE upgrade = ? AND alert_id IN ({marks})",
                [checked, INSTANT, *s["alert_ids"]],
            )
        if not html:
            continue
        listings = parse_listings(html)
        if not listings:
            continue
        summary["pages"] += 1
        enrich_from_search_state(html, listings)
        with listing_write_batch():
            for listing in listings:
                listing_url = listing.get("url", "")
                zid = extract_zameen_id(listing_url)
                if not zid:
                    continue
                if s["type_label"]:
                    listing["property_type"] = s["type_label"]
                if s["area_name"]:
                    area_name, area_slug, lat, lng = s["area_name"], s["area_slug"], s["lat"], s["lng"]
                else:
                    inferred = infer_area_from_location(s["city"], listing.get("location"))
                    area_name, area_slug, lat, lng = inferred or (None, None, None, None)
                result = upsert_listing(
                    zameen_id=zid, url=listing_url, city=s["city"],
                    area_name=area_name, area_slug=area_slug, lat=lat, lng=lng,
                    card_data=listing, search_state=listing.get("search_state"),
                    commit=False,
                )
                if result == "inserted":
                    summary["new"] += 1
                elif result == "updated":
                    summary["updated"] += 1
    return summary
