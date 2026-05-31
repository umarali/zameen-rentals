"""API route handlers."""
import asyncio
import hmac
import logging
import os
import time
from threading import Lock as _Lock
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse

from app.data import KARACHI_AREAS, PROPERTY_TYPES, CITIES, CITY_AREAS, get_areas, _ENGLISH_TO_URDU
from app.cache import limiter
from app.database import log_search, get_popular_searches, get_recent_searches, save_feedback
from app.parsing import parse_query_with_claude
from app.parsing import parse_natural_query
from app.scraper import search_zameen, fetch_listing_contact, fetch_listing_detail, extract_zameen_id
from app.db_listings import (
    decode_listing_json_field,
    search_listings, count_listings_by_area, get_listing_by_zameen_id,
    get_crawl_stats, get_nearby_enrichment_candidates, search_exact_listings_in_bounds,
    search_nearby_listings,
    upsert_listing,
)

logger = logging.getLogger("zameenrentals")
router = APIRouter()

# In-memory cache for the default city-browse query (no filters, page=1).
# Keyed by city. TTL=30s. 3 entries max (one per city). Zero memory growth risk.
_DEFAULT_SEARCH_CACHE: dict = {}
_DEFAULT_SEARCH_LOCK = _Lock()
_DEFAULT_SEARCH_TTL = 30


def _is_default_search(area, property_type, bedrooms, bedrooms_max,
                       price_min, price_max, size_marla_min, size_marla_max,
                       furnished, sort, page) -> bool:
    return (area is None and property_type is None and bedrooms is None
            and bedrooms_max is None and price_min is None and price_max is None
            and size_marla_min is None and size_marla_max is None
            and furnished is None and sort is None and page == 1)


_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_MAX_VIEWPORT_AREAS = 500
_NEARBY_SUPPORTED_CITIES = {"karachi", "lahore", "islamabad"}
_NEARBY_ENRICHMENT_LIMIT = 12
_NEARBY_ENRICHMENT_CONCURRENCY = 3
_PARSE_QUERY_TIMEOUT_SECONDS = 8
_PLAYWRIGHT_SERVER = os.getenv("ZAMEENRENTALS_PLAYWRIGHT") == "1"
_SEARCH_RATE_LIMIT = "10000/minute" if _PLAYWRIGHT_SERVER else "10/minute"
_MAP_SEARCH_RATE_LIMIT = "10000/minute" if _PLAYWRIGHT_SERVER else "20/minute"
_NEARBY_SEARCH_RATE_LIMIT = "10000/minute" if _PLAYWRIGHT_SERVER else "10/minute"
_PARSE_QUERY_RATE_LIMIT = "10000/minute" if _PLAYWRIGHT_SERVER else "15/minute"
_LISTING_DETAIL_RATE_LIMIT = "10000/minute" if _PLAYWRIGHT_SERVER else "20/minute"


def _require_admin_token(request: Request):
    configured = os.getenv("ZAMEENRENTALS_ADMIN_TOKEN", "")
    supplied = request.headers.get("X-Admin-Token", "")
    if not configured:
        raise HTTPException(status_code=503, detail="Admin endpoint is not configured")
    if not supplied or not hmac.compare_digest(supplied, configured):
        raise HTTPException(status_code=401, detail="Invalid admin token")


