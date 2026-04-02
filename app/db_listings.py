"""Listing CRUD operations and local search queries."""
import hashlib, json, logging, math
from datetime import datetime

from app.database import _get_conn
from app.data import PROPERTY_TYPES

logger = logging.getLogger("zameenrentals")


def _listing_filter_clauses(*, city="karachi", area=None, area_names=None, property_type=None,
                            bedrooms=None, price_min=None, price_max=None,
                            furnished=None, q=None, exact_only=False, geocoded_only=False):
    conditions = ["is_active = 1", "city = ?"]
    params = [city]

    if exact_only:
        conditions.append("location_source = 'listing_exact'")
    if geocoded_only:
        conditions.append("latitude IS NOT NULL AND longitude IS NOT NULL")

    if area_names:
        placeholders = ",".join("?" for _ in area_names)
        conditions.append(f"area_name IN ({placeholders})")
        params.extend(area_names)
    elif area:
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

    return conditions, params


def _bounding_box(lat, lng, radius_km):
    radius_km = max(radius_km, 0.001)
    lat_delta = radius_km / 111.0
    cos_lat = max(math.cos(math.radians(lat)), 0.01)
    lng_delta = radius_km / (111.320 * cos_lat)
    return (
        lat - lat_delta,
        lat + lat_delta,
        lng - lng_delta,
        lng + lng_delta,
    )


def _haversine_km(lat1, lng1, lat2, lng2):
    lat1, lng1, lat2, lng2 = map(math.radians, [lat1, lng1, lat2, lng2])
    dlat = lat2 - lat1
    dlng = lng2 - lng1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    return 6371.0 * (2 * math.asin(math.sqrt(a)))


def _center_distance_expr(center_lat, center_lng, *, require_coordinates=True):
    lng_weight = max(math.cos(math.radians(center_lat)), 0.01) ** 2
    base_expr = """
        ((latitude - ?) * (latitude - ?)
         + ((longitude - ?) * (longitude - ?)) * ?)
    """
    params = [center_lat, center_lat, center_lng, center_lng, lng_weight]
    if not require_coordinates:
        return base_expr, params
    return f"""
        CASE
            WHEN latitude IS NOT NULL AND longitude IS NOT NULL THEN {base_expr}
            ELSE 999999999
        END
    """, params


def _datetime_sort_value(value):
    if not value:
        return 0.0
    try:
        return datetime.fromisoformat(value).timestamp()
    except ValueError:
        return 0.0


def _nearby_sort_key(row, sort):
    distance_km = row["_distance_km"]
    price = row["price"]
    first_seen_at = _datetime_sort_value(row["first_seen_at"])
    last_seen_at = _datetime_sort_value(row["last_seen_at"])

    if sort == "price_low":
        return (price is None, price if price is not None else float("inf"), distance_km, -last_seen_at)
    if sort == "price_high":
        return (price is None, -(price if price is not None else 0), distance_km, -last_seen_at)
    if sort == "newest":
        return (-first_seen_at, distance_km, -last_seen_at)
    return (distance_km, -last_seen_at)


def content_hash(price, title, bedrooms, bathrooms, area_size):
    """Hash card-level fields to detect changes."""
    raw = f"{price}|{title}|{bedrooms}|{bathrooms}|{area_size}"
    return hashlib.md5(raw.encode()).hexdigest()


def detail_hash(phone, description, whatsapp_phone=None, latitude=None, longitude=None, location_source=None):
    """Hash detail-level fields to detect changes."""
    raw = f"{phone}|{whatsapp_phone}|{description}|{latitude}|{longitude}|{location_source}"
    return hashlib.md5(raw.encode()).hexdigest()


def _json_value(data, key, existing_json):
    if key not in data:
        return existing_json
    value = data.get(key)
    return json.dumps(value) if value else None


def _value_or_existing(data, key, existing_value):
    if key in data and data.get(key) is not None:
        return data.get(key)
    return existing_value


