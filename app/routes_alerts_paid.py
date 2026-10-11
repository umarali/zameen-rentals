"""Paid alert upgrades API: priority check and daily shortlist, charged per day."""
from fastapi import APIRouter, HTTPException, Query, Request

from app import alert_upgrades as upgrades
from app import credits
from app.cache import limiter
from app.routes import _PERSONALIZATION_BURST, _PERSONALIZATION_STEADY, _require_client_id

router = APIRouter()


@router.get("/api/alerts/upgrades")
@limiter.limit(_PERSONALIZATION_STEADY)
async def alert_upgrades_state(request: Request):
    """Balance, daily costs, per-alert upgrade state and unread notices."""
    client_id = _require_client_id(request)
    return upgrades.get_state(client_id)


@router.post("/api/alerts/{alert_id}/upgrades/{upgrade}")
@limiter.limit(_PERSONALIZATION_BURST)
async def alert_upgrade_set(request: Request, alert_id: int, upgrade: str):
    """Switch an upgrade on (charges today now) or off (stops future charges)."""
    client_id = _require_client_id(request)
    if upgrade not in upgrades.UPGRADES:
        raise HTTPException(status_code=404, detail="Unknown upgrade")
    try:
        body = await request.json()
    except ValueError:
        body = None
    if not isinstance(body, dict) or not isinstance(body.get("enabled"), bool):
        raise HTTPException(status_code=400, detail="Body must be {\"enabled\": true|false}")
    try:
        return upgrades.set_upgrade(client_id, alert_id, upgrade, body["enabled"])
    except credits.InsufficientCredits as exc:
        raise HTTPException(status_code=402, detail=exc.as_detail())
    except LookupError:
        raise HTTPException(status_code=404, detail="Alert not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/api/alerts/{alert_id}/shortlists")
@limiter.limit(_PERSONALIZATION_STEADY)
async def alert_shortlists(request: Request, alert_id: int, limit: int = Query(7, ge=1, le=30)):
    """Delivered daily shortlists for one alert, newest first. Marks them seen."""
    client_id = _require_client_id(request)
    if upgrades._alert_row(client_id, alert_id) is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    return {"shortlists": upgrades.list_shortlists(client_id, alert_id, limit=limit)}


@router.post("/api/alerts/upgrades/notices/seen")
@limiter.limit(_PERSONALIZATION_BURST)
async def alert_upgrade_notices_seen(request: Request):
    client_id = _require_client_id(request)
    try:
        body = await request.json()
    except ValueError:
        body = {}
    ids = body.get("ids") if isinstance(body, dict) else None
    if ids is not None and not (isinstance(ids, list) and all(isinstance(i, int) for i in ids)):
        raise HTTPException(status_code=400, detail="ids must be a list of integers")
    return {"updated": upgrades.dismiss_notices(client_id, ids)}
