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
from app.scraper import search_zameen

logger = logging.getLogger("zameenrentals")
router = APIRouter()

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


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
        result = await search_zameen(area=area, property_type=property_type, bedrooms=bedrooms, price_min=price_min, price_max=price_max, furnished=furnished, page=page, sort=sort, city=city)
        log_search(city=city, area=area, property_type=property_type, bedrooms=bedrooms,
                   price_min=price_min, price_max=price_max, furnished=furnished,
                   sort=sort, result_count=result.get("total", 0))
        return result
    except HTTPException:
        raise
    except Exception:
        logger.exception("Search error")
        raise HTTPException(status_code=500, detail="An internal error occurred. Please try again later.")


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
