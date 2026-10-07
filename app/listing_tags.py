"""Listing tags from Jev: who may rent, backup power, separate entrance, new build.

Tags live in their own table, keyed by zameen_id, so the crawler never waits on
the decision API. tools/tag_listings.py fills it; search reads it. A tag is only
shown or filtered on when Jev was confident, so an unsure answer never hides a
listing.
"""
import asyncio
import json
import logging
import time

from app.database import _get_conn
from app.decisions import DecisionError, choice, noul

logger = logging.getLogger("zameenrentals")

SCHEMA = """
    CREATE TABLE IF NOT EXISTS listing_tags (
        zameen_id             TEXT PRIMARY KEY,
        content_hash          TEXT,
        had_description       INTEGER NOT NULL DEFAULT 0,
        tenant_fit            TEXT,
        tenant_fit_confidence REAL,
        backup_power          REAL,
        separate_entrance     REAL,
        newly_built           REAL,
        model                 TEXT NOT NULL,
        input_tokens          INTEGER,
        scored_at             TEXT NOT NULL DEFAULT (datetime('now'))
    );
    CREATE INDEX IF NOT EXISTS idx_listing_tags_tenant
        ON listing_tags(tenant_fit, tenant_fit_confidence);
"""

TENANT_FITS = ("family", "bachelor", "either", "unclear")
FEATURES = ("backup_power", "separate_entrance", "newly_built")

# Thresholds for acting on an answer. Tune them with tools/eval_listing_tags.py.
TENANT_MIN_CONFIDENCE = 0.7
FEATURE_MIN_PROBABILITY = 0.8

QUESTIONS = {
    "tenant_fit": choice(
        "Who does this rental listing say may rent it? Judge only from what it states. "
        "Calling it a 'family home' or 'family apartment' as decoration does not count.",
        {
            "family": "Families only, or says no bachelors",
            "bachelor": "Bachelors, students, working men or women, or singles welcome",
            "either": "Says both families and bachelors are welcome",
            "unclear": "Does not say who may rent it",
        },
    ),
    "backup_power": noul(
        "The listing says the unit has backup power: solar panels, UPS, inverter or generator."),
    "separate_entrance": noul(
        "The listing says the unit has its own separate entrance or gate, not shared "
        "with another portion of the building."),
    "newly_built": noul(
        "The listing says the property is brand new, newly built or never lived in."),
}

_DESCRIPTION_CHARS = 800
_MAX_AMENITIES = 15
_ABORT_AFTER_CONSECUTIVE_FAILURES = 5


def init_listing_tags_schema(conn=None):
    conn = conn or _get_conn()
    with conn:
        conn.executescript(SCHEMA)


def listing_state(row):
    """Compact text Jev judges. Only fields that bear on the questions."""
    parts = [f"Rental listing in {(row['city'] or '').title()}, {row['area_name'] or 'unknown area'}."]
    facts = []
    if row["property_type"]:
        facts.append(f"Type: {row['property_type']}")
    if row["price"]:
        facts.append(f"Rent: PKR {row['price']:,}/month")
    if row["bedrooms"]:
        facts.append(f"Beds: {row['bedrooms']}")
    if row["area_size"]:
        facts.append(f"Size: {row['area_size']}")
    if facts:
        parts.append(". ".join(facts) + ".")
    parts.append(f"Title: {row['title']}")
    if row["description"]:
        desc = " ".join(row["description"].split())[:_DESCRIPTION_CHARS]
        parts.append(f"Description: {desc}")
    amenities = _amenity_names(row["amenities_json"])
    if amenities:
        parts.append("Amenities: " + ", ".join(amenities[:_MAX_AMENITIES]))
    return "\n".join(parts)


def _amenity_names(raw):
    if not raw:
        return []
    try:
        items = json.loads(raw)
    except (TypeError, ValueError):
        return []
    if not isinstance(items, list):
        return []
    return [str(i.get("name") if isinstance(i, dict) else i) for i in items if i]


def listings_needing_tags(*, limit, city=None, include_title_only=False):
    """Active listings with no tag, or whose content or description changed since tagging."""
    conditions = [
        "l.is_active = 1",
        "COALESCE(l.title, '') != ''",
        "(t.zameen_id IS NULL OR t.content_hash IS NOT l.content_hash"
        " OR (t.had_description = 0 AND COALESCE(l.description, '') != ''))",
    ]
    params = []
    if not include_title_only:
        conditions.append("COALESCE(l.description, '') != ''")
    if city:
        conditions.append("l.city = ?")
        params.append(city)
    params.append(limit)
    return _get_conn().execute(
        f"""
        SELECT l.* FROM listings l
        LEFT JOIN listing_tags t ON t.zameen_id = l.zameen_id
        WHERE {' AND '.join(conditions)}
        ORDER BY l.last_seen_at DESC
        LIMIT ?
        """,
        params,
    ).fetchall()


