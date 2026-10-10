"""Append-only history of what Zameen reported about each listing, and when we saw it.

Zameen moves a listing's "Added" date forward while keeping its ID, and the
listings table keeps only the latest value, so every such change erased the
earlier evidence (docs/listing-trust-2026-10-10). This table keeps each distinct
version of a listing, per source page type, with Zameen's raw epochs and labels.

A version that is seen again only extends ``last_observed_at`` and
``observation_count``, so continued visibility stays measurable. Rows are never
deleted and never invalidated by listing edits.

Times are UTC ISO 8601 with an explicit offset. Zameen's epochs are stored as
reported, not interpreted.
"""
import hashlib
import json
import logging
from datetime import datetime, timezone

from app.database import _get_conn

logger = logging.getLogger("zameenrentals")

SOURCES = ("search_card", "detail_page", "snapshot_import")

SCHEMA = """
    CREATE TABLE IF NOT EXISTS listing_observations (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        zameen_id           TEXT NOT NULL,
        source              TEXT NOT NULL,
        version_hash        TEXT NOT NULL,
        first_observed_at   TEXT NOT NULL,
        last_observed_at    TEXT NOT NULL,
        observation_count   INTEGER NOT NULL DEFAULT 1,
        added_text          TEXT,
        last_added_text     TEXT,
        updated_text        TEXT,
        last_updated_text   TEXT,
        created_epoch       REAL,
        updated_epoch       REAL,
        reactivated_epoch   REAL,
        approved_epoch      REAL,
        product             TEXT,
        state               TEXT,
        purpose             TEXT,
        is_verified         INTEGER,
        photo_count         INTEGER,
        video_count         INTEGER,
        agency_external_id  TEXT,
        agency_tier         INTEGER,
        agency_product      TEXT,
        price               INTEGER,
        title               TEXT,
        image_url           TEXT,
        page_url            TEXT,
        provenance          TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_listing_observations_latest
        ON listing_observations(zameen_id, source, last_observed_at);
    CREATE UNIQUE INDEX IF NOT EXISTS idx_listing_observations_version
        ON listing_observations(zameen_id, source, version_hash, first_observed_at);
"""

# Fields that make a new version. Zameen derives the relative labels from the
# epochs ("3 hours ago" changes on every crawl), so labels only count when no
# epoch was reported.
_VERSION_FIELDS = (
    "created_epoch", "updated_epoch", "reactivated_epoch", "approved_epoch",
    "product", "state", "purpose", "is_verified", "photo_count", "video_count",
    "agency_external_id", "agency_tier", "agency_product", "price", "title", "image_url",
)
_LABEL_FIELDS = ("added_text", "updated_text")
_STORED_FIELDS = _VERSION_FIELDS + _LABEL_FIELDS


def init_listing_observations_schema(conn=None):
    conn = conn or _get_conn()
    with conn:
        conn.executescript(SCHEMA)


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def utc_iso(naive_utc):
    """Mark a naive UTC timestamp string (how the listings table stores times) as UTC."""
    if not naive_utc:
        return None
    parsed = datetime.fromisoformat(str(naive_utc).replace(" ", "T"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat(timespec="seconds")


def version_hash(fields):
    keyed = {k: fields.get(k) for k in _VERSION_FIELDS}
    if fields.get("created_epoch") is None:
        keyed.update({k: fields.get(k) for k in _LABEL_FIELDS})
    return hashlib.sha256(json.dumps(keyed, sort_keys=True).encode()).hexdigest()[:32]


def record_observation(conn, zameen_id, source, fields, *, observed_at=None,
                       page_url=None, provenance=None, merge=True):
    """Record that ``source`` showed ``fields`` for a listing at ``observed_at``.

    With ``merge`` (live crawls), an unchanged version extends the latest row
    for this listing and source. Without it (historical imports), each
    observation is its own row; re-importing the same one is a no-op.
    Returns "inserted", "extended" or "duplicate".
    """
    if source not in SOURCES:
        raise ValueError(f"unknown observation source: {source}")
    fields = {k: v for k, v in (fields or {}).items() if k in _STORED_FIELDS and v is not None}
    if not fields:
        return "duplicate"
    observed_at = observed_at or utc_now()
    v_hash = version_hash(fields)

    if merge:
        latest = conn.execute(
            """SELECT id, version_hash FROM listing_observations
               WHERE zameen_id = ? AND source = ?
               ORDER BY last_observed_at DESC, id DESC LIMIT 1""",
            (zameen_id, source),
        ).fetchone()
        if latest is not None and latest["version_hash"] == v_hash:
            conn.execute(
                """UPDATE listing_observations SET
                       last_observed_at = MAX(last_observed_at, ?),
                       observation_count = observation_count + 1,
                       last_added_text = COALESCE(?, last_added_text),
                       last_updated_text = COALESCE(?, last_updated_text)
                   WHERE id = ?""",
                (observed_at, fields.get("added_text"), fields.get("updated_text"), latest["id"]),
            )
            return "extended"

    columns = ["zameen_id", "source", "version_hash", "first_observed_at", "last_observed_at",
               "last_added_text", "last_updated_text", "page_url", "provenance", *fields]
    values = [zameen_id, source, v_hash, observed_at, observed_at,
              fields.get("added_text"), fields.get("updated_text"), page_url, provenance,
              *fields.values()]
    cur = conn.execute(
        f"INSERT OR IGNORE INTO listing_observations ({', '.join(columns)}) "
        f"VALUES ({', '.join('?' for _ in columns)})",
        values,
    )
    return "inserted" if cur.rowcount else "duplicate"


def card_observation_fields(card_data, search_state=None):
    """Observation fields from a search-results card and its embedded search hit."""
    from app.db_listings import split_zameen_age_text

    added_text, updated_text = split_zameen_age_text(card_data.get("added"), card_data.get("updated"))
    fields = {
        "added_text": added_text,
        "updated_text": updated_text,
        "price": card_data.get("price"),
        "title": card_data.get("title"),
        "image_url": card_data.get("image_url"),
    }
    fields.update((search_state or {}).get("lifecycle") or {})
    return fields


def get_observations(zameen_id, conn=None):
    """All recorded observations of one listing, oldest first."""
    conn = conn or _get_conn()
    rows = conn.execute(
        """SELECT * FROM listing_observations WHERE zameen_id = ?
           ORDER BY first_observed_at, id""",
        (zameen_id,),
    ).fetchall()
    return [dict(r) for r in rows]