def upsert_listing(*, zameen_id, url, city, area_name=None, area_slug=None,
                   lat=None, lng=None, card_data=None, detail_data=None):
    """Insert or update a listing. Returns 'inserted', 'updated', or 'unchanged'."""
    conn = _get_conn()
    now = datetime.utcnow().isoformat()

    existing = conn.execute(
        "SELECT * FROM listings WHERE zameen_id = ?",
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
            location_source = "area_centroid" if lat is not None and lng is not None else None
            conn.execute("""
                INSERT INTO listings (
                    zameen_id, url, title, price, price_text, bedrooms, bathrooms,
                    area_size, location, image_url, images_json, property_type,
                    added_text, city, area_name, area_slug, latitude, longitude, location_source,
                    card_scraped_at, last_seen_at, content_hash, is_active
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            """, (
                zameen_id, url, card_data.get("title"), card_data.get("price"),
                card_data.get("price_text"), card_data.get("bedrooms"),
                card_data.get("bathrooms"), card_data.get("area_size"),
                card_data.get("location"), card_data.get("image_url"),
                json.dumps(images) if images else None,
                card_data.get("property_type"), card_data.get("added"),
                city, area_name, area_slug, lat, lng, location_source, now, now, c_hash
            ))
            conn.commit()
            return "inserted"

        if existing["content_hash"] == c_hash:
            next_lat = existing["latitude"]
            next_lng = existing["longitude"]
            next_location_source = existing["location_source"]
            if existing["location_source"] != "listing_exact" and lat is not None and lng is not None:
                next_lat = lat
                next_lng = lng
                next_location_source = "area_centroid"
            conn.execute("""
                UPDATE listings SET
                    area_name = COALESCE(?, area_name),
                    area_slug = COALESCE(?, area_slug),
                    latitude = ?, longitude = ?, location_source = ?,
                    last_seen_at = ?, is_active = 1
                WHERE zameen_id = ?
            """, (area_name, area_slug, next_lat, next_lng, next_location_source, now, zameen_id))
            conn.commit()
            return "unchanged"

        # Card data changed
        images = card_data.get("images", [])
        if not images and card_data.get("image_url"):
            images = [card_data["image_url"]]
        next_lat = existing["latitude"]
        next_lng = existing["longitude"]
        next_location_source = existing["location_source"]
        if existing["location_source"] != "listing_exact" and lat is not None and lng is not None:
            next_lat = lat
            next_lng = lng
            next_location_source = "area_centroid"
        conn.execute("""
            UPDATE listings SET
                title = ?, price = ?, price_text = ?, bedrooms = ?, bathrooms = ?,
                area_size = ?, location = ?, image_url = ?, images_json = ?,
                property_type = ?, added_text = ?, area_name = ?, area_slug = ?,
                latitude = ?, longitude = ?, location_source = ?,
                card_scraped_at = ?, last_seen_at = ?, content_hash = ?, is_active = 1
            WHERE zameen_id = ?
        """, (
            card_data.get("title"), card_data.get("price"),
            card_data.get("price_text"), card_data.get("bedrooms"),
            card_data.get("bathrooms"), card_data.get("area_size"),
            card_data.get("location"), card_data.get("image_url"),
            json.dumps(images) if images else None,
            card_data.get("property_type"), card_data.get("added"),
            area_name, area_slug, next_lat, next_lng, next_location_source, now, now, c_hash, zameen_id
        ))
        conn.commit()
        return "updated"

    if detail_data and existing:
        call_phone = (
            detail_data.get("call_phone")
            or detail_data.get("phone")
            or existing["call_phone"]
            or existing["phone"]
        )
        if "whatsapp_phone" in detail_data:
            whatsapp_phone = detail_data.get("whatsapp_phone")
        else:
            whatsapp_phone = existing["whatsapp_phone"]
        description = _value_or_existing(detail_data, "description", existing["description"])
        features_json = _json_value(detail_data, "features", existing["features_json"])
        amenities_json = _json_value(detail_data, "amenities", existing["amenities_json"])
        details_json = _json_value(detail_data, "details", existing["details_json"])
        detail_images_json = _json_value(detail_data, "images", existing["detail_images_json"])
        agent_name = _value_or_existing(detail_data, "agent_name", existing["agent_name"])
        agent_agency = _value_or_existing(detail_data, "agent_agency", existing["agent_agency"])

        contact_payload_json = existing["contact_payload_json"]
        if "contact_payload" in detail_data:
            contact_payload = detail_data.get("contact_payload")
            contact_payload_json = json.dumps(contact_payload) if contact_payload else None

        contact_source = _value_or_existing(detail_data, "contact_source", existing["contact_source"])
        contact_requested = any(
            key in detail_data
            for key in ("phone", "call_phone", "whatsapp_phone", "contact_payload", "contact_source")
        )
        contact_fetched_at = (
            now if contact_requested and (call_phone or whatsapp_phone or contact_payload_json or contact_source)
            else existing["contact_fetched_at"]
        )

        latitude = existing["latitude"]
        longitude = existing["longitude"]
        location_source = existing["location_source"]
        if detail_data.get("latitude") is not None and detail_data.get("longitude") is not None:
            latitude = detail_data.get("latitude")
            longitude = detail_data.get("longitude")
            location_source = detail_data.get("location_source") or "listing_exact"

        detail_requested = any(
            key in detail_data
            for key in ("description", "features", "amenities", "details", "agent_name", "agent_agency", "images", "latitude", "longitude", "location_source")
        )
        detail_scraped_at = now if detail_requested else existing["detail_scraped_at"]
        d_hash = detail_hash(call_phone, description, whatsapp_phone, latitude, longitude, location_source)

        if (
            existing["phone"] == call_phone
            and existing["call_phone"] == call_phone
            and existing["whatsapp_phone"] == whatsapp_phone
            and existing["contact_payload_json"] == contact_payload_json
            and existing["contact_fetched_at"] == contact_fetched_at
            and existing["contact_source"] == contact_source
            and existing["description"] == description
            and existing["features_json"] == features_json
            and existing["amenities_json"] == amenities_json
            and existing["details_json"] == details_json
            and existing["agent_name"] == agent_name
            and existing["agent_agency"] == agent_agency
            and existing["detail_images_json"] == detail_images_json
            and existing["latitude"] == latitude
            and existing["longitude"] == longitude
            and existing["location_source"] == location_source
            and existing["detail_scraped_at"] == detail_scraped_at
            and existing["detail_hash"] == d_hash
        ):
            return "unchanged"

        conn.execute("""
            UPDATE listings SET
                phone = ?, call_phone = ?, whatsapp_phone = ?,
                contact_payload_json = ?, contact_fetched_at = ?, contact_source = ?,
                description = ?, features_json = ?, amenities_json = ?,
                details_json = ?, agent_name = ?, agent_agency = ?,
                detail_images_json = ?, latitude = ?, longitude = ?, location_source = ?,
                detail_scraped_at = ?, detail_hash = ?
            WHERE zameen_id = ?
        """, (
            call_phone, call_phone, whatsapp_phone,
            contact_payload_json, contact_fetched_at, contact_source,
            description, features_json, amenities_json, details_json,
            agent_name, agent_agency, detail_images_json,
            latitude, longitude, location_source,
            detail_scraped_at, d_hash, zameen_id
        ))
        conn.commit()
        return "updated"

    return "unchanged"


def search_listings(*, city="karachi", area=None, area_names=None, property_type=None,
                    bedrooms=None, price_min=None, price_max=None,
                    furnished=None, sort=None, q=None, page=1, per_page=25,
                    center_lat=None, center_lng=None):
    """Search listings from local DB. Returns dict matching current API shape."""
    conn = _get_conn()
    conditions, params = _listing_filter_clauses(
        city=city, area=area, area_names=area_names, property_type=property_type,
        bedrooms=bedrooms, price_min=price_min, price_max=price_max,
        furnished=furnished, q=q,
    )
    where = " AND ".join(conditions)

    map_focus = center_lat is not None and center_lng is not None
    distance_expr, distance_params = (
        _center_distance_expr(center_lat, center_lng)
        if map_focus
        else ("NULL", [])
    )

    if sort == "price_low":
        order = "price ASC NULLS LAST"
    elif sort == "price_high":
        order = "price DESC NULLS LAST"
    elif sort == "newest":
        order = "first_seen_at DESC"
    elif map_focus:
        order = "distance_to_center ASC, CASE WHEN location_source = 'listing_exact' THEN 0 ELSE 1 END ASC, last_seen_at DESC"
    else:
        order = "last_seen_at DESC"

    if map_focus and sort in {"price_low", "price_high", "newest"}:
        order = f"{order}, distance_to_center ASC, CASE WHEN location_source = 'listing_exact' THEN 0 ELSE 1 END ASC"

    total = conn.execute(f"SELECT COUNT(*) FROM listings WHERE {where}", params).fetchone()[0]

    offset = (page - 1) * per_page
    query_params = distance_params + params + [per_page, offset]
    rows = conn.execute(
        f"SELECT *, {distance_expr} AS distance_to_center FROM listings WHERE {where} ORDER BY {order} LIMIT ? OFFSET ?",
        query_params
    ).fetchall()

    results = [_row_to_listing(r) for r in rows]
    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "results": results,
        "ranking": "map_focus" if map_focus else "default",
    }


