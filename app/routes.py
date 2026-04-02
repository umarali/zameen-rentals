"""API route handlers."""
import logging
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse

from app.data import KARACHI_AREAS, PROPERTY_TYPES, CITIES, CITY_AREAS, get_areas, _ENGLISH_TO_URDU
from app.cache import limiter
from app.database import log_search, get_popular_searches, get_recent_searches
from app.parsing import parse_query_with_claude
from app.scraper import search_zameen, fetch_listing_contact, fetch_listing_detail, extract_zameen_id
from app.db_listings import (
    search_listings, count_listings_by_area, get_listing_by_zameen_id,
    get_crawl_stats, upsert_listing,
)

logger = logging.getLogger("zameenrentals")
router = APIRouter()

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _contact_response_from_listing(listing):
    call_phone = listing.get("call_phone") or listing.get("phone")
    whatsapp_phone = listing.get("whatsapp_phone") or call_phone
    return {
        "phone": call_phone,
        "call_phone": call_phone,
        "whatsapp_phone": whatsapp_phone,
        "agent_agency": listing.get("agent_agency"),
        "source": "local",
    }


@router.get("/api/health")
async def health():
    return {"status": "ok", "service": "ZameenRentals", "version": "1.0.0"}


@router.get("/api/cities")
async def get_cities():
    return [{"key": k, "name": v["name"], "lat": v["lat"], "lng": v["lng"]} for k, v in CITIES.items()]


@router.get("/api/areas")
async def get_areas_api(city: str = Query("karachi")):
    areas = get_areas(city)
    urdu_map = _ENGLISH_TO_URDU if city == "karachi" else {}
    return [{"name": n, "slug": s, "id": i, "lat": lat, "lng": lng, "name_ur": urdu_map.get(n, "")} for n, (s, i, lat, lng) in sorted(areas.items())]


@router.get("/api/search-areas")
async def search_areas(q: str = Query(..., min_length=1), city: str = Query("karachi"), limit: int = Query(20, ge=1, le=50)):
    """Fuzzy search across all known areas for a city. Returns top matches."""
    areas = get_areas(city)
    ql = q.strip().lower()
    scored = []
    city_name = CITIES.get(city, CITIES["karachi"])["name"]
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
@limiter.limit("15/minute")
async def api_parse_query(request: Request, q: str = Query(..., min_length=1), city: str = Query("karachi")):
    try:
        result = await parse_query_with_claude(q, city=city)
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
    except Exception:
        logger.exception("Parse query error")
        raise HTTPException(status_code=500, detail="Failed to parse query. Please try again.")


@router.get("/api/search")
@limiter.limit("10/minute")
async def search(request: Request, city: str = Query("karachi"), area: Optional[str]=Query(None), property_type: Optional[str]=Query(None), bedrooms: Optional[int]=Query(None, ge=1, le=10), price_min: Optional[int]=Query(None, ge=0), price_max: Optional[int]=Query(None, ge=0), furnished: Optional[bool]=Query(None), page: int=Query(1, ge=1), sort: Optional[str]=Query(None)):
    try:
        # Try local DB first (instant results from crawler data)
        local_result = search_listings(
            city=city, area=area, property_type=property_type,
            bedrooms=bedrooms, price_min=price_min, price_max=price_max,
            furnished=furnished, sort=sort, page=page
        )
        if local_result["total"] > 0:
            local_result["source"] = "local"
            log_search(city=city, area=area, property_type=property_type, bedrooms=bedrooms,
                       price_min=price_min, price_max=price_max, furnished=furnished,
                       sort=sort, result_count=local_result["total"])
            return local_result

        # Fallback to live scraping if local DB has no results for this query
        try:
            result = await search_zameen(area=area, property_type=property_type, bedrooms=bedrooms, price_min=price_min, price_max=price_max, furnished=furnished, page=page, sort=sort, city=city)
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
@limiter.limit("20/minute")
async def map_search(
    request: Request,
    city: str = Query("karachi"),
    areas: list[str] = Query([]),
    property_type: Optional[str] = Query(None),
    bedrooms: Optional[int] = Query(None, ge=1, le=10),
    price_min: Optional[int] = Query(None, ge=0),
    price_max: Optional[int] = Query(None, ge=0),
    furnished: Optional[bool] = Query(None),
    page: int = Query(1, ge=1),
    sort: Optional[str] = Query(None),
    center_lat: Optional[float] = Query(None, ge=-90, le=90),
    center_lng: Optional[float] = Query(None, ge=-180, le=180),
):
    area_names = [a for a in areas if a]
    if not area_names:
        return {
            "total": 0,
            "page": page,
            "per_page": 25,
            "results": [],
            "source": "local",
            "mode": "viewport",
            "visible_areas": 0,
            "area_totals": {},
        }

    result = search_listings(
        city=city, area_names=area_names, property_type=property_type,
        bedrooms=bedrooms, price_min=price_min, price_max=price_max,
        furnished=furnished, sort=sort, page=page,
        center_lat=center_lat, center_lng=center_lng,
    )
    result["source"] = "local"
    result["mode"] = "viewport"
    result["visible_areas"] = len(area_names)
    result["focus_center"] = (
        {"lat": center_lat, "lng": center_lng}
        if center_lat is not None and center_lng is not None
        else None
    )
    result["area_totals"] = count_listings_by_area(
        city=city, area_names=area_names, property_type=property_type,
        bedrooms=bedrooms, price_min=price_min, price_max=price_max,
        furnished=furnished,
    )
    return result


