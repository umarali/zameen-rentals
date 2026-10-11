"""Tailored list: a renter's detailed brief -> the ~10 best local listings, with reasons.

Two steps, split so the route can charge only when there is something to rank:

1. ``prepare(brief, city, client_id)`` (free): the existing NL parser turns the
   brief into search filters, then candidates come from the local DB with the
   usual filter SQL. If too few match, filters are relaxed one step at a time
   and each relaxation is reported to the renter. Hidden listings are left out.
2. ``rank(prepared)`` (paid): Claude ranks the candidates with reasons and
   trade-offs grounded in listing data (app/ranking.py).
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

from app import ranking
from app.data import CITIES, PROPERTY_TYPES

logger = logging.getLogger("zameenrentals")

BRIEF_MIN_CHARS = 10
BRIEF_MAX_CHARS = 600
RESULT_LIMIT = 10
# Below this many strict matches, widen the search before ranking.
MIN_CANDIDATES = 12
_FETCH_PER_STEP = 80

FILTER_KEYS = ("area", "areas", "property_type", "bedrooms", "bedrooms_max", "price_min",
               "price_max", "size_marla_min", "size_marla_max", "furnished")


@dataclass
class Prepared:
    city: str
    brief: str
    filters: dict
    candidates: list = field(default_factory=list)
    relaxed: list = field(default_factory=list)
    strict_count: int = 0


def validate_brief(brief, city) -> tuple[str, str]:
    """Normalized (brief, city). Raises ValueError with a message fit for the renter."""
    if not isinstance(brief, str):
        raise ValueError("Describe what you're looking for.")
    brief = " ".join(brief.split())
    if len(brief) < BRIEF_MIN_CHARS:
        raise ValueError(f"Add a little more detail (at least {BRIEF_MIN_CHARS} characters).")
    if len(brief) > BRIEF_MAX_CHARS:
        raise ValueError(f"Keep it under {BRIEF_MAX_CHARS} characters.")
    city = (city or "").strip().lower()
    if city not in CITIES:
        raise ValueError("Choose Karachi, Lahore or Islamabad.")
    return brief, city


async def understand_brief(brief: str, city: str) -> tuple[dict, str]:
    """Search filters from the brief and the city they apply to.

    Reuses the search box parser (Claude with a regex fallback, cached).
    Browser tests never call Claude.
    """
    from app.parsing import parse_natural_query, parse_query_with_claude
    if os.environ.get("ZAMEENRENTALS_PLAYWRIGHT") == "1":
        parsed = parse_natural_query(brief, city=city)
    else:
        parsed = await parse_query_with_claude(brief, city=city)
    hint = parsed.get("city_hint")
    if hint in CITIES:
        city = hint
    filters = {k: parsed[k] for k in FILTER_KEYS if parsed.get(k) not in (None, "", [])}
    if filters.get("property_type") and filters["property_type"].lower() not in PROPERTY_TYPES:
        filters.pop("property_type")
    return filters, city


def _search(city, filters, per_page=_FETCH_PER_STEP):
    from app.db_listings import search_listings
    areas = filters.get("areas") or []
    return search_listings(
        city=city,
        area=None if len(areas) > 1 else filters.get("area"),
        area_names=areas if len(areas) > 1 else None,
        property_type=filters.get("property_type"),
        bedrooms=filters.get("bedrooms"), bedrooms_max=filters.get("bedrooms_max"),
        price_min=filters.get("price_min"), price_max=filters.get("price_max"),
        size_marla_min=filters.get("size_marla_min"), size_marla_max=filters.get("size_marla_max"),
        furnished=filters.get("furnished"), per_page=per_page,
    )


def _relaxations(filters):
    """Wider filter sets to try in order, each with a note for the renter."""
    steps = []
    current = dict(filters)
    if current.get("bedrooms") and not current.get("bedrooms_max") and current["bedrooms"] < 10:
        current = {**current, "bedrooms_max": current["bedrooms"] + 1}
        steps.append((dict(current), f"Also included {current['bedrooms_max']} bedroom homes."))
    if current.get("price_max"):
        wider = int(round(current["price_max"] * 1.15, -3))
        current = {**current, "price_max": wider}
        steps.append((dict(current), f"Included homes up to 15% over your budget (up to PKR {wider:,})."))
    dropped = [k for k in ("size_marla_min", "size_marla_max", "furnished") if k in current]
    if dropped:
        current = {k: v for k, v in current.items() if k not in dropped}
        parts = (["size"] if any(k.startswith("size") for k in dropped) else []) \
            + (["furnishing"] if "furnished" in dropped else [])
        label = " and ".join(parts)
        steps.append((dict(current), f"Included homes outside your {label} filter."))
    return steps


async def prepare(brief: str, city: str, client_id: str | None = None) -> Prepared:
    filters, city = await understand_brief(brief, city)
    hidden = set()
    if client_id:
        from app.personalization import get_hidden_zameen_ids
        hidden = get_hidden_zameen_ids(client_id)

    prepared = Prepared(city=city, brief=brief, filters=filters)
    seen = set()

    def take(results, tier):
        for item in results:
            zid = str(item.get("zameen_id") or "")
            if zid and zid not in seen and zid not in hidden:
                seen.add(zid)
                prepared.candidates.append((tier, item))

    strict = _search(city, filters)
    prepared.strict_count = strict["total"]
    take(strict["results"], 0)
    for tier, (wider, note) in enumerate(_relaxations(filters), start=1):
        if len(prepared.candidates) >= MIN_CANDIDATES:
            break
        before = len(prepared.candidates)
        take(_search(city, wider)["results"], tier)
        if len(prepared.candidates) > before:
            prepared.relaxed.append(note)

    # Strict matches first; within a tier, listings with a description first
    # (more facts to judge by), otherwise newest first as the DB returned them.
    ordered = sorted(enumerate(prepared.candidates),
                     key=lambda p: (p[1][0], not p[1][1].get("description"), p[0]))
    prepared.candidates = [item for _, (_, item) in ordered][:ranking.MAX_CANDIDATES]
    return prepared


def rank(prepared: Prepared) -> dict:
    """Paid step. Raises ranking.RankingError on failure."""
    criteria = {"city": prepared.city, **prepared.filters}
    ranked, preferences = ranking.rank_with_preferences(
        criteria, prepared.candidates, prepared.brief, RESULT_LIMIT, feature="tailored_list")
    by_id = {str(item["zameen_id"]): item for item in prepared.candidates}
    results = []
    for row in ranked:
        listing = dict(by_id[row["zameen_id"]])
        listing["ai_reason"] = row["reason"]
        listing["ai_trade_off"] = row["trade_off"]
        results.append(listing)
    return {
        "results": results,
        "understood": {"city": prepared.city, "filters": prepared.filters, "preferences": preferences},
        "relaxed": prepared.relaxed,
        "candidates_considered": len(prepared.candidates),
        "source": "Zameen.com",
    }