def count_listings_by_area(*, city="karachi", area_names=None, property_type=None,
                           bedrooms=None, price_min=None, price_max=None,
                           furnished=None, q=None):
    """Return listing counts grouped by area for the current filter set."""
    conn = _get_conn()
    conditions, params = _listing_filter_clauses(
        city=city, area_names=area_names, property_type=property_type,
        bedrooms=bedrooms, price_min=price_min, price_max=price_max,
        furnished=furnished, q=q,
    )
    where = " AND ".join(conditions)
    rows = conn.execute(
        f"""
        SELECT area_name, COUNT(*) AS total
        FROM listings
        WHERE {where} AND area_name IS NOT NULL
        GROUP BY area_name
        ORDER BY total DESC, area_name ASC
        """,
        params,
    ).fetchall()
    return {row["area_name"]: row["total"] for row in rows}


def search_nearby_listings(*, city="karachi", lat, lng, radius_km=5,
                           area=None, property_type=None, bedrooms=None,
                           price_min=None, price_max=None, furnished=None,
                           sort=None, q=None, page=1, per_page=25):
    """Search nearby listings using exact coordinates only."""
    conn = _get_conn()
    conditions, params = _listing_filter_clauses(
        city=city, area=area, property_type=property_type,
        bedrooms=bedrooms, price_min=price_min, price_max=price_max,
        furnished=furnished, q=q, exact_only=True, geocoded_only=True,
    )
    south, north, west, east = _bounding_box(lat, lng, radius_km)
    conditions.extend([
        "latitude BETWEEN ? AND ?",
        "longitude BETWEEN ? AND ?",
    ])
    params.extend([south, north, west, east])
    where = " AND ".join(conditions)

    rows = conn.execute(
        f"SELECT * FROM listings WHERE {where}",
        params,
    ).fetchall()

    nearby_rows = []
    for row in rows:
        distance_km = _haversine_km(lat, lng, row["latitude"], row["longitude"])
        if distance_km > radius_km:
            continue
        row_data = dict(row)
        row_data["_distance_km"] = distance_km
        nearby_rows.append(row_data)

    nearby_rows.sort(key=lambda row: _nearby_sort_key(row, sort))
    total = len(nearby_rows)
    offset = (page - 1) * per_page
    paginated_rows = nearby_rows[offset:offset + per_page]

    results = []
    for row in paginated_rows:
        row["distance_km"] = row["_distance_km"]
        row["distance_source"] = "listing_exact"
        row["is_distance_approximate"] = False
        results.append(_row_to_listing(row))

    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "results": results,
        "ranking": "nearby_distance" if sort not in {"price_low", "price_high", "newest"} else "nearby_sort",
    }


