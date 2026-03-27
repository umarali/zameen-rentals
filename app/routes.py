"""API route handlers."""
import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse

from app.data import KARACHI_AREAS, PROPERTY_TYPES, _ENGLISH_TO_URDU
from app.parsing import parse_query_with_claude
from app.scraper import search_zameen

logger = logging.getLogger("zameenrentals")
router = APIRouter()

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


@router.get("/api/health")
async def health():
    return {"status": "ok", "service": "ZameenRentals", "version": "1.0.0"}


@router.get("/api/areas")
async def get_areas():
    return [{"name": n, "slug": s, "id": i, "lat": lat, "lng": lng, "name_ur": _ENGLISH_TO_URDU.get(n, "")} for n, (s, i, lat, lng) in sorted(KARACHI_AREAS.items())]


@router.get("/api/property-types")
async def get_property_types():
    seen, types = set(), []
    for key, info in PROPERTY_TYPES.items():
        if key == "flat": continue
        if info["slug"] not in seen: seen.add(info["slug"]); types.append({"key": key, "label": info["label"]})
    return types


@router.get("/api/parse-query")
async def api_parse_query(q: str = Query(..., min_length=1)):
    result = await parse_query_with_claude(q)
    return {"query": q, "filters": result}


@router.get("/api/search")
async def search(area: Optional[str]=Query(None), property_type: Optional[str]=Query(None), bedrooms: Optional[int]=Query(None, ge=1, le=10), price_min: Optional[int]=Query(None, ge=0), price_max: Optional[int]=Query(None, ge=0), furnished: Optional[bool]=Query(None), page: int=Query(1, ge=1), sort: Optional[str]=Query(None)):
    try: return await search_zameen(area=area, property_type=property_type, bedrooms=bedrooms, price_min=price_min, price_max=price_max, furnished=furnished, page=page, sort=sort)
    except HTTPException: raise
    except Exception as e: logger.error(f"Search error: {e}"); raise HTTPException(status_code=500, detail=str(e))


@router.get("/")
async def serve_frontend():
    p = _PROJECT_ROOT / "static" / "index.html"
    return FileResponse(p, media_type="text/html") if p.exists() else HTMLResponse("<h1>RentKarachi</h1><p>index.html not found</p>")