def save_tags(row, decision):
    a = decision.answers
    tenant = a.get("tenant_fit")
    with _get_conn() as conn:
        conn.execute(
            """
            INSERT INTO listing_tags (zameen_id, content_hash, had_description, tenant_fit,
                tenant_fit_confidence, backup_power, separate_entrance, newly_built,
                model, input_tokens, scored_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(zameen_id) DO UPDATE SET
                content_hash = excluded.content_hash,
                had_description = excluded.had_description,
                tenant_fit = excluded.tenant_fit,
                tenant_fit_confidence = excluded.tenant_fit_confidence,
                backup_power = excluded.backup_power,
                separate_entrance = excluded.separate_entrance,
                newly_built = excluded.newly_built,
                model = excluded.model,
                input_tokens = excluded.input_tokens,
                scored_at = excluded.scored_at
            """,
            (
                row["zameen_id"], row["content_hash"], int(bool(row["description"])),
                tenant.value if tenant and tenant.value in TENANT_FITS else None,
                tenant.confidence if tenant else None,
                *(a[name].value if name in a else None for name in FEATURES),
                decision.model, decision.input_tokens,
            ),
        )


async def tag_listings(provider, *, limit=500, concurrency=4, city=None,
                       include_title_only=False):
    """Tag up to `limit` listings. Stops early when the API keeps failing."""
    rows = listings_needing_tags(limit=limit, city=city, include_title_only=include_title_only)
    stats = {"candidates": len(rows), "tagged": 0, "failed": 0, "input_tokens": 0,
             "latencies_ms": [], "aborted": None}
    sem = asyncio.Semaphore(concurrency)
    consecutive_failures = 0
    stop = asyncio.Event()

    async def one(row):
        nonlocal consecutive_failures
        async with sem:
            if stop.is_set():
                return
            started = time.perf_counter()
            try:
                decision = await provider.decide(listing_state(row), QUESTIONS)
            except DecisionError as exc:
                stats["failed"] += 1
                consecutive_failures += 1
                logger.warning("[Tags] %s: %s", row["zameen_id"], exc)
                if not exc.retryable or consecutive_failures >= _ABORT_AFTER_CONSECUTIVE_FAILURES:
                    stats["aborted"] = str(exc)
                    stop.set()
                return
            stats["latencies_ms"].append((time.perf_counter() - started) * 1000)
            consecutive_failures = 0
            save_tags(row, decision)
            stats["tagged"] += 1
            stats["input_tokens"] += decision.input_tokens

    await asyncio.gather(*(one(r) for r in rows))
    return stats


# ── Read side: search filters and the per-listing `tags` object ──

def tag_filter_clauses(*, tenant=None, backup_power=None, separate_entrance=None):
    """SQL conditions on listings.zameen_id. Only confident tags match."""
    conditions, params = [], []
    if tenant in ("family", "bachelor"):
        conditions.append(
            "zameen_id IN (SELECT zameen_id FROM listing_tags"
            " WHERE tenant_fit IN (?, 'either') AND tenant_fit_confidence >= ?)")
        params.extend([tenant, TENANT_MIN_CONFIDENCE])
    for name, wanted in (("backup_power", backup_power), ("separate_entrance", separate_entrance)):
        if wanted:
            conditions.append(
                f"zameen_id IN (SELECT zameen_id FROM listing_tags WHERE {name} >= ?)")
            params.append(FEATURE_MIN_PROBABILITY)
    return conditions, params


def public_tags(row):
    """Tags a user may see. None means unknown; a low noul means "not stated", never "no"."""
    tenant = row["tenant_fit"]
    confident_tenant = (tenant in ("family", "bachelor", "either")
                        and (row["tenant_fit_confidence"] or 0) >= TENANT_MIN_CONFIDENCE)
    tags = {"tenant_fit": tenant if confident_tenant else None}
    for name in FEATURES:
        tags[name] = True if (row[name] or 0) >= FEATURE_MIN_PROBABILITY else None
    return tags


def attach_tags(listings):
    """Add a `tags` dict to each listing that has been tagged."""
    ids = [item["zameen_id"] for item in listings if item.get("zameen_id")]
    if not ids:
        return listings
    marks = ",".join("?" * len(ids))
    rows = _get_conn().execute(
        f"SELECT * FROM listing_tags WHERE zameen_id IN ({marks})", ids).fetchall()
    by_id = {r["zameen_id"]: public_tags(r) for r in rows}
    for item in listings:
        tags = by_id.get(item.get("zameen_id"))
        if tags:
            item["tags"] = tags
    return listings