def search_exact_listings_in_bounds(*, city="karachi", south, west, north, east,
                                    property_type=None, bedrooms=None,
                                    price_min=None, price_max=None,
                                    furnished=None, sort=None, q=None,
                                    page=1, per_page=25, center_lat=None,
                                    center_lng=None):
    """Search exact-coordinate listings currently inside the viewport bounds."""
    conn = _get_conn()
    conditions, params = _listing_filter_clauses(
        city=city, property_type=property_type,
        bedrooms=bedrooms, price_min=price_min, price_max=price_max,
        furnished=furnished, q=q, exact_only=True, geocoded_only=True,
    )
    conditions.extend([
        "latitude BETWEEN ? AND ?",
        "longitude BETWEEN ? AND ?",
    ])
    params.extend([south, north, west, east])
    where = " AND ".join(conditions)

    map_focus = center_lat is not None and center_lng is not None
    distance_expr, distance_params = (
        _center_distance_expr(center_lat, center_lng, require_coordinates=False)
        if map_focus
        else ("NULL", [])
    )

    if sort == "price_low":
        order = "price ASC NULLS LAST"
    elif sort == "price_high":
        order = "price DESC NULLS LAST"
    elif sort == "newest":
        order = "first_seen_at DESC"
    elif map_focus:
        order = "distance_to_center ASC, last_seen_at DESC"
    else:
        order = "last_seen_at DESC"

    if sort in {"price_low", "price_high", "newest"}:
        if map_focus:
            order = f"{order}, distance_to_center ASC"
        order = f"{order}, last_seen_at DESC"

    total = conn.execute(
        f"SELECT COUNT(*) FROM listings WHERE {where}",
        params,
    ).fetchone()[0]
    offset = (page - 1) * per_page
    rows = conn.execute(
        f"SELECT *, {distance_expr} AS distance_to_center FROM listings WHERE {where} ORDER BY {order} LIMIT ? OFFSET ?",
        distance_params + params + [per_page, offset],
    ).fetchall()

    area_rows = conn.execute(
        f"""
        SELECT area_name, COUNT(*) AS total
        FROM listings
        WHERE {where} AND area_name IS NOT NULL
        GROUP BY area_name
        ORDER BY total DESC, area_name ASC
        """,
        params,
    ).fetchall()
    area_totals = {row["area_name"]: row["total"] for row in area_rows}

    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "results": [_row_to_listing(row) for row in rows],
        "ranking": "map_focus" if map_focus else "default",
        "area_totals": area_totals,
    }