def _normalize_area_names(areas, *, limit=_MAX_VIEWPORT_AREAS):
    names, seen = [], set()
    for area in areas:
        name = (area or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        names.append(name)
        if len(names) > limit:
            raise HTTPException(status_code=400, detail=f"Too many areas. Maximum is {limit}.")
    return names


def _contact_response_from_listing(listing):
    phone = listing.get("phone") or listing.get("call_phone")
    call_phone = listing.get("call_phone") or listing.get("phone")
    return {
        "phone": phone,
        "call_phone": call_phone,
        "whatsapp_phone": listing.get("whatsapp_phone"),
        "agent_agency": listing.get("agent_agency"),
        "source": "local",
    }


def _validate_nearby_request(city, lat, lng, radius_km):
    if city not in _NEARBY_SUPPORTED_CITIES:
        raise HTTPException(status_code=400, detail="Nearby search is not available for this city.")
    if not (-90 <= lat <= 90):
        raise HTTPException(status_code=400, detail="Latitude must be between -90 and 90.")
    if not (-180 <= lng <= 180):
        raise HTTPException(status_code=400, detail="Longitude must be between -180 and 180.")
    if not (1 <= radius_km <= 20):
        raise HTTPException(status_code=400, detail="Radius must be between 1 and 20 km.")


def _validate_price_range(price_min, price_max):
    if (
        price_min is not None
        and price_max is not None
        and price_min > price_max
    ):
        raise HTTPException(status_code=400, detail="price_min must be less than or equal to price_max.")


def _validate_viewport_bounds(south, west, north, east):
    provided = [south, west, north, east]
    if all(value is None for value in provided):
        return False
    if any(value is None for value in provided):
        raise HTTPException(status_code=400, detail="south, west, north, and east are required together.")
    if south >= north:
        raise HTTPException(status_code=400, detail="south must be less than north.")
    if west >= east:
        raise HTTPException(status_code=400, detail="west must be less than east.")
    return True


def _build_parse_query_response(q, city, result):
    # Flag when the matched area differs from what the user typed
    areas = get_areas(city)
    if result.get("area") and result["area"] in areas:
        ql = q.lower()
        query_tokens = set(ql.replace("-", " ").split()) - {"in", "for", "rent", "rental", "ke", "ka", "ki", "mein", "me"}
        area_tokens = set(result["area"].lower().replace("-", " ").split())
        unmatched = query_tokens - area_tokens
        noise = {"house", "flat", "apartment", "portion", "upper", "lower", "room", "bed", "bedroom", "furnished", "full", "ghar", "makan", "bala", "nichla", "kamra"}
        unmatched -= noise
        unmatched = {t for t in unmatched if not t.isdigit()}
        if unmatched:
            result["area_approximate"] = True
            result["area_query"] = " ".join(unmatched)
    return {"query": q, "filters": result}


async def _refresh_exact_location_candidate(candidate):
    try:
        detail = await fetch_listing_detail(candidate["url"])
    except Exception:
        logger.exception("Nearby enrichment failed for %s", candidate["url"])
        return False

    if not detail:
        return False

    upsert_listing(
        zameen_id=candidate["zameen_id"],
        url=candidate["url"],
        city=candidate["city"],
        detail_data=detail,
    )
    return bool(detail.get("has_exact_geography"))


async def _maybe_enrich_nearby_exact_locations(*, city, lat, lng, radius_km, area,
                                               property_type, bedrooms, bedrooms_max=None,
                                               price_min, price_max,
                                               size_marla_min=None, size_marla_max=None,
                                               furnished, q=None):
    candidates = get_nearby_enrichment_candidates(
        city=city, lat=lat, lng=lng, radius_km=radius_km, area=area,
        property_type=property_type, bedrooms=bedrooms, bedrooms_max=bedrooms_max,
        price_min=price_min, price_max=price_max,
        size_marla_min=size_marla_min, size_marla_max=size_marla_max,
        furnished=furnished, q=q, limit=_NEARBY_ENRICHMENT_LIMIT,
    )
    if not candidates:
        return False

    semaphore = asyncio.Semaphore(_NEARBY_ENRICHMENT_CONCURRENCY)

    async def run(candidate):
        async with semaphore:
            return await _refresh_exact_location_candidate(candidate)

    results = await asyncio.gather(*(run(candidate) for candidate in candidates), return_exceptions=True)
    return any(result is True for result in results)


@router.get("/api/health")
async def health():
    return {"status": "ok", "service": "ZameenRentals", "version": "1.0.0"}


@router.get("/api/cities")
async def get_cities():
    return [{"key": k, "name": v["name"], "lat": v["lat"], "lng": v["lng"]} for k, v in CITIES.items()]


@router.get("/api/areas")
async def get_areas_api(city: str = Query("lahore")):
    areas = get_areas(city)
    urdu_map = _ENGLISH_TO_URDU if city == "karachi" else {}
    return [{"name": n, "slug": s, "id": i, "lat": lat, "lng": lng, "name_ur": urdu_map.get(n, "")} for n, (s, i, lat, lng) in sorted(areas.items())]


@router.get("/api/search-areas")
async def search_areas(q: str = Query(..., min_length=1), city: str = Query("lahore"), limit: int = Query(20, ge=1, le=50)):
    """Fuzzy search across all known areas for a city. Returns top matches."""
    areas = get_areas(city)
    ql = q.strip().lower()
    scored = []
    city_name = CITIES.get(city, CITIES["lahore"])["name"]
    for name, (slug, aid, lat, lng) in areas.items():
        if name == city_name:
            continue
        nl = name.lower()
        if nl == ql:
            scored.append((100, name))
            continue
        if nl.startswith(ql):
            scored.append((90, name))
            continue
        if ql in nl:
            scored.append((80 - len(name), name))
            continue
        if nl in ql:
            scored.append((70, name))
            continue
        qt = set(ql.split())
        nt = set(nl.split())
        overlap = len(qt & nt)
        if overlap > 0:
            scored.append((50 + overlap * 10, name))
            continue
        ratio = SequenceMatcher(None, ql, nl).ratio()
        if ratio >= 0.4:
            scored.append((int(ratio * 40), name))

    scored.sort(key=lambda x: -x[0])
    urdu_map = _ENGLISH_TO_URDU if city == "karachi" else {}
    results = []
    for _, name in scored[:limit]:
        s, i, lat, lng = areas[name]
        results.append({"name": name, "slug": s, "id": i, "lat": lat, "lng": lng, "name_ur": urdu_map.get(name, "")})
    return results


@router.get("/api/property-types")
async def get_property_types():
    seen, types = set(), []
    for key, info in PROPERTY_TYPES.items():
        if key == "flat": continue
        if info["slug"] not in seen: seen.add(info["slug"]); types.append({"key": key, "label": info["label"]})
    return types


@router.get("/api/parse-query")
@limiter.limit(_PARSE_QUERY_RATE_LIMIT)
async def api_parse_query(request: Request, q: str = Query(..., min_length=1), city: str = Query("lahore")):
    try:
        if _PLAYWRIGHT_SERVER:
            result = parse_natural_query(q, city=city)
        else:
            try:
                result = await asyncio.wait_for(
                    parse_query_with_claude(q, city=city),
                    timeout=_PARSE_QUERY_TIMEOUT_SECONDS,
                )
            except asyncio.TimeoutError:
                logger.warning(
                    "Parse query timed out after %ss, falling back to regex parser",
                    _PARSE_QUERY_TIMEOUT_SECONDS,
                )
                result = parse_natural_query(q, city=city)
        return _build_parse_query_response(q, city, result)
    except Exception:
        logger.exception("Parse query error")
        raise HTTPException(status_code=500, detail="Failed to parse query. Please try again.")


@router.get("/api/search")
@limiter.limit(_SEARCH_RATE_LIMIT)
async def search(request: Request, city: str = Query("lahore"), area: Optional[str]=Query(None), property_type: Optional[str]=Query(None), bedrooms: Optional[int]=Query(None, ge=1, le=10), bedrooms_max: Optional[int]=Query(None, ge=1, le=10), price_min: Optional[int]=Query(None, ge=0), price_max: Optional[int]=Query(None, ge=0), size_marla_min: Optional[float]=Query(None, ge=0), size_marla_max: Optional[float]=Query(None, ge=0), furnished: Optional[bool]=Query(None), page: int=Query(1, ge=1), sort: Optional[str]=Query(None)):
    try:
        _validate_price_range(price_min, price_max)
        # Serve from in-memory cache for the default (no-filter, page=1) query.
        # log_search is intentionally skipped on cache hits to avoid inflating search history counts.
        is_default = _is_default_search(area, property_type, bedrooms, bedrooms_max,
                                        price_min, price_max, size_marla_min, size_marla_max,
                                        furnished, sort, page)
        if is_default:
            with _DEFAULT_SEARCH_LOCK:
                cached = _DEFAULT_SEARCH_CACHE.get(city)
            if cached and cached[1] > time.monotonic():
                return {**cached[0], "source": "local"}

        # Try local DB first (instant results from crawler data)
        local_result = search_listings(
            city=city, area=area, property_type=property_type,
            bedrooms=bedrooms, bedrooms_max=bedrooms_max,
            price_min=price_min, price_max=price_max,
            size_marla_min=size_marla_min, size_marla_max=size_marla_max,
            furnished=furnished, sort=sort, page=page
        )
        if local_result["total"] > 0:
            local_result["source"] = "local"
            if is_default:
                with _DEFAULT_SEARCH_LOCK:
                    _DEFAULT_SEARCH_CACHE[city] = (local_result, time.monotonic() + _DEFAULT_SEARCH_TTL)
            log_search(city=city, area=area, property_type=property_type, bedrooms=bedrooms,
                       price_min=price_min, price_max=price_max, furnished=furnished,
                       sort=sort, result_count=local_result["total"])
            return local_result

        if _PLAYWRIGHT_SERVER:
            return {
                "total": 0,
                "page": page,
                "per_page": 25,
                "results": [],
                "source": "unavailable",
            }

        # Fallback to live scraping if local DB has no results for this query
        try:
            result = await search_zameen(area=area, property_type=property_type, bedrooms=bedrooms, bedrooms_max=bedrooms_max, price_min=price_min, price_max=price_max, furnished=furnished, page=page, sort=sort, city=city)
            result["source"] = "live"
            log_search(city=city, area=area, property_type=property_type, bedrooms=bedrooms,
                       price_min=price_min, price_max=price_max, furnished=furnished,
                       sort=sort, result_count=result.get("total", 0))
            return result
        except HTTPException as exc:
            if exc.status_code == 502:
                return {"total": 0, "page": page, "per_page": 25, "results": [], "source": "unavailable"}
            raise
    except HTTPException:
        raise
    except Exception:
        logger.exception("Search error")
        raise HTTPException(status_code=500, detail="An internal error occurred. Please try again later.")


@router.get("/api/map-search")
@limiter.limit(_MAP_SEARCH_RATE_LIMIT)
async def map_search(
    request: Request,
    city: str = Query("lahore"),
    areas: list[str] = Query([]),
    property_type: Optional[str] = Query(None),
    bedrooms: Optional[int] = Query(None, ge=1, le=10),
    bedrooms_max: Optional[int] = Query(None, ge=1, le=10),
    price_min: Optional[int] = Query(None, ge=0),
    price_max: Optional[int] = Query(None, ge=0),
    size_marla_min: Optional[float] = Query(None, ge=0),
    size_marla_max: Optional[float] = Query(None, ge=0),
    furnished: Optional[bool] = Query(None),
    page: int = Query(1, ge=1),
    sort: Optional[str] = Query(None),
    center_lat: Optional[float] = Query(None, ge=-90, le=90),
    center_lng: Optional[float] = Query(None, ge=-180, le=180),
    south: Optional[float] = Query(None, ge=-90, le=90),
    west: Optional[float] = Query(None, ge=-180, le=180),
    north: Optional[float] = Query(None, ge=-90, le=90),
    east: Optional[float] = Query(None, ge=-180, le=180),
):
    _validate_price_range(price_min, price_max)
    area_names = _normalize_area_names(areas)
    has_bounds = _validate_viewport_bounds(south, west, north, east)
    result = None
    exact_bounds_total = None

    if has_bounds:
        exact_result = search_exact_listings_in_bounds(
            city=city, south=south, west=west, north=north, east=east,
            property_type=property_type, bedrooms=bedrooms, bedrooms_max=bedrooms_max,
            price_min=price_min, price_max=price_max,
            size_marla_min=size_marla_min, size_marla_max=size_marla_max,
            furnished=furnished,
            sort=sort, page=page, center_lat=center_lat, center_lng=center_lng,
        )
        exact_bounds_total = exact_result["total"]
        if exact_result["total"] > 0 or not area_names:
            result = exact_result
            result["scope"] = "exact_bounds"
            result["visible_areas"] = max(len(area_names), len(result["area_totals"]))

    if result is None:
        if not area_names:
            return {
                "total": 0,
                "page": page,
                "per_page": 25,
                "results": [],
                "source": "local",
                "mode": "viewport",
                "scope": "area_coverage",
                "visible_areas": 0,
                "area_totals": {},
            }

        result = search_listings(
            city=city, area_names=area_names, property_type=property_type,
            bedrooms=bedrooms, bedrooms_max=bedrooms_max,
            price_min=price_min, price_max=price_max,
            size_marla_min=size_marla_min, size_marla_max=size_marla_max,
            furnished=furnished, sort=sort, page=page,
            center_lat=center_lat, center_lng=center_lng,
        )
        result["scope"] = "area_coverage"
        result["visible_areas"] = len(area_names)
        result["area_totals"] = count_listings_by_area(
            city=city, area_names=area_names, property_type=property_type,
            bedrooms=bedrooms, bedrooms_max=bedrooms_max,
            price_min=price_min, price_max=price_max,
            size_marla_min=size_marla_min, size_marla_max=size_marla_max,
            furnished=furnished,
        )

    if has_bounds:
        result["attempted_exact_bounds"] = True
        result["exact_bounds_total"] = exact_bounds_total or 0

    result["source"] = "local"
    result["mode"] = "viewport"
    result["focus_center"] = (
        {"lat": center_lat, "lng": center_lng}
        if center_lat is not None and center_lng is not None
        else None
    )
    return result


@router.get("/api/nearby-search")
@limiter.limit(_NEARBY_SEARCH_RATE_LIMIT)
async def nearby_search(
    request: Request,
    city: str = Query("lahore"),
    lat: float = Query(...),
    lng: float = Query(...),
    radius_km: float = Query(5),
    area: Optional[str] = Query(None),
    property_type: Optional[str] = Query(None),
    bedrooms: Optional[int] = Query(None, ge=1, le=10),
    bedrooms_max: Optional[int] = Query(None, ge=1, le=10),
    price_min: Optional[int] = Query(None, ge=0),
    price_max: Optional[int] = Query(None, ge=0),
    size_marla_min: Optional[float] = Query(None, ge=0),
    size_marla_max: Optional[float] = Query(None, ge=0),
    furnished: Optional[bool] = Query(None),
    page: int = Query(1, ge=1),
    sort: Optional[str] = Query(None),
):
    _validate_nearby_request(city, lat, lng, radius_km)
    _validate_price_range(price_min, price_max)

    result = search_nearby_listings(
        city=city, lat=lat, lng=lng, radius_km=radius_km, area=area,
        property_type=property_type, bedrooms=bedrooms, bedrooms_max=bedrooms_max,
        price_min=price_min, price_max=price_max,
        size_marla_min=size_marla_min, size_marla_max=size_marla_max,
        furnished=furnished, sort=sort, page=page,
    )

    if page == 1 and result["total"] < result["per_page"]:
        upgraded = await _maybe_enrich_nearby_exact_locations(
            city=city, lat=lat, lng=lng, radius_km=radius_km, area=area,
            property_type=property_type, bedrooms=bedrooms, bedrooms_max=bedrooms_max,
            price_min=price_min, price_max=price_max,
            size_marla_min=size_marla_min, size_marla_max=size_marla_max,
            furnished=furnished,
        )
        if upgraded:
            result = search_nearby_listings(
                city=city, lat=lat, lng=lng, radius_km=radius_km, area=area,
                property_type=property_type, bedrooms=bedrooms, bedrooms_max=bedrooms_max,
                price_min=price_min, price_max=price_max,
                size_marla_min=size_marla_min, size_marla_max=size_marla_max,
                furnished=furnished, sort=sort, page=page,
            )

    result["source"] = "local"
    result["mode"] = "nearby"
    result["radius_km"] = radius_km
    result["focus_center"] = {"lat": lat, "lng": lng}
    log_search(city=city, area=area, property_type=property_type, bedrooms=bedrooms,
               price_min=price_min, price_max=price_max, furnished=furnished,
               sort=sort, result_count=result["total"])
    return result


@router.get("/api/listing-detail")
@limiter.limit(_LISTING_DETAIL_RATE_LIMIT)
async def listing_detail(request: Request, url: str = Query(...)):
    """Fetch enriched detail — from local DB if available, else live scrape."""
    if not url.startswith("https://www.zameen.com/"):
        raise HTTPException(status_code=400, detail="Invalid Zameen.com URL")
    try:
        # Try local DB first
        zid = extract_zameen_id(url)
        listing = None
        local_detail = None
        if zid:
            listing = get_listing_by_zameen_id(zid)
            if listing and listing.get("detail_scraped_at"):
                local_detail = {
                    "phone": listing.get("phone") or listing.get("call_phone"),
                    "call_phone": listing.get("call_phone") or listing.get("phone"),
                    "whatsapp_phone": listing.get("whatsapp_phone"),
                    "description": listing.get("description"),
                    "features": decode_listing_json_field(
                        listing.get("features_json"),
                        field_name="features_json",
                        zameen_id=listing.get("zameen_id"),
                        default=[],
                        expected_type=list,
                    ),
                    "amenities": decode_listing_json_field(
                        listing.get("amenities_json"),
                        field_name="amenities_json",
                        zameen_id=listing.get("zameen_id"),
                        default=[],
                        expected_type=list,
                    ),
                    "details": decode_listing_json_field(
                        listing.get("details_json"),
                        field_name="details_json",
                        zameen_id=listing.get("zameen_id"),
                        default={},
                        expected_type=dict,
                    ),
                    "agent_name": listing.get("agent_name"),
                    "agent_agency": listing.get("agent_agency"),
                    "images": decode_listing_json_field(
                        listing.get("detail_images_json"),
                        field_name="detail_images_json",
                        zameen_id=listing.get("zameen_id"),
                        default=[],
                        expected_type=list,
                    ),
                    "latitude": listing.get("latitude"),
                    "longitude": listing.get("longitude"),
                    "location_source": listing.get("location_source"),
                    "has_exact_geography": listing.get("location_source") == "listing_exact",
                    "contact_source": listing.get("contact_source"),
                    "source": "local",
                }
                if local_detail["has_exact_geography"]:
                    return local_detail
        if _PLAYWRIGHT_SERVER:
            return local_detail or {}
        # Fallback to live scrape
        detail = await fetch_listing_detail(url)
        if detail and zid and listing:
            upsert_listing(
                zameen_id=zid,
                url=url,
                city=listing.get("city") or "",
                detail_data=detail,
            )
            detail["source"] = "live"
        return detail or local_detail or {}
    except Exception:
        logger.exception("Detail fetch error")
        return {}


@router.get("/api/listing-contact")
@limiter.limit(_LISTING_DETAIL_RATE_LIMIT)
async def listing_contact(request: Request, url: str = Query(...)):
    """Fetch contact data — from local DB if available, else live via showNumbers."""
    if not url.startswith("https://www.zameen.com/"):
        raise HTTPException(status_code=400, detail="Invalid Zameen.com URL")
    try:
        zid = extract_zameen_id(url)
        listing = None
        if zid:
            listing = get_listing_by_zameen_id(zid)
            if listing and (listing.get("call_phone") or listing.get("phone") or listing.get("whatsapp_phone")):
                return _contact_response_from_listing(listing)
        if _PLAYWRIGHT_SERVER:
            return {"phone": None, "call_phone": None, "whatsapp_phone": None}
        contact = await fetch_listing_contact(url)
        if not contact:
            return {"phone": None, "call_phone": None, "whatsapp_phone": None}
        if zid and listing:
            upsert_listing(
                zameen_id=zid, url=url, city=listing.get("city") or "",
                detail_data={
                    "phone": contact.get("phone"),
                    "call_phone": contact.get("call_phone"),
                    "whatsapp_phone": contact.get("whatsapp_phone"),
                    "agent_agency": contact.get("agent_agency"),
                    "contact_payload": contact.get("contact_payload"),
                    "contact_source": contact.get("contact_source"),
                },
            )
        return {
            "phone": contact.get("phone"),
            "call_phone": contact.get("call_phone"),
            "whatsapp_phone": contact.get("whatsapp_phone"),
            "agent_agency": contact.get("agent_agency"),
            "source": "live",
        }
    except Exception:
        logger.exception("Contact fetch error")
        return {"phone": None, "call_phone": None, "whatsapp_phone": None}


@router.get("/api/listing-phone")
@limiter.limit(_LISTING_DETAIL_RATE_LIMIT)
async def listing_phone(request: Request, url: str = Query(...)):
    """Legacy contact endpoint kept for card actions."""
    if not url.startswith("https://www.zameen.com/"):
        raise HTTPException(status_code=400, detail="Invalid Zameen.com URL")
    try:
        return await listing_contact(request, url)
    except Exception:
        logger.exception("Phone fetch error")
        return {"phone": None, "call_phone": None, "whatsapp_phone": None}


@router.get("/api/crawl-status")
async def crawl_status(city: Optional[str] = Query(None)):
    """Return crawl progress and data freshness info."""
    return get_crawl_stats(city)


@router.get("/api/popular-searches")
async def popular_searches(city: str = Query("lahore"), limit: int = Query(8, ge=1, le=20)):
    return get_popular_searches(city, limit)


@router.get("/api/recent-searches")
async def recent_searches(city: str = Query("lahore"), limit: int = Query(8, ge=1, le=20)):
    return get_recent_searches(city, limit)


@router.post("/api/feedback")
@limiter.limit("5/minute")
async def submit_feedback(request: Request):
    body = await request.json()
    message = (body.get("message") or "").strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message is required")
    if len(message) > 2000:
        raise HTTPException(status_code=400, detail="Message too long")
    context = body.get("context")
    save_feedback(message, context)
    return {"ok": True}


# ── Personalization: alerts, favorites, hidden, recently viewed, push ──

from app import personalization as pers  # noqa: E402

_PERSONALIZATION_BURST = "240/minute" if _PLAYWRIGHT_SERVER else "60/minute"
_PERSONALIZATION_STEADY = "240/minute" if _PLAYWRIGHT_SERVER else "120/minute"
_PERSONALIZATION_HIGH = "600/minute" if _PLAYWRIGHT_SERVER else "240/minute"


def _require_client_id(request: Request) -> str:
    client_id = (request.headers.get("X-Client-Id") or "").strip()
    if not pers.is_valid_client_id(client_id):
        raise HTTPException(status_code=400, detail="Missing or invalid X-Client-Id header")
    return client_id


@router.post("/api/personalization/touch")
@limiter.limit(_PERSONALIZATION_BURST)
async def personalization_touch(request: Request):
    """Record a new session visit and return the previous visit timestamp.

    The previous timestamp powers the 'new since your last visit' badge.
    """
    client_id = _require_client_id(request)
    previous_visit = pers.previous_visit_at(client_id)
    pers.ensure_client(client_id, touch_visit=True)
    unseen = pers.unseen_match_count(client_id)
    return {
        "client_id": client_id,
        "previous_visit_at": previous_visit,
        "unseen_alert_matches": unseen,
        "vapid_public_key": pers.vapid_public_key(),
    }


@router.get("/api/personalization/state")
@limiter.limit(_PERSONALIZATION_STEADY)
async def personalization_state(request: Request):
    """Snapshot of everything the frontend needs to render personalization."""
    client_id = _require_client_id(request)
    pers.ensure_client(client_id)
    return {
        "favorites": sorted(pers.get_favorite_zameen_ids(client_id)),
        "hidden": sorted(pers.get_hidden_zameen_ids(client_id)),
        "alert_count": pers.count_alerts(client_id),
        "unseen_alert_matches": pers.unseen_match_count(client_id),
        "vapid_public_key": pers.vapid_public_key(),
        "push_subscription_count": len(pers.list_push_subscriptions(client_id)),
    }


@router.get("/api/alerts")
@limiter.limit(_PERSONALIZATION_STEADY)
async def alerts_list(request: Request):
    client_id = _require_client_id(request)
    return {"alerts": pers.list_alerts(client_id)}


@router.post("/api/alerts")
@limiter.limit(_PERSONALIZATION_BURST)
async def alerts_create(request: Request):
    client_id = _require_client_id(request)
    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Body must be an object")
    filters = body.get("filters") or {}
    label = body.get("label")
    try:
        alert = pers.create_alert(
            client_id,
            label=label,
            filters=filters,
            notify_push=body.get("notify_push", True),
            notify_inapp=body.get("notify_inapp", True),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return alert


@router.patch("/api/alerts/{alert_id}")
@limiter.limit(_PERSONALIZATION_STEADY)
async def alerts_update(request: Request, alert_id: int):
    client_id = _require_client_id(request)
    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Body must be an object")
    try:
        alert = pers.update_alert(
            client_id,
            alert_id,
            label=body.get("label"),
            paused=body.get("paused"),
            notify_push=body.get("notify_push"),
            notify_inapp=body.get("notify_inapp"),
            filters=body.get("filters"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    return alert


@router.delete("/api/alerts/{alert_id}")
@limiter.limit(_PERSONALIZATION_BURST)
async def alerts_delete(request: Request, alert_id: int):
    client_id = _require_client_id(request)
    if not pers.delete_alert(client_id, alert_id):
        raise HTTPException(status_code=404, detail="Alert not found")
    return {"ok": True}


@router.get("/api/alerts/matches")
@limiter.limit(_PERSONALIZATION_STEADY)
async def alerts_matches(request: Request,
                         alert_id: Optional[int] = Query(None),
                         unseen: bool = Query(False),
                         limit: int = Query(50, ge=1, le=200)):
    client_id = _require_client_id(request)
    matches = pers.list_matches(client_id, alert_id=alert_id, unseen_only=unseen, limit=limit)
    return {
        "matches": matches,
        "unseen_count": pers.unseen_match_count(client_id),
    }


@router.post("/api/alerts/matches/seen")
@limiter.limit(_PERSONALIZATION_BURST)
async def alerts_matches_seen(request: Request):
    client_id = _require_client_id(request)
    body = await request.json() if await _has_json_body(request) else {}
    match_ids = body.get("match_ids") if isinstance(body, dict) else None
    alert_id = body.get("alert_id") if isinstance(body, dict) else None
    updated = pers.mark_matches_seen(client_id, match_ids=match_ids, alert_id=alert_id)
    return {"updated": updated, "unseen_count": pers.unseen_match_count(client_id)}


async def _has_json_body(request: Request) -> bool:
    ctype = request.headers.get("content-type", "")
    if "application/json" not in ctype.lower():
        return False
    raw = await request.body()
    return bool(raw)


@router.post("/api/alerts/run-match-cycle")
@limiter.limit("6/minute")
async def alerts_run_cycle(request: Request):
    """Trigger a global alert match cycle for an authorized admin."""
    _require_admin_token(request)
    dispatch = (request.query_params.get("dispatch") or "").lower() in ("1", "true", "yes")
    summary = pers.run_match_cycle(dispatch=dispatch)
    return summary


@router.get("/api/favorites")
@limiter.limit(_PERSONALIZATION_STEADY)
async def favorites_list(request: Request, limit: int = Query(200, ge=1, le=500)):
    client_id = _require_client_id(request)
    return {"favorites": pers.list_favorites(client_id, limit=limit)}


@router.post("/api/favorites")
@limiter.limit(_PERSONALIZATION_STEADY)
async def favorites_create(request: Request):
    client_id = _require_client_id(request)
    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Body must be an object")
    zameen_id = (body.get("zameen_id") or "").strip()
    if not zameen_id:
        raise HTTPException(status_code=400, detail="zameen_id is required")
    fav = pers.add_favorite(client_id, zameen_id, note=body.get("note"))
    return {"favorite": fav}


@router.delete("/api/favorites/{zameen_id}")
@limiter.limit(_PERSONALIZATION_STEADY)
async def favorites_remove(request: Request, zameen_id: str):
    client_id = _require_client_id(request)
    removed = pers.remove_favorite(client_id, zameen_id)
    return {"ok": removed}


@router.get("/api/hidden")
@limiter.limit(_PERSONALIZATION_STEADY)
async def hidden_list(request: Request, limit: int = Query(200, ge=1, le=500)):
    client_id = _require_client_id(request)
    return {"hidden": pers.list_hidden(client_id, limit=limit)}


@router.post("/api/hidden")
@limiter.limit(_PERSONALIZATION_STEADY)
async def hidden_create(request: Request):
    client_id = _require_client_id(request)
    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Body must be an object")
    zameen_id = (body.get("zameen_id") or "").strip()
    if not zameen_id:
        raise HTTPException(status_code=400, detail="zameen_id is required")
    added = pers.add_hidden(client_id, zameen_id)
    return {"ok": True, "added": added}


@router.delete("/api/hidden/{zameen_id}")
@limiter.limit(_PERSONALIZATION_STEADY)
async def hidden_remove(request: Request, zameen_id: str):
    client_id = _require_client_id(request)
    removed = pers.remove_hidden(client_id, zameen_id)
    return {"ok": removed}


@router.get("/api/recent-views")
@limiter.limit(_PERSONALIZATION_STEADY)
async def recent_views_list(request: Request, limit: int = Query(50, ge=1, le=200)):
    client_id = _require_client_id(request)
    return {"recent_views": pers.list_recent_views(client_id, limit=limit)}


@router.post("/api/recent-views")
@limiter.limit(_PERSONALIZATION_HIGH)
async def recent_views_record(request: Request):
    client_id = _require_client_id(request)
    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Body must be an object")
    zameen_id = (body.get("zameen_id") or "").strip()
    if not zameen_id:
        raise HTTPException(status_code=400, detail="zameen_id is required")
    pers.record_view(client_id, zameen_id)
    return {"ok": True}


@router.get("/api/push/vapid-key")
async def push_vapid_key():
    return {"vapid_public_key": pers.vapid_public_key()}


@router.post("/api/push/subscribe")
@limiter.limit(_PERSONALIZATION_BURST)
async def push_subscribe(request: Request):
    client_id = _require_client_id(request)
    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Body must be an object")
    endpoint = (body.get("endpoint") or "").strip()
    keys = body.get("keys") or {}
    p256dh = (keys.get("p256dh") or "").strip()
    auth = (keys.get("auth") or "").strip()
    if not endpoint or not p256dh or not auth:
        raise HTTPException(status_code=400, detail="endpoint, keys.p256dh, and keys.auth are required")
    ua = request.headers.get("user-agent")
    try:
        sub = pers.save_push_subscription(client_id, endpoint=endpoint, p256dh=p256dh,
                                          auth=auth, user_agent=ua)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, "subscription_id": sub.get("id")}


@router.post("/api/push/unsubscribe")
@limiter.limit(_PERSONALIZATION_BURST)
async def push_unsubscribe(request: Request):
    client_id = _require_client_id(request)
    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Body must be an object")
    endpoint = (body.get("endpoint") or "").strip()
    if not endpoint:
        raise HTTPException(status_code=400, detail="endpoint is required")
    pers.remove_push_subscription(endpoint=endpoint, client_id=client_id)
    return {"ok": True}


@router.post("/api/push/test")
@limiter.limit("6/minute")
async def push_test(request: Request):
    """Send a one-off test notification to all of the caller's subscriptions."""
    client_id = _require_client_id(request)
    subs = pers.list_push_subscriptions(client_id)
    if not subs:
        return {"sent": 0, "detail": "No push subscriptions"}
    payload = {
        "type": "test",
        "title": "ZameenRentals",
        "body": "Notifications are working! You'll get a ping when a new rental matches one of your alerts.",
        "url": "/?alerts=open",
        "tag": "zameen-test",
    }
    sent = sum(1 for sub in subs if pers.send_push(sub, payload))
    return {"sent": sent, "total": len(subs)}


_ROOT_STATIC_FILES = {
    "sw.js": "application/javascript",
    "offline.html": "text/html",
    "site.webmanifest": "application/manifest+json",
    "favicon.svg": "image/svg+xml",
    "favicon-16x16.png": "image/png",
    "favicon-32x32.png": "image/png",
    "favicon-512.png": "image/png",
    "apple-touch-icon.png": "image/png",
    "android-chrome-192x192.png": "image/png",
    "android-chrome-512x512.png": "image/png",
    "logo.svg": "image/svg+xml",
    "og-card.png": "image/png",
    "og-card.svg": "image/svg+xml",
}


@router.get("/{filename}")
async def serve_root_static(filename: str):
    """Serve PWA assets (service worker, manifest, favicons) from root path.

    The service worker MUST be served from a path whose scope includes the
    pages it controls — registering /sw.js at scope '/' requires the file
    itself to be at /sw.js, not /static/sw.js.
    """
    if filename not in _ROOT_STATIC_FILES:
        raise HTTPException(status_code=404)
    path = _PROJECT_ROOT / "static" / filename
    if not path.exists():
        raise HTTPException(status_code=404)
    headers = {}
    if filename == "sw.js":
        # Never cache the service worker so updates roll out on next visit.
        headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        headers["Service-Worker-Allowed"] = "/"
    return FileResponse(path, media_type=_ROOT_STATIC_FILES[filename], headers=headers)


@router.get("/")
async def serve_frontend():
    p = _PROJECT_ROOT / "static" / "index.html"
    return FileResponse(p, media_type="text/html") if p.exists() else HTMLResponse("<h1>ZameenRentals</h1><p>index.html not found</p>")
