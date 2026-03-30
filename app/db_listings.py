"""Listing CRUD operations and local search queries."""
import hashlib, json, logging
from datetime import datetime

from app.database import _get_conn
from app.data import PROPERTY_TYPES

logger = logging.getLogger("zameenrentals")


def content_hash(price, title, bedrooms, bathrooms, area_size):
    """Hash card-level fields to detect changes."""
    raw = f"{price}|{title}|{bedrooms}|{bathrooms}|{area_size}"
    return hashlib.md5(raw.encode()).hexdigest()


def detail_hash(phone, description):
    """Hash detail-level fields to detect changes."""
    raw = f"{phone}|{description}"
    return hashlib.md5(raw.encode()).hexdigest()


def upsert_listing(*, zameen_id, url, city, area_name=None, area_slug=None,
                   lat=None, lng=None, card_data=None, detail_data=None):
    """Insert or update a listing. Returns 'inserted', 'updated', or 'unchanged'."""
    conn = _get_conn()
    now = datetime.utcnow().isoformat()

    existing = conn.execute(
        "SELECT id, content_hash, detail_hash FROM listings WHERE zameen_id = ?",
        (zameen_id,)
    ).fetchone()

    if card_data:
        c_hash = content_hash(
            card_data.get("price"), card_data.get("title"),
            card_data.get("bedrooms"), card_data.get("bathrooms"),
            card_data.get("area_size")
        )

        if existing is None:
            images = card_data.get("images", [])
            if not images and card_data.get("image_url"):
                images = [card_data["image_url"]]
            conn.execute("""
                INSERT INTO listings (
                    zameen_id, url, title, price, price_text, bedrooms, bathrooms,
                    area_size, location, image_url, images_json, property_type,
                    added_text, city, area_name, area_slug, latitude, longitude,
                    card_scraped_at, last_seen_at, content_hash, is_active
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            """, (
                zameen_id, url, card_data.get("title"), card_data.get("price"),
                card_data.get("price_text"), card_data.get("bedrooms"),
                card_data.get("bathrooms"), card_data.get("area_size"),
                card_data.get("location"), card_data.get("image_url"),
                json.dumps(images) if images else None,
                card_data.get("property_type"), card_data.get("added"),
                city, area_name, area_slug, lat, lng, now, now, c_hash
            ))
            conn.commit()
            return "inserted"

        if existing["content_hash"] == c_hash:
            conn.execute(
                "UPDATE listings SET last_seen_at = ?, is_active = 1 WHERE zameen_id = ?",
                (now, zameen_id)
            )
            conn.commit()
            return "unchanged"

        # Card data changed
        images = card_data.get("images", [])
        if not images and card_data.get("image_url"):
            images = [card_data["image_url"]]
        conn.execute("""
            UPDATE listings SET
                title = ?, price = ?, price_text = ?, bedrooms = ?, bathrooms = ?,
                area_size = ?, location = ?, image_url = ?, images_json = ?,
                property_type = ?, added_text = ?, area_name = ?, area_slug = ?,
                latitude = ?, longitude = ?,
                card_scraped_at = ?, last_seen_at = ?, content_hash = ?, is_active = 1
            WHERE zameen_id = ?
        """, (
            card_data.get("title"), card_data.get("price"),
            card_data.get("price_text"), card_data.get("bedrooms"),
            card_data.get("bathrooms"), card_data.get("area_size"),
            card_data.get("location"), card_data.get("image_url"),
            json.dumps(images) if images else None,
            card_data.get("property_type"), card_data.get("added"),
            area_name, area_slug, lat, lng, now, now, c_hash, zameen_id
        ))
        conn.commit()
        return "updated"

    if detail_data and existing:
        d_hash = detail_hash(detail_data.get("phone"), detail_data.get("description"))
        if existing["detail_hash"] == d_hash:
            return "unchanged"

        features = detail_data.get("features", [])
        amenities = detail_data.get("amenities", [])
        details = detail_data.get("details", {})
        detail_images = detail_data.get("images", [])

        conn.execute("""
            UPDATE listings SET
                phone = ?, description = ?, features_json = ?, amenities_json = ?,
                details_json = ?, agent_name = ?, agent_agency = ?,
                detail_images_json = ?, detail_scraped_at = ?, detail_hash = ?
            WHERE zameen_id = ?
        """, (
            detail_data.get("phone"), detail_data.get("description"),
            json.dumps(features) if features else None,
            json.dumps(amenities) if amenities else None,
            json.dumps(details) if details else None,
            detail_data.get("agent_name"), detail_data.get("agent_agency"),
            json.dumps(detail_images) if detail_images else None,
            now, d_hash, zameen_id
        ))
        conn.commit()
        return "updated"

    return "unchanged"


