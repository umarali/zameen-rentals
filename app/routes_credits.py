"""Credits API. Payment checkout and restore routes are added here too."""
from fastapi import APIRouter, Request

from app import credits
from app.cache import limiter
from app.routes import _require_client_id, _PERSONALIZATION_STEADY

router = APIRouter()


@router.get("/api/credits")
@limiter.limit(_PERSONALIZATION_STEADY)
async def get_credits(request: Request):
    client_id = _require_client_id(request)
    return credits.summary(client_id)
