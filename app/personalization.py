"""Personalization: anonymous client identity, alerts, favorites, hidden, recently viewed, push notifications.

All state is server-side, keyed by an opaque `client_id` (UUID) the browser
generates and presents via the `X-Client-Id` header. There's no auth — losing
the client_id loses the state, same as clearing localStorage.
"""
import json
import logging
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

from app.database import _get_conn
from app.data import PROPERTY_TYPES

logger = logging.getLogger("zameenrentals")

CLIENT_ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")

# Alert filter fields. Mirrors the search API surface — every key listed here
# is honored by build_match_query() and the frontend save-search flow.
ALERT_FIELDS = (
    "city", "area", "property_type",
    "bedrooms", "bedrooms_max",
    "price_min", "price_max",
    "size_marla_min", "size_marla_max",
    "furnished", "q",
)

MAX_ALERTS_PER_CLIENT = 25
MAX_FAVORITES_PER_CLIENT = 500
MAX_HIDDEN_PER_CLIENT = 500
MAX_RECENT_VIEWS_PER_CLIENT = 100
ALERT_LABEL_MAX = 80
ALERT_MATCH_RETENTION_DAYS = 30
_SOURCE_ACTIVITY_SQL = "COALESCE(l.zameen_updated_at, l.zameen_posted_at, l.first_seen_at)"


# ── Schema ───────────────────────────────────────────────────────────────────