def search_listings(*, city="karachi", area=None, property_type=None,
                    bedrooms=None, price_min=None, price_max=None,
                    furnished=None, sort=None, q=None, page=1, per_page=25):
    """Search listings from local DB. Returns dict matching current API shape."""
    conn = _get_conn()
    conditions = ["is_active = 1", "city = ?"]
    params = [city]

    if area:
        conditions.append("area_name = ?")
        params.append(area)
    if property_type:
        info = PROPERTY_TYPES.get(property_type.lower())
        if info:
            conditions.append("property_type = ?")
            params.append(info["label"])
    if bedrooms:
        conditions.append("bedrooms = ?")
        params.append(bedrooms)
    if price_min:
        conditions.append("price >= ?")
        params.append(price_min)
    if price_max:
        conditions.append("price <= ?")
        params.append(price_max)
    if furnished:
        conditions.append("(amenities_json LIKE '%furnished%' OR details_json LIKE '%furnished%')")
    if q:
        conditions.append("id IN (SELECT rowid FROM listings_fts WHERE listings_fts MATCH ?)")
        params.append(q)

    where = " AND ".join(conditions)

    order = "last_seen_at DESC"
    if sort == "price_low":
        order = "price ASC NULLS LAST"
    elif sort == "price_high":
        order = "price DESC NULLS LAST"
    elif sort == "newest":
        order = "first_seen_at DESC"

    total = conn.execute(f"SELECT COUNT(*) FROM listings WHERE {where}", params).fetchone()[0]

    offset = (page - 1) * per_page
    rows = conn.execute(
        f"SELECT * FROM listings WHERE {where} ORDER BY {order} LIMIT ? OFFSET ?",
        params + [per_page, offset]
    ).fetchall()

    results = [_row_to_listing(r) for r in rows]
    return {"total": total, "page": page, "per_page": per_page, "results": results}


def _row_to_listing(row):
    """Convert a DB row to the JSON shape the frontend expects."""
    d = {
        "title": row["title"],
        "url": row["url"],
        "price": row["price"],
        "price_text": row["price_text"],
        "bedrooms": row["bedrooms"],
        "bathrooms": row["bathrooms"],
        "area_size": row["area_size"],
        "location": row["location"],
        "image_url": row["image_url"],
        "property_type": row["property_type"],
        "added": row["added_text"],
    }
    if row["images_json"]:
        try:
            imgs = json.loads(row["images_json"])
            if len(imgs) > 1:
                d["images"] = imgs
        except (json.JSONDecodeError, TypeError):
            pass
    # Include detail fields if available
    if row["phone"]:
        d["phone"] = row["phone"]
    if row["description"]:
        d["description"] = row["description"]
    if row["features_json"]:
        try:
            d["features"] = json.loads(row["features_json"])
        except (json.JSONDecodeError, TypeError):
            pass
    if row["amenities_json"]:
        try:
            d["amenities"] = json.loads(row["amenities_json"])
        except (json.JSONDecodeError, TypeError):
            pass
    if row["agent_name"]:
        d["agent_name"] = row["agent_name"]
    if row["agent_agency"]:
        d["agent_agency"] = row["agent_agency"]
    return d


def get_listing_by_zameen_id(zameen_id):
    """Get a single listing by its Zameen.com ID."""
    conn = _get_conn()
    row = conn.execute("SELECT * FROM listings WHERE zameen_id = ?", (zameen_id,)).fetchone()
    return dict(row) if row else None


def get_listings_needing_detail(limit=10):
    """Get listings that need detail page scraping (never scraped or stale)."""
    conn = _get_conn()
    rows = conn.execute("""
        SELECT zameen_id, url FROM listings
        WHERE is_active = 1 AND (
            detail_scraped_at IS NULL
            OR detail_scraped_at < datetime('now', '-7 days')
            OR (card_scraped_at > detail_scraped_at)
        )
        ORDER BY detail_scraped_at ASC NULLS FIRST
        LIMIT ?
    """, (limit,)).fetchall()
    return [dict(r) for r in rows]


def mark_stale_listings(days=7):
    """Mark listings not seen in N days as inactive."""
    conn = _get_conn()
    result = conn.execute(
        "UPDATE listings SET is_active = 0 WHERE is_active = 1 AND last_seen_at < datetime('now', ?)",
        (f'-{days} days',)
    )
    conn.commit()
    count = result.rowcount
    if count:
        logger.info("Marked %d listings as inactive (not seen in %d days)", count, days)
    return count


def get_crawl_stats(city=None):
    """Get crawl statistics for the status endpoint."""
    conn = _get_conn()
    if city:
        total = conn.execute("SELECT COUNT(*) FROM listings WHERE is_active = 1 AND city = ?", (city,)).fetchone()[0]
        with_detail = conn.execute("SELECT COUNT(*) FROM listings WHERE is_active = 1 AND city = ? AND detail_scraped_at IS NOT NULL", (city,)).fetchone()[0]
        areas_crawled = conn.execute("SELECT COUNT(*) FROM crawl_state WHERE city = ? AND last_crawl_at IS NOT NULL", (city,)).fetchone()[0]
        areas_total = conn.execute("SELECT COUNT(*) FROM crawl_state WHERE city = ?", (city,)).fetchone()[0]
        last_crawl = conn.execute("SELECT MAX(last_crawl_at) FROM crawl_state WHERE city = ?", (city,)).fetchone()[0]
    else:
        total = conn.execute("SELECT COUNT(*) FROM listings WHERE is_active = 1").fetchone()[0]
        with_detail = conn.execute("SELECT COUNT(*) FROM listings WHERE is_active = 1 AND detail_scraped_at IS NOT NULL").fetchone()[0]
        areas_crawled = conn.execute("SELECT COUNT(*) FROM crawl_state WHERE last_crawl_at IS NOT NULL").fetchone()[0]
        areas_total = conn.execute("SELECT COUNT(*) FROM crawl_state").fetchone()[0]
        last_crawl = conn.execute("SELECT MAX(last_crawl_at) FROM crawl_state").fetchone()[0]

    return {
        "total_listings": total,
        "detail_coverage": round(with_detail / total * 100, 1) if total else 0,
        "areas_crawled": areas_crawled,
        "areas_total": areas_total,
        "last_crawl_at": last_crawl,
    }