def get_nearby_enrichment_candidates(*, city="karachi", lat, lng, radius_km=5,
                                     area=None, property_type=None, bedrooms=None,
                                     price_min=None, price_max=None, furnished=None,
                                     q=None, limit=12):
    """Return centroid-backed candidates worth upgrading to exact coordinates."""
    conn = _get_conn()
    conditions, params = _listing_filter_clauses(
        city=city, area=area, property_type=property_type,
        bedrooms=bedrooms, price_min=price_min, price_max=price_max,
        furnished=furnished, q=q, geocoded_only=True,
    )
    conditions.append("location_source IS NOT NULL")
    conditions.append("location_source != 'listing_exact'")
    south, north, west, east = _bounding_box(lat, lng, radius_km)
    conditions.extend([
        "latitude BETWEEN ? AND ?",
        "longitude BETWEEN ? AND ?",
    ])
    params.extend([south, north, west, east])
    where = " AND ".join(conditions)

    rows = conn.execute(
        f"SELECT zameen_id, url, city, latitude, longitude FROM listings WHERE {where}",
        params,
    ).fetchall()
    candidates = []
    for row in rows:
        distance_km = _haversine_km(lat, lng, row["latitude"], row["longitude"])
        if distance_km > radius_km:
            continue
        candidates.append({
            "zameen_id": row["zameen_id"],
            "url": row["url"],
            "city": row["city"],
            "distance_km": distance_km,
        })
    candidates.sort(key=lambda row: row["distance_km"])
    return candidates[:limit]


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
        d["phone"] = row["call_phone"] or row["phone"]
    if row["call_phone"]:
        d["call_phone"] = row["call_phone"]
    elif row["phone"]:
        d["call_phone"] = row["phone"]
    if row["whatsapp_phone"]:
        d["whatsapp_phone"] = row["whatsapp_phone"]
    if row["latitude"] is not None and row["longitude"] is not None:
        d["latitude"] = row["latitude"]
        d["longitude"] = row["longitude"]
        d["location_source"] = row["location_source"] or "area_centroid"
    d["has_exact_geography"] = row["location_source"] == "listing_exact"
    if "distance_to_center" in row.keys() and row["distance_to_center"] is not None:
        d["distance_to_center"] = row["distance_to_center"]
    if "distance_km" in row.keys() and row["distance_km"] is not None:
        d["distance_km"] = row["distance_km"]
    if "distance_source" in row.keys() and row["distance_source"] is not None:
        d["distance_source"] = row["distance_source"]
    if "is_distance_approximate" in row.keys():
        d["is_distance_approximate"] = bool(row["is_distance_approximate"])
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
            OR location_source IS NULL
            OR location_source != 'listing_exact'
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