def init_personalization_schema():
    """Create personalization tables. Idempotent — safe to call on every boot."""
    conn = _get_conn()
    with conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS clients (
                client_id     TEXT PRIMARY KEY,
                created_at    TEXT NOT NULL DEFAULT (datetime('now')),
                last_seen_at  TEXT NOT NULL DEFAULT (datetime('now')),
                last_visit_at TEXT
            );

            CREATE TABLE IF NOT EXISTS alerts (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id       TEXT NOT NULL,
                label           TEXT NOT NULL,
                filters_json    TEXT NOT NULL,
                created_at      TEXT NOT NULL DEFAULT (datetime('now')),
                last_matched_at TEXT,
                last_seen_id    INTEGER,
                paused          INTEGER NOT NULL DEFAULT 0,
                notify_push     INTEGER NOT NULL DEFAULT 1,
                notify_inapp    INTEGER NOT NULL DEFAULT 1,
                FOREIGN KEY (client_id) REFERENCES clients(client_id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_alerts_client ON alerts(client_id);
            CREATE INDEX IF NOT EXISTS idx_alerts_active ON alerts(paused, last_matched_at);

            CREATE TABLE IF NOT EXISTS alert_matches (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                alert_id    INTEGER NOT NULL,
                client_id   TEXT NOT NULL,
                listing_id  INTEGER NOT NULL,
                zameen_id   TEXT NOT NULL,
                matched_at  TEXT NOT NULL DEFAULT (datetime('now')),
                seen_at     TEXT,
                notified_push INTEGER NOT NULL DEFAULT 0,
                UNIQUE(alert_id, listing_id),
                FOREIGN KEY (alert_id) REFERENCES alerts(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_alert_matches_client_unseen
                ON alert_matches(client_id, seen_at, matched_at);
            CREATE INDEX IF NOT EXISTS idx_alert_matches_alert ON alert_matches(alert_id, matched_at DESC);

            CREATE TABLE IF NOT EXISTS push_subscriptions (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id    TEXT NOT NULL,
                endpoint     TEXT NOT NULL UNIQUE,
                p256dh       TEXT NOT NULL,
                auth         TEXT NOT NULL,
                user_agent   TEXT,
                created_at   TEXT NOT NULL DEFAULT (datetime('now')),
                last_used_at TEXT,
                FOREIGN KEY (client_id) REFERENCES clients(client_id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_push_client ON push_subscriptions(client_id);

            CREATE TABLE IF NOT EXISTS favorites (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id   TEXT NOT NULL,
                zameen_id   TEXT NOT NULL,
                saved_at    TEXT NOT NULL DEFAULT (datetime('now')),
                note        TEXT,
                UNIQUE(client_id, zameen_id),
                FOREIGN KEY (client_id) REFERENCES clients(client_id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_favorites_client ON favorites(client_id, saved_at DESC);

            CREATE TABLE IF NOT EXISTS hidden_listings (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id   TEXT NOT NULL,
                zameen_id   TEXT NOT NULL,
                hidden_at   TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE(client_id, zameen_id),
                FOREIGN KEY (client_id) REFERENCES clients(client_id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_hidden_client ON hidden_listings(client_id);

            CREATE TABLE IF NOT EXISTS recent_views (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id   TEXT NOT NULL,
                zameen_id   TEXT NOT NULL,
                viewed_at   TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE(client_id, zameen_id),
                FOREIGN KEY (client_id) REFERENCES clients(client_id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_recent_client ON recent_views(client_id, viewed_at DESC);
        """)
        conn.execute(
            "DELETE FROM alert_matches WHERE alert_id NOT IN (SELECT id FROM alerts)"
        )


# ── Client identity ──────────────────────────────────────────────────────────


def is_valid_client_id(value: str | None) -> bool:
    return bool(value) and bool(CLIENT_ID_RE.match(value or ""))


def ensure_client(client_id: str, *, touch_visit: bool = False) -> dict | None:
    """Insert-or-update the clients row. Returns the row as a dict (or None for bad id)."""
    if not is_valid_client_id(client_id):
        return None
    conn = _get_conn()
    now = datetime.utcnow().isoformat()
    with conn:
        existing = conn.execute(
            "SELECT * FROM clients WHERE client_id = ?", (client_id,)
        ).fetchone()
        if existing is None:
            visit = now if touch_visit else None
            conn.execute(
                "INSERT INTO clients (client_id, created_at, last_seen_at, last_visit_at) VALUES (?, ?, ?, ?)",
                (client_id, now, now, visit),
            )
            return {
                "client_id": client_id,
                "created_at": now,
                "last_seen_at": now,
                "last_visit_at": visit,
            }
        if touch_visit:
            conn.execute(
                "UPDATE clients SET last_seen_at = ?, last_visit_at = ? WHERE client_id = ?",
                (now, now, client_id),
            )
        else:
            conn.execute(
                "UPDATE clients SET last_seen_at = ? WHERE client_id = ?",
                (now, client_id),
            )
    row = conn.execute(
        "SELECT * FROM clients WHERE client_id = ?", (client_id,)
    ).fetchone()
    return dict(row) if row else None


def get_client(client_id: str) -> dict | None:
    if not is_valid_client_id(client_id):
        return None
    conn = _get_conn()
    row = conn.execute(
        "SELECT * FROM clients WHERE client_id = ?", (client_id,)
    ).fetchone()
    return dict(row) if row else None


# ── Filter normalisation ─────────────────────────────────────────────────────


def normalize_filters(raw: dict) -> dict:
    """Strip unknown fields, coerce types, drop empties. Mirrors the search API."""
    if not isinstance(raw, dict):
        raise ValueError("filters must be an object")
    out: dict[str, Any] = {}
    for key in ALERT_FIELDS:
        if key not in raw:
            continue
        value = raw.get(key)
        if value is None or value == "":
            continue
        if key in ("bedrooms", "bedrooms_max", "price_min", "price_max"):
            try:
                value = int(value)
            except (TypeError, ValueError):
                continue
            if value < 0:
                continue
        elif key in ("size_marla_min", "size_marla_max"):
            try:
                value = float(value)
            except (TypeError, ValueError):
                continue
            if value < 0:
                continue
        elif key == "furnished":
            if isinstance(value, str):
                value = value.lower() in ("1", "true", "yes", "on")
            else:
                value = bool(value)
            if not value:
                continue
        elif key in ("city", "area", "property_type", "q"):
            value = str(value).strip()
            if not value:
                continue
        out[key] = value

    # City is the only required field; default to lahore (matches frontend).
    out.setdefault("city", "lahore")
    return out


def derive_alert_label(filters: dict) -> str:
    parts = []
    if filters.get("bedrooms"):
        if filters.get("bedrooms_max") and filters["bedrooms_max"] != filters["bedrooms"]:
            parts.append(f"{filters['bedrooms']}-{filters['bedrooms_max']} bed")
        else:
            parts.append(f"{filters['bedrooms']} bed")
    if filters.get("property_type"):
        info = PROPERTY_TYPES.get(filters["property_type"].lower())
        parts.append(info["label"] if info else filters["property_type"].title())
    location = filters.get("area") or (filters.get("city") or "lahore").title()
    parts.append(f"in {location}")
    if filters.get("price_max"):
        parts.append(f"under {filters['price_max'] // 1000}K")
    elif filters.get("price_min"):
        parts.append(f"over {filters['price_min'] // 1000}K")
    if filters.get("furnished"):
        parts.append("furnished")
    label = " ".join(parts) or "All listings"
    return label[:ALERT_LABEL_MAX]


# ── Alerts CRUD ──────────────────────────────────────────────────────────────


def list_alerts(client_id: str) -> list[dict]:
    if not is_valid_client_id(client_id):
        return []
    conn = _get_conn()
    rows = conn.execute(
        """
        SELECT a.*,
               CASE WHEN a.notify_inapp = 1 THEN
                   (SELECT COUNT(*) FROM alert_matches m WHERE m.alert_id = a.id AND m.seen_at IS NULL)
               ELSE 0 END AS unseen_count,
               (SELECT MAX(matched_at) FROM alert_matches m WHERE m.alert_id = a.id) AS last_match_at
        FROM alerts a
        WHERE a.client_id = ?
        ORDER BY a.created_at DESC
        """,
        (client_id,),
    ).fetchall()
    out = []
    for r in rows:
        item = dict(r)
        item["filters"] = json.loads(item.pop("filters_json") or "{}")
        item["paused"] = bool(item["paused"])
        item["notify_push"] = bool(item["notify_push"])
        item["notify_inapp"] = bool(item["notify_inapp"])
        out.append(item)
    return out


def get_alert(client_id: str, alert_id: int) -> dict | None:
    if not is_valid_client_id(client_id):
        return None
    conn = _get_conn()
    row = conn.execute(
        "SELECT * FROM alerts WHERE id = ? AND client_id = ?",
        (alert_id, client_id),
    ).fetchone()
    if row is None:
        return None
    item = dict(row)
    item["filters"] = json.loads(item.pop("filters_json") or "{}")
    item["paused"] = bool(item["paused"])
    item["notify_push"] = bool(item["notify_push"])
    item["notify_inapp"] = bool(item["notify_inapp"])
    return item


def count_alerts(client_id: str) -> int:
    conn = _get_conn()
    row = conn.execute(
        "SELECT COUNT(*) FROM alerts WHERE client_id = ?", (client_id,)
    ).fetchone()
    return row[0] if row else 0


def create_alert(client_id: str, *, label: str | None, filters: dict,
                 notify_push: bool = True, notify_inapp: bool = True) -> dict:
    ensure_client(client_id)
    norm = normalize_filters(filters)
    if count_alerts(client_id) >= MAX_ALERTS_PER_CLIENT:
        raise ValueError(f"Alert limit reached ({MAX_ALERTS_PER_CLIENT}).")
    final_label = (label or "").strip()[:ALERT_LABEL_MAX] or derive_alert_label(norm)
    conn = _get_conn()
    cur = conn.execute(
        """
        INSERT INTO alerts (client_id, label, filters_json, notify_push, notify_inapp)
        VALUES (?, ?, ?, ?, ?)
        """,
        (client_id, final_label, json.dumps(norm), 1 if notify_push else 0,
         1 if notify_inapp else 0),
    )
    conn.commit()
    alert_id = cur.lastrowid
    # Seed last_seen_id with the current max listing id so the alert only fires
    # on listings inserted *after* this point — never on the existing backlog.
    seed = conn.execute("SELECT COALESCE(MAX(id), 0) FROM listings").fetchone()[0]
    conn.execute(
        "UPDATE alerts SET last_seen_id = ?, last_matched_at = datetime('now') WHERE id = ?",
        (seed, alert_id),
    )
    conn.commit()
    return get_alert(client_id, alert_id)


def update_alert(client_id: str, alert_id: int, *,
                 label: str | None = None, paused: bool | None = None,
                 notify_push: bool | None = None, notify_inapp: bool | None = None,
                 filters: dict | None = None) -> dict | None:
    existing = get_alert(client_id, alert_id)
    if existing is None:
        return None
    fields, params = [], []
    if label is not None:
        clean = label.strip()[:ALERT_LABEL_MAX]
        if clean:
            fields.append("label = ?")
            params.append(clean)
    if paused is not None:
        fields.append("paused = ?")
        params.append(1 if paused else 0)
    if notify_push is not None:
        fields.append("notify_push = ?")
        params.append(1 if notify_push else 0)
    if notify_inapp is not None:
        fields.append("notify_inapp = ?")
        params.append(1 if notify_inapp else 0)
    if filters is not None:
        fields.append("filters_json = ?")
        params.append(json.dumps(normalize_filters(filters)))
    if not fields:
        return existing
    params.extend([alert_id, client_id])
    conn = _get_conn()
    conn.execute(
        f"UPDATE alerts SET {', '.join(fields)} WHERE id = ? AND client_id = ?",
        params,
    )
    conn.commit()
    return get_alert(client_id, alert_id)


def delete_alert(client_id: str, alert_id: int) -> bool:
    conn = _get_conn()
    conn.execute(
        "DELETE FROM alert_matches WHERE alert_id IN ("
        "SELECT id FROM alerts WHERE id = ? AND client_id = ?)",
        (alert_id, client_id),
    )
    cur = conn.execute(
        "DELETE FROM alerts WHERE id = ? AND client_id = ?",
        (alert_id, client_id),
    )
    conn.commit()
    return cur.rowcount > 0


# ── Matching ─────────────────────────────────────────────────────────────────


def _build_match_clauses(filters: dict, *, listings_alias: str = "l") -> tuple[list[str], list]:
    """Translate an alert's filter dict to SQL WHERE fragments + params.

    Mirrors app.db_listings._listing_filter_clauses but operates on a specific
    table alias and skips the city filter so callers can apply it selectively.
    """
    conds: list[str] = []
    params: list = []
    a = listings_alias
    if filters.get("city"):
        conds.append(f"{a}.city = ?")
        params.append(filters["city"])
    if filters.get("area"):
        conds.append(f"{a}.area_name = ?")
        params.append(filters["area"])
    if filters.get("property_type"):
        info = PROPERTY_TYPES.get(filters["property_type"].lower())
        if info:
            conds.append(f"{a}.property_type = ?")
            params.append(info["label"])
    bedrooms = filters.get("bedrooms")
    bedrooms_max = filters.get("bedrooms_max")
    if bedrooms and bedrooms_max:
        conds.append(f"{a}.bedrooms >= ? AND {a}.bedrooms <= ?")
        params.extend([bedrooms, bedrooms_max])
    elif bedrooms:
        conds.append(f"{a}.bedrooms = ?")
        params.append(bedrooms)
    if filters.get("price_min"):
        conds.append(f"{a}.price >= ?")
        params.append(filters["price_min"])
    if filters.get("price_max"):
        conds.append(f"{a}.price <= ?")
        params.append(filters["price_max"])
    size_min = filters.get("size_marla_min")
    size_max = filters.get("size_marla_max")
    size_expr = f"""(CASE
        WHEN {a}.area_size LIKE '% Marla' THEN CAST(REPLACE(REPLACE({a}.area_size, ' Marla', ''), ',', '') AS REAL)
        WHEN {a}.area_size LIKE '% Kanal' THEN CAST(REPLACE(REPLACE({a}.area_size, ' Kanal', ''), ',', '') AS REAL) * 20
        WHEN {a}.area_size LIKE '% sqft' THEN CAST(REPLACE(REPLACE({a}.area_size, ' sqft', ''), ',', '') AS REAL) / 225.0
        WHEN {a}.area_size LIKE '% Sq. Yd.' THEN CAST(REPLACE(REPLACE({a}.area_size, ' Sq. Yd.', ''), ',', '') AS REAL) * 9.0 / 225.0
        ELSE NULL END)"""
    if size_min is not None:
        conds.append(f"{size_expr} >= ?")
        params.append(size_min)
    if size_max is not None:
        conds.append(f"{size_expr} <= ?")
        params.append(size_max)
    if filters.get("furnished"):
        conds.append(
            f"((LOWER({a}.title) LIKE '%furnished%' OR LOWER(COALESCE({a}.amenities_json,'')) LIKE '%furnished%' OR LOWER(COALESCE({a}.details_json,'')) LIKE '%furnished%')"
            f" AND LOWER({a}.title) NOT LIKE '%unfurnished%'"
            f" AND LOWER(COALESCE({a}.amenities_json,'')) NOT LIKE '%unfurnished%'"
            f" AND LOWER(COALESCE({a}.details_json,'')) NOT LIKE '%unfurnished%')"
        )
    if filters.get("q"):
        conds.append(f"{a}.id IN (SELECT rowid FROM listings_fts WHERE listings_fts MATCH ?)")
        params.append(filters["q"])
    conds.append(f"{a}.is_active = 1")
    return conds, params


def listing_matches_alert(listing_row: dict, filters: dict) -> bool:
    """Apply filters that can be evaluated from a listing snapshot.

    The real-time insert hook uses the SQL matcher so full-text and unit-aware
    filters remain authoritative.
    """
    if not listing_row.get("is_active", 1):
        return False
    city = filters.get("city")
    if city and listing_row.get("city") != city:
        return False
    area = filters.get("area")
    if area and listing_row.get("area_name") != area:
        return False
    pt = filters.get("property_type")
    if pt:
        info = PROPERTY_TYPES.get(pt.lower())
        if info and listing_row.get("property_type") != info["label"]:
            return False
    beds = listing_row.get("bedrooms")
    if filters.get("bedrooms") and filters.get("bedrooms_max"):
        if beds is None or beds < filters["bedrooms"] or beds > filters["bedrooms_max"]:
            return False
    elif filters.get("bedrooms"):
        if beds != filters["bedrooms"]:
            return False
    price = listing_row.get("price")
    if filters.get("price_min") and (price is None or price < filters["price_min"]):
        return False
    if filters.get("price_max") and (price is None or price > filters["price_max"]):
        return False
    if filters.get("furnished"):
        haystack = " ".join(filter(None, [
            (listing_row.get("title") or "").lower(),
            (listing_row.get("amenities_json") or "").lower(),
            (listing_row.get("details_json") or "").lower(),
        ]))
        if "furnished" not in haystack or "unfurnished" in haystack:
            return False
    # Size and full-text filters require the SQL matcher.
    return True


def find_new_matches(*, limit_per_alert: int = 50) -> list[dict]:
    """Scan listings inserted since each alert's last_seen_id and record matches.

    Returns the list of newly-recorded matches (one row per match) with enough
    fields to format a notification.
    """
    conn = _get_conn()
    alerts = conn.execute(
        "SELECT id, client_id, filters_json, last_seen_id, paused, notify_push, notify_inapp, "
        "label, created_at "
        "FROM alerts WHERE paused = 0"
    ).fetchall()
    if not alerts:
        return []
    max_listing_id = conn.execute("SELECT COALESCE(MAX(id), 0) FROM listings").fetchone()[0]
    new_matches: list[dict] = []
    for a in alerts:
        try:
            filters = json.loads(a["filters_json"] or "{}")
        except json.JSONDecodeError:
            logger.warning("Alert %d has invalid filters_json", a["id"])
            continue
        cursor = a["last_seen_id"] or 0
        if cursor >= max_listing_id:
            continue
        conds, params = _build_match_clauses(filters)
        conds.append("l.id > ?")
        params.append(cursor)
        conds.append(f"datetime({_SOURCE_ACTIVITY_SQL}) >= datetime(?)")
        params.append(a["created_at"])
        # Exclude already-recorded matches for this alert (cheap because the
        # join is on an indexed unique pair).
        sql = f"""
            SELECT l.id, l.zameen_id, l.title, l.price, l.price_text, l.bedrooms,
                   l.bathrooms, l.area_name, l.location, l.image_url, l.url,
                   l.city, l.first_seen_at
            FROM listings l
            LEFT JOIN alert_matches m ON m.alert_id = ? AND m.listing_id = l.id
            WHERE {' AND '.join(conds)} AND m.id IS NULL
            ORDER BY l.id ASC
            LIMIT ?
        """
        rows = conn.execute(sql, [a["id"], *params, limit_per_alert]).fetchall()
        for row in rows:
            try:
                conn.execute(
                    """
                    INSERT INTO alert_matches (alert_id, client_id, listing_id, zameen_id)
                    VALUES (?, ?, ?, ?)
                    """,
                    (a["id"], a["client_id"], row["id"], row["zameen_id"]),
                )
                new_matches.append({
                    "alert_id": a["id"],
                    "alert_label": a["label"],
                    "client_id": a["client_id"],
                    "notify_push": bool(a["notify_push"]),
                    "notify_inapp": bool(a["notify_inapp"]),
                    "listing": dict(row),
                })
            except Exception:
                logger.exception("Failed to insert match for alert %d listing %d",
                                 a["id"], row["id"])
        next_cursor = rows[-1]["id"] if len(rows) >= limit_per_alert else max_listing_id
        conn.execute(
            "UPDATE alerts SET last_seen_id = ?, last_matched_at = datetime('now') WHERE id = ?",
            (next_cursor, a["id"]),
        )
    conn.commit()
    return new_matches


def record_match_for_inserted_listing(listing_id: int, listing_row: dict) -> list[dict]:
    """Hook invoked by upsert_listing on 'inserted' return. Returns new matches.

    The city pre-filter keeps this cheap, while the SQL matcher remains
    authoritative for filters such as full-text search and area-size units.
    """
    try:
        conn = _get_conn()
        alerts = conn.execute(
            "SELECT id, client_id, filters_json, paused, notify_push, notify_inapp, "
            "label, created_at "
            "FROM alerts WHERE paused = 0 AND (filters_json LIKE ? OR filters_json LIKE ?)",
            (f'%"city": "{listing_row.get("city")}"%',
             f"%\"city\":\"{listing_row.get('city')}\"%"),
        ).fetchall()
    except Exception:
        logger.exception("Failed to load alerts for inserted listing %s", listing_id)
        return []

    matches: list[dict] = []
    for a in alerts:
        try:
            filters = json.loads(a["filters_json"] or "{}")
        except json.JSONDecodeError:
            continue
        conds, params = _build_match_clauses(filters)
        conds.append("l.id = ?")
        params.append(listing_id)
        conds.append(f"datetime({_SOURCE_ACTIVITY_SQL}) >= datetime(?)")
        params.append(a["created_at"])
        try:
            listing = conn.execute(
                f"""
                SELECT l.id, l.zameen_id, l.title, l.price, l.price_text, l.bedrooms,
                       l.bathrooms, l.area_name, l.location, l.image_url, l.url,
                       l.city, l.first_seen_at
                FROM listings l
                WHERE {' AND '.join(conds)}
                """,
                params,
            ).fetchone()
        except Exception:
            logger.exception("Failed to validate real-time match alert=%d listing=%d",
                             a["id"], listing_id)
            continue
        if listing is None:
            continue
        try:
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO alert_matches (alert_id, client_id, listing_id, zameen_id)
                VALUES (?, ?, ?, ?)
                """,
                (a["id"], a["client_id"], listing_id, listing_row.get("zameen_id")),
            )
            if cur.rowcount == 0:
                continue
            conn.execute(
                "UPDATE alerts SET last_seen_id = MAX(COALESCE(last_seen_id, 0), ?), "
                "last_matched_at = datetime('now') WHERE id = ?",
                (listing_id, a["id"]),
            )
            matches.append({
                "alert_id": a["id"],
                "alert_label": a["label"],
                "client_id": a["client_id"],
                "notify_push": bool(a["notify_push"]),
                "notify_inapp": bool(a["notify_inapp"]),
                "listing": dict(listing),
            })
        except Exception:
            logger.exception("Failed to record real-time match alert=%d listing=%d",
                             a["id"], listing_id)
    if matches:
        conn.commit()
    return matches


def list_matches(client_id: str, *, alert_id: int | None = None,
                 unseen_only: bool = False, limit: int = 50) -> list[dict]:
    if not is_valid_client_id(client_id):
        return []
    conn = _get_conn()
    conds = ["m.client_id = ?", "a.notify_inapp = 1"]
    params: list = [client_id]
    if alert_id is not None:
        conds.append("m.alert_id = ?")
        params.append(alert_id)
    if unseen_only:
        conds.append("m.seen_at IS NULL")
    sql = f"""
        SELECT m.id AS match_id, m.alert_id, m.matched_at, m.seen_at,
               a.label AS alert_label,
               l.zameen_id, l.title, l.price, l.price_text, l.bedrooms, l.bathrooms,
               l.area_size, l.area_name, l.location, l.image_url, l.images_json,
               l.property_type, l.city, l.url, l.first_seen_at,
               l.zameen_posted_at AS posted_at, l.zameen_updated_at AS updated_at
        FROM alert_matches m
        JOIN alerts a ON a.id = m.alert_id
        JOIN listings l ON l.id = m.listing_id
        WHERE {' AND '.join(conds)}
        ORDER BY m.matched_at DESC, m.id DESC
        LIMIT ?
    """
    rows = conn.execute(sql, [*params, limit]).fetchall()
    return [dict(r) for r in rows]


def mark_matches_seen(client_id: str, *, match_ids: Iterable[int] | None = None,
                      alert_id: int | None = None) -> int:
    if not is_valid_client_id(client_id):
        return 0
    conn = _get_conn()
    if match_ids:
        ids = [int(x) for x in match_ids]
        if not ids:
            return 0
        placeholders = ",".join("?" * len(ids))
        cur = conn.execute(
            f"UPDATE alert_matches SET seen_at = datetime('now') "
            f"WHERE client_id = ? AND seen_at IS NULL AND id IN ({placeholders})",
            [client_id, *ids],
        )
    elif alert_id is not None:
        cur = conn.execute(
            "UPDATE alert_matches SET seen_at = datetime('now') "
            "WHERE client_id = ? AND alert_id = ? AND seen_at IS NULL",
            (client_id, alert_id),
        )
    else:
        cur = conn.execute(
            "UPDATE alert_matches SET seen_at = datetime('now') "
            "WHERE client_id = ? AND seen_at IS NULL",
            (client_id,),
        )
    conn.commit()
    return cur.rowcount


def unseen_match_count(client_id: str) -> int:
    if not is_valid_client_id(client_id):
        return 0
    conn = _get_conn()
    row = conn.execute(
        """
        SELECT COUNT(*)
        FROM alert_matches m
        JOIN alerts a ON a.id = m.alert_id
        WHERE m.client_id = ? AND m.seen_at IS NULL AND a.notify_inapp = 1
        """,
        (client_id,),
    ).fetchone()
    return row[0] if row else 0


def prune_old_matches(*, days: int = ALERT_MATCH_RETENTION_DAYS) -> int:
    conn = _get_conn()
    cur = conn.execute(
        "DELETE FROM alert_matches WHERE matched_at < datetime('now', ?)",
        (f"-{days} days",),
    )
    conn.commit()
    return cur.rowcount


def prune_stale_discovered_matches() -> int:
    """Drop matches discovered late for listings that predate the saved alert."""
    conn = _get_conn()
    cur = conn.execute(
        """
        DELETE FROM alert_matches
        WHERE EXISTS (
            SELECT 1
            FROM alerts a
            JOIN listings l ON l.id = alert_matches.listing_id
            WHERE a.id = alert_matches.alert_id
              AND datetime(COALESCE(l.zameen_updated_at, l.zameen_posted_at, l.first_seen_at))
                  < datetime(a.created_at)
        )
        """
    )
    conn.commit()
    return cur.rowcount


# ── Favorites / hidden / recently viewed ─────────────────────────────────────


def _enforce_limit(table: str, client_id: str, max_rows: int, *, order_col: str):
    conn = _get_conn()
    count = conn.execute(
        f"SELECT COUNT(*) FROM {table} WHERE client_id = ?", (client_id,)
    ).fetchone()[0]
    if count <= max_rows:
        return
    excess = count - max_rows
    conn.execute(
        f"DELETE FROM {table} WHERE id IN ("
        f"SELECT id FROM {table} WHERE client_id = ? "
        f"ORDER BY {order_col} ASC LIMIT ?)",
        (client_id, excess),
    )
    conn.commit()


def add_favorite(client_id: str, zameen_id: str, *, note: str | None = None) -> dict:
    ensure_client(client_id)
    conn = _get_conn()
    conn.execute(
        "INSERT OR IGNORE INTO favorites (client_id, zameen_id, note) VALUES (?, ?, ?)",
        (client_id, zameen_id, (note or "").strip()[:500] or None),
    )
    if note is not None:
        conn.execute(
            "UPDATE favorites SET note = ? WHERE client_id = ? AND zameen_id = ?",
            ((note or "").strip()[:500] or None, client_id, zameen_id),
        )
    conn.commit()
    _enforce_limit("favorites", client_id, MAX_FAVORITES_PER_CLIENT, order_col="saved_at")
    row = conn.execute(
        "SELECT * FROM favorites WHERE client_id = ? AND zameen_id = ?",
        (client_id, zameen_id),
    ).fetchone()
    return dict(row) if row else {}


def remove_favorite(client_id: str, zameen_id: str) -> bool:
    conn = _get_conn()
    cur = conn.execute(
        "DELETE FROM favorites WHERE client_id = ? AND zameen_id = ?",
        (client_id, zameen_id),
    )
    conn.commit()
    return cur.rowcount > 0


def list_favorites(client_id: str, limit: int = 200) -> list[dict]:
    if not is_valid_client_id(client_id):
        return []
    conn = _get_conn()
    rows = conn.execute(
        """
        SELECT f.zameen_id, f.saved_at, f.note,
               l.title, l.price, l.price_text, l.bedrooms, l.bathrooms,
               l.area_size, l.location, l.image_url, l.images_json,
               l.property_type, l.city, l.url, l.first_seen_at, l.is_active
        FROM favorites f
        LEFT JOIN listings l ON l.zameen_id = f.zameen_id
        WHERE f.client_id = ?
        ORDER BY f.saved_at DESC
        LIMIT ?
        """,
        (client_id, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def add_hidden(client_id: str, zameen_id: str) -> bool:
    ensure_client(client_id)
    conn = _get_conn()
    cur = conn.execute(
        "INSERT OR IGNORE INTO hidden_listings (client_id, zameen_id) VALUES (?, ?)",
        (client_id, zameen_id),
    )
    conn.commit()
    _enforce_limit("hidden_listings", client_id, MAX_HIDDEN_PER_CLIENT, order_col="hidden_at")
    return cur.rowcount > 0


def remove_hidden(client_id: str, zameen_id: str) -> bool:
    conn = _get_conn()
    cur = conn.execute(
        "DELETE FROM hidden_listings WHERE client_id = ? AND zameen_id = ?",
        (client_id, zameen_id),
    )
    conn.commit()
    return cur.rowcount > 0


def list_hidden(client_id: str, limit: int = 200) -> list[dict]:
    if not is_valid_client_id(client_id):
        return []
    conn = _get_conn()
    rows = conn.execute(
        """
        SELECT h.zameen_id, h.hidden_at,
               l.title, l.price, l.price_text, l.bedrooms, l.bathrooms,
               l.area_size, l.location, l.image_url, l.images_json,
               l.property_type, l.city, l.url
        FROM hidden_listings h
        LEFT JOIN listings l ON l.zameen_id = h.zameen_id
        WHERE h.client_id = ?
        ORDER BY h.hidden_at DESC
        LIMIT ?
        """,
        (client_id, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def get_hidden_zameen_ids(client_id: str) -> set[str]:
    if not is_valid_client_id(client_id):
        return set()
    conn = _get_conn()
    rows = conn.execute(
        "SELECT zameen_id FROM hidden_listings WHERE client_id = ?", (client_id,)
    ).fetchall()
    return {r["zameen_id"] for r in rows}


def get_favorite_zameen_ids(client_id: str) -> set[str]:
    if not is_valid_client_id(client_id):
        return set()
    conn = _get_conn()
    rows = conn.execute(
        "SELECT zameen_id FROM favorites WHERE client_id = ?", (client_id,)
    ).fetchall()
    return {r["zameen_id"] for r in rows}


def record_view(client_id: str, zameen_id: str):
    ensure_client(client_id)
    conn = _get_conn()
    now = datetime.utcnow().isoformat()
    # UPSERT to refresh viewed_at if the listing was already in the list.
    conn.execute(
        """
        INSERT INTO recent_views (client_id, zameen_id, viewed_at) VALUES (?, ?, ?)
        ON CONFLICT(client_id, zameen_id) DO UPDATE SET viewed_at = excluded.viewed_at
        """,
        (client_id, zameen_id, now),
    )
    conn.commit()
    _enforce_limit("recent_views", client_id, MAX_RECENT_VIEWS_PER_CLIENT, order_col="viewed_at")


def list_recent_views(client_id: str, limit: int = 50) -> list[dict]:
    if not is_valid_client_id(client_id):
        return []
    conn = _get_conn()
    rows = conn.execute(
        """
        SELECT r.zameen_id, r.viewed_at,
               l.title, l.price, l.price_text, l.bedrooms, l.bathrooms,
               l.area_size, l.location, l.image_url, l.images_json,
               l.property_type, l.city, l.url
        FROM recent_views r
        LEFT JOIN listings l ON l.zameen_id = r.zameen_id
        WHERE r.client_id = ?
        ORDER BY r.viewed_at DESC
        LIMIT ?
        """,
        (client_id, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def previous_visit_at(client_id: str) -> str | None:
    """The visit BEFORE the current one, used for 'new since your last visit'."""
    client = get_client(client_id)
    if not client:
        return None
    # last_visit_at is updated on the current visit, so we expose it as the
    # "previous" timestamp from the client's point of view — only refreshed
    # when /api/personalization/touch is called at the start of a session.
    return client.get("last_visit_at")


# ── Push subscriptions + dispatch ────────────────────────────────────────────


def save_push_subscription(client_id: str, *, endpoint: str, p256dh: str, auth: str,
                            user_agent: str | None = None) -> dict:
    ensure_client(client_id)
    if not endpoint or not p256dh or not auth:
        raise ValueError("endpoint, p256dh, and auth are required")
    conn = _get_conn()
    now = datetime.utcnow().isoformat()
    conn.execute(
        """
        INSERT INTO push_subscriptions (client_id, endpoint, p256dh, auth, user_agent, last_used_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(endpoint) DO UPDATE SET
            client_id = excluded.client_id,
            p256dh = excluded.p256dh,
            auth = excluded.auth,
            user_agent = excluded.user_agent,
            last_used_at = excluded.last_used_at
        """,
        (client_id, endpoint, p256dh, auth, user_agent, now),
    )
    conn.commit()
    row = conn.execute(
        "SELECT * FROM push_subscriptions WHERE endpoint = ?", (endpoint,)
    ).fetchone()
    return dict(row) if row else {}


def remove_push_subscription(*, endpoint: str, client_id: str | None = None) -> bool:
    conn = _get_conn()
    if client_id is None:
        cur = conn.execute(
            "DELETE FROM push_subscriptions WHERE endpoint = ?", (endpoint,)
        )
    else:
        cur = conn.execute(
            "DELETE FROM push_subscriptions WHERE endpoint = ? AND client_id = ?",
            (endpoint, client_id),
        )
    conn.commit()
    return cur.rowcount > 0


def list_push_subscriptions(client_id: str) -> list[dict]:
    if not is_valid_client_id(client_id):
        return []
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM push_subscriptions WHERE client_id = ? ORDER BY created_at DESC",
        (client_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def list_pending_push_matches(*, limit: int = 500) -> list[dict]:
    """Return recorded push matches that have not been delivered successfully."""
    conn = _get_conn()
    rows = conn.execute(
        """
        SELECT m.id AS match_id, a.id AS alert_id, a.label AS alert_label,
               a.client_id, a.notify_push, a.notify_inapp,
               l.id, l.zameen_id, l.title, l.price, l.price_text, l.bedrooms,
               l.bathrooms, l.area_name, l.location, l.image_url, l.url,
               l.city, l.first_seen_at
        FROM alert_matches m
        JOIN alerts a ON a.id = m.alert_id
        JOIN listings l ON l.id = m.listing_id
        WHERE m.notified_push = 0 AND a.paused = 0 AND a.notify_push = 1
          AND datetime(COALESCE(l.zameen_updated_at, l.zameen_posted_at, l.first_seen_at))
              >= datetime(a.created_at)
          AND EXISTS (
              SELECT 1 FROM push_subscriptions s WHERE s.client_id = a.client_id
          )
        ORDER BY m.id ASC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [
        {
            "match_id": row["match_id"],
            "alert_id": row["alert_id"],
            "alert_label": row["alert_label"],
            "client_id": row["client_id"],
            "notify_push": bool(row["notify_push"]),
            "notify_inapp": bool(row["notify_inapp"]),
            "listing": {
                key: row[key]
                for key in (
                    "id", "zameen_id", "title", "price", "price_text",
                    "bedrooms", "bathrooms", "area_name", "location",
                    "image_url", "url", "city", "first_seen_at",
                )
            },
        }
        for row in rows
    ]


# ── VAPID key handling ───────────────────────────────────────────────────────

_VAPID_DIR = Path(__file__).resolve().parent.parent / "data"
_VAPID_PRIVATE_PATH = _VAPID_DIR / "vapid_private.pem"
_VAPID_PUBLIC_PATH = _VAPID_DIR / "vapid_public.txt"

_VAPID_CACHE: dict[str, Any] = {}


def ensure_vapid_keys() -> dict[str, str]:
    """Load or generate the VAPID keypair. Keys are persisted to data/.

    Returns {"public_key": <urlsafe-base64>, "private_pem": <pem string>,
             "subject": <contact mailto:>}
    """
    if "public_key" in _VAPID_CACHE and "private_pem" in _VAPID_CACHE:
        return _VAPID_CACHE  # type: ignore[return-value]

    import os
    subject = os.getenv("ZAMEENRENTALS_VAPID_SUBJECT", "mailto:hello@zameenrentals.local")

    if _VAPID_PRIVATE_PATH.exists() and _VAPID_PUBLIC_PATH.exists():
        private_pem = _VAPID_PRIVATE_PATH.read_text()
        public_key = _VAPID_PUBLIC_PATH.read_text().strip()
        _VAPID_CACHE.update({"public_key": public_key, "private_pem": private_pem,
                             "subject": subject})
        return _VAPID_CACHE  # type: ignore[return-value]

    # Generate a fresh keypair.
    import base64
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    private_key = ec.generate_private_key(ec.SECP256R1())
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    raw_public = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint,
    )
    public_key = base64.urlsafe_b64encode(raw_public).rstrip(b"=").decode("utf-8")

    _VAPID_DIR.mkdir(parents=True, exist_ok=True)
    _VAPID_PRIVATE_PATH.write_text(private_pem)
    _VAPID_PUBLIC_PATH.write_text(public_key)
    try:
        _VAPID_PRIVATE_PATH.chmod(0o600)
    except OSError:
        pass
    logger.info("Generated VAPID keypair at %s", _VAPID_PRIVATE_PATH)

    _VAPID_CACHE.update({"public_key": public_key, "private_pem": private_pem,
                         "subject": subject})
    return _VAPID_CACHE  # type: ignore[return-value]


def vapid_public_key() -> str:
    return ensure_vapid_keys()["public_key"]


def send_push(subscription: dict, payload: dict, *, ttl: int = 86400) -> bool:
    """Send a single push. Returns True if delivered, False to mark stale."""
    try:
        from pywebpush import WebPushException, webpush
    except ImportError:
        logger.warning("pywebpush not installed — skipping push dispatch")
        return False

    keys = ensure_vapid_keys()
    try:
        webpush(
            subscription_info={
                "endpoint": subscription["endpoint"],
                "keys": {"p256dh": subscription["p256dh"], "auth": subscription["auth"]},
            },
            data=json.dumps(payload),
            vapid_private_key=keys["private_pem"],
            vapid_claims={"sub": keys["subject"]},
            ttl=ttl,
        )
        return True
    except WebPushException as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        if status in (404, 410):
            logger.info("Push subscription gone (%s) — removing", status)
            remove_push_subscription(endpoint=subscription["endpoint"])
        else:
            logger.warning("WebPush failed (status=%s): %s", status, exc)
        return False
    except Exception:
        logger.exception("Unexpected push send error")
        return False


def dispatch_matches(matches: list[dict]) -> dict:
    """Send web-push notifications for the given matches. Returns counts."""
    if not matches:
        return {"sent": 0, "skipped": 0, "no_subscription": 0, "failed": 0}
    conn = _get_conn()
    # Bundle matches per client_id + alert so a single push can carry up to N.
    grouped: dict[tuple[str, int], list[dict]] = {}
    for m in matches:
        if not m.get("notify_push"):
            continue
        key = (m["client_id"], m["alert_id"])
        grouped.setdefault(key, []).append(m)

    sent = 0
    failed = 0
    no_subscription = 0
    skipped = sum(1 for m in matches if not m.get("notify_push"))

    for (client_id, alert_id), group in grouped.items():
        subs = list_push_subscriptions(client_id)
        if not subs:
            no_subscription += 1
            continue
        first = group[0]
        listing = first["listing"]
        title = first.get("alert_label") or "ZameenRentals"
        count = len(group)
        if count == 1:
            body = listing.get("title") or "New rental matches your alert"
            url = listing.get("url") or "/"
            tag = f"alert-{alert_id}-{listing.get('zameen_id')}"
        else:
            body = f"{count} new rentals match your alert"
            url = f"/?alerts=open&alert_id={alert_id}"
            tag = f"alert-{alert_id}-bundle"

        payload = {
            "type": "alert_match",
            "alert_id": alert_id,
            "title": f"{title}",
            "body": body,
            "url": url,
            "tag": tag,
            "count": count,
            "image": listing.get("image_url"),
        }
        match_ids = [m.get("match_id") for m in group if m.get("match_id")]
        delivered = False
        for sub in subs:
            ok = send_push(sub, payload)
            if ok:
                delivered = True
                sent += 1
                conn.execute(
                    "UPDATE push_subscriptions SET last_used_at = datetime('now') WHERE id = ?",
                    (sub["id"],),
                )
            else:
                failed += 1
        if match_ids and delivered:
            placeholders = ",".join("?" * len(match_ids))
            conn.execute(
                f"UPDATE alert_matches SET notified_push = 1 WHERE id IN ({placeholders})",
                match_ids,
            )
    conn.commit()
    return {"sent": sent, "failed": failed, "no_subscription": no_subscription,
            "skipped": skipped}


def run_match_cycle(*, dispatch: bool = True) -> dict:
    """Find new alert matches and (optionally) dispatch push notifications.

    Designed to be called from the crawler between cycles. Returns a summary.
    """
    stale_pruned = prune_stale_discovered_matches()
    new_matches = find_new_matches()
    summary = {"matches": len(new_matches)}
    if dispatch:
        summary.update(dispatch_matches(list_pending_push_matches()))
    pruned = prune_old_matches()
    summary["pruned"] = pruned
    summary["stale_pruned"] = stale_pruned
    return summary