@router.get("/api/listing-detail")
@limiter.limit("20/minute")
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
                import json
                local_detail = {
                    "phone": listing.get("phone"),
                    "call_phone": listing.get("call_phone") or listing.get("phone"),
                    "whatsapp_phone": listing.get("whatsapp_phone") or listing.get("call_phone") or listing.get("phone"),
                    "description": listing.get("description"),
                    "features": json.loads(listing["features_json"]) if listing.get("features_json") else [],
                    "amenities": json.loads(listing["amenities_json"]) if listing.get("amenities_json") else [],
                    "details": json.loads(listing["details_json"]) if listing.get("details_json") else {},
                    "agent_name": listing.get("agent_name"),
                    "agent_agency": listing.get("agent_agency"),
                    "images": json.loads(listing["detail_images_json"]) if listing.get("detail_images_json") else [],
                    "latitude": listing.get("latitude"),
                    "longitude": listing.get("longitude"),
                    "location_source": listing.get("location_source"),
                    "has_exact_geography": listing.get("location_source") == "listing_exact",
                    "contact_source": listing.get("contact_source"),
                    "source": "local",
                }
                if local_detail["has_exact_geography"]:
                    return local_detail
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
@limiter.limit("20/minute")
async def listing_contact(request: Request, url: str = Query(...)):
    """Fetch contact data — from local DB if available, else live via showNumbers."""
    if not url.startswith("https://www.zameen.com/"):
        raise HTTPException(status_code=400, detail="Invalid Zameen.com URL")
    try:
        zid = extract_zameen_id(url)
        if zid:
            listing = get_listing_by_zameen_id(zid)
            if listing and (listing.get("call_phone") or listing.get("phone") or listing.get("whatsapp_phone")):
                return _contact_response_from_listing(listing)
        contact = await fetch_listing_contact(url)
        if not contact:
            return {"phone": None, "call_phone": None, "whatsapp_phone": None}
        if zid:
            upsert_listing(
                zameen_id=zid, url=url, city="",
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
@limiter.limit("20/minute")
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
async def popular_searches(city: str = Query("karachi"), limit: int = Query(8, ge=1, le=20)):
    return get_popular_searches(city, limit)


@router.get("/api/recent-searches")
async def recent_searches(city: str = Query("karachi"), limit: int = Query(8, ge=1, le=20)):
    return get_recent_searches(city, limit)


@router.get("/")
async def serve_frontend():
    p = _PROJECT_ROOT / "static" / "index.html"
    return FileResponse(p, media_type="text/html") if p.exists() else HTMLResponse("<h1>ZameenRentals</h1><p>index.html not found</p>")
