"""NLP query parsing, area matching, price parsing, and URL building."""
import asyncio, logging, os, re
from difflib import SequenceMatcher
from typing import Literal, Optional
from urllib.parse import urlencode

import anthropic
import instructor
from pydantic import BaseModel, Field

from app.data import (
    KARACHI_AREAS, PROPERTY_TYPES,
    URDU_AREAS, ROMAN_URDU_AREAS,
    URDU_TYPES, ROMAN_URDU_TYPES,
)
from app.cache import cache_key, cache_get, cache_set

logger = logging.getLogger("zameenrentals")


def _parse_price_token(text):
    """Parse a price value from text like '50k', '50000', '1.5lac', '2lakh', '50 hazar'."""
    text = text.strip().lower().replace(',', '')
    m = re.match(r'([\d.]+)\s*(?:lac|lakh|lacs|laakh)', text)
    if m: return int(float(m.group(1)) * 100_000)
    m = re.match(r'([\d.]+)\s*(?:k|hazar|hazaar)', text)
    if m: return int(float(m.group(1)) * 1_000)
    m = re.match(r'([\d.]+)\s*(?:crore|cr)', text)
    if m: return int(float(m.group(1)) * 10_000_000)
    m = re.match(r'[\d.]+', text)
    if m:
        v = float(m.group(0))
        if v <= 500: return int(v * 1_000)  # "50" likely means 50k
        return int(v)
    return None


def parse_natural_query(query: str) -> dict:
    """Parse a natural language rental query into structured filters.
    Supports English, Roman Urdu, and Urdu script."""
    result = {}
    q = query.strip()
    if not q:
        return result
    ql = q.lower()

    # --- Furnished ---
    if re.search(r'\b(?:furnished|furnish|فرنشڈ|فرنش)\b', q, re.I):
        result['furnished'] = True
        ql = re.sub(r'\b(?:furnished|furnish)\b', ' ', ql, flags=re.I)

    # --- Sort ---
    if re.search(r'\b(?:cheapest|sasta|سستا|cheap|affordable|budget)\b', q, re.I):
        result['sort'] = 'price_low'
    elif re.search(r'\b(?:expensive|mehenga|مہنگا|luxury|premium)\b', q, re.I):
        result['sort'] = 'price_high'
    elif re.search(r'\b(?:newest|latest|naya|نیا|new|recent)\b', q, re.I):
        result['sort'] = 'newest'

    # --- Bedrooms ---
    m = re.search(r'(\d+)\s*(?:bed(?:room)?s?|br|bhk|kamr[eao]|کمر[ےوں]|بیڈ)', ql)
    if m:
        result['bedrooms'] = min(int(m.group(1)), 10)
    elif re.search(r'\b(?:studio|اسٹوڈیو)\b', q, re.I):
        result['bedrooms'] = 1

    # --- Property type (Urdu script first) ---
    for ur_type, key in sorted(URDU_TYPES.items(), key=lambda x: -len(x[0])):
        if ur_type in q:
            result['property_type'] = key
            break
    if 'property_type' not in result:
        for alias, key in sorted(ROMAN_URDU_TYPES.items(), key=lambda x: -len(x[0])):
            if re.search(r'\b' + re.escape(alias) + r'\b', ql):
                result['property_type'] = key
                break

    # --- Price ---
    m = re.search(r'([\d.]+\s*(?:k|lac|lakh|lacs|laakh|hazar|hazaar|crore|cr)?)\s*(?:-|to|se|سے|تک)\s*([\d.]+\s*(?:k|lac|lakh|lacs|laakh|hazar|hazaar|crore|cr)?)', ql)
    if m:
        pmin = _parse_price_token(m.group(1))
        pmax = _parse_price_token(m.group(2))
        if pmin is not None: result['price_min'] = pmin
        if pmax is not None: result['price_max'] = pmax
    else:
        m = re.search(r'(?:under|below|max|upto|up\s*to|tak|تک|andar|kam|کم|se\s*kam|سے\s*کم|ke\s*andar)\s*([\d.]+\s*(?:k|lac|lakh|lacs|laakh|hazar|hazaar|crore|cr)?)', ql)
        if m:
            pmax = _parse_price_token(m.group(1))
            if pmax is not None: result['price_max'] = pmax
        else:
            m = re.search(r'([\d.]+\s*(?:k|lac|lakh|lacs|laakh|hazar|hazaar|crore|cr)?)\s*(?:ke\s*andar|se\s*kam|tak|تک|کم)', ql)
            if m:
                pmax = _parse_price_token(m.group(1))
                if pmax is not None: result['price_max'] = pmax

        m2 = re.search(r'(?:above|over|min(?:imum)?|from|zyada|زیادہ|se\s*zyada|سے\s*زیادہ)\s*([\d.]+\s*(?:k|lac|lakh|lacs|laakh|hazar|hazaar|crore|cr)?)', ql)
        if m2:
            pmin = _parse_price_token(m2.group(1))
            if pmin is not None: result['price_min'] = pmin
        elif not m:
            m2 = re.search(r'([\d.]+\s*(?:k|lac|lakh|lacs|laakh|hazar|hazaar|crore|cr)?)\s*(?:se\s*zyada|سے\s*زیادہ|plus|\+)', ql)
            if m2:
                pmin = _parse_price_token(m2.group(1))
                if pmin is not None: result['price_min'] = pmin

    # --- Area ---
    for ur_area, en_area in sorted(URDU_AREAS.items(), key=lambda x: -len(x[0])):
        if ur_area in q:
            result['area'] = en_area
            break
    if 'area' not in result:
        for alias, area_name in sorted(ROMAN_URDU_AREAS.items(), key=lambda x: -len(x[0])):
            if re.search(r'\b' + re.escape(alias) + r'\b', ql):
                result['area'] = area_name
                break
    if 'area' not in result:
        for name in sorted(KARACHI_AREAS.keys(), key=lambda x: -len(x)):
            if name.lower() in ql:
                result['area'] = name
                break

    return result


def match_area(query):
    q = query.strip()
    for ur, en in URDU_AREAS.items():
        if ur == q: return en
    for ur, en in URDU_AREAS.items():
        if q in ur or ur in q: return en
    q = q.lower()
    for name in KARACHI_AREAS:
        if name.lower() == q: return name
    for name in KARACHI_AREAS:
        if q in name.lower() or name.lower() in q: return name
    qt = set(re.findall(r'\w+', q))
    best, best_score = None, 0
    for name in KARACHI_AREAS:
        score = len(qt & set(re.findall(r'\w+', name.lower())))
        if score > best_score: best_score, best = score, name
    if best_score >= 1: return best
    best, best_ratio = None, 0.0
    for name in KARACHI_AREAS:
        r = SequenceMatcher(None, q, name.lower()).ratio()
        if r > best_ratio: best_ratio, best = r, name
    return best if best_ratio >= 0.5 else None


def parse_price(text):
    if not text: return None
    text = text.strip().replace(",","").replace("PKR","").replace("Rs.","").replace("Rs","").strip()
    m = re.search(r'([\d.]+)\s*crore', text, re.I)
    if m: return int(float(m.group(1)) * 10_000_000)
    m = re.search(r'([\d.]+)\s*la(?:kh|c)', text, re.I)
    if m: return int(float(m.group(1)) * 100_000)
    m = re.search(r'([\d.]+)\s*thousand', text, re.I)
    if m: return int(float(m.group(1)) * 1_000)
    m = re.search(r'[\d.]+', text)
    return int(float(m.group(0))) if m else None


def build_url(area=None, property_type=None, bedrooms=None, price_min=None, price_max=None, furnished=None, page=1, sort=None):
    ptype_slug = "Rentals"
    if property_type and property_type.lower() in PROPERTY_TYPES:
        ptype_slug = PROPERTY_TYPES[property_type.lower()]["slug"]
    area_slug, area_id = "Karachi", 2
    if area:
        matched = match_area(area)
        if matched: area_slug, area_id = KARACHI_AREAS[matched][:2]
    url = f"https://www.zameen.com/{ptype_slug}/{area_slug}-{area_id}-{page}.html"
    params = {}
    if bedrooms is not None: params["beds_in"] = str(bedrooms)
    if price_min is not None: params["price_min"] = str(price_min)
    if price_max is not None: params["price_max"] = str(price_max)
    if furnished: params["furnishing"] = "furnished"
    if sort:
        sm = {"price_low":"price_asc","price_high":"price_desc","newest":"date_desc"}
        if sort in sm: params["sort"] = sm[sort]
    if params: url += "?" + urlencode(params)
    return url


# --- Claude / Instructor NLP ---

class RentalFilters(BaseModel):
    """Structured rental search filters extracted from a natural language query."""
    area: Optional[str] = Field(None, description="Area name in Karachi (use exact English name from available list)")
    property_type: Optional[Literal["house", "apartment", "upper_portion", "lower_portion", "room", "penthouse", "farm_house"]] = Field(None, description="Property type key")
    bedrooms: Optional[int] = Field(None, ge=1, le=10, description="Number of bedrooms")
    price_min: Optional[int] = Field(None, ge=0, description="Minimum price in PKR")
    price_max: Optional[int] = Field(None, ge=0, description="Maximum price in PKR")
    furnished: Optional[bool] = Field(None, description="Whether the property must be furnished")
    sort: Optional[Literal["price_low", "price_high", "newest"]] = Field(None, description="Sort order")


_NLQ_SYSTEM = """You extract Karachi rental search filters from natural language queries.
The user may write in English, Roman Urdu (Urdu in Latin script), or Urdu script.

AVAILABLE AREAS: {areas}

Price shorthand: 50k=50000, 1.5lac=150000, 2lakh=200000, 50hazar=50000.
Roman Urdu: ghar=house, flat/apartment=apartment, bala hissa=upper_portion, nichla hissa=lower_portion, kamra=room, sasta=price_low, mehenga=price_high, naya=newest.
Urdu: گھر=house, فلیٹ=apartment, بالا حصہ=upper_portion, نچلا حصہ=lower_portion, کمرہ=room, فرنشڈ=furnished.

Only include fields you are confident about. Omit anything not mentioned."""

_instructor_client = None

def _get_instructor_client():
    global _instructor_client
    if _instructor_client is None:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            return None
        _instructor_client = instructor.from_anthropic(anthropic.Anthropic(api_key=api_key))
    return _instructor_client


async def parse_query_with_claude(query: str) -> dict:
    """Use Instructor + Claude Haiku to parse a natural language rental query."""
    client = _get_instructor_client()
    if client is None:
        return parse_natural_query(query)

    ck = cache_key(nlq=query)
    cached = cache_get(ck)
    if cached is not None:
        return cached

    areas_list = ", ".join(sorted(KARACHI_AREAS.keys()))

    try:
        filters = await asyncio.to_thread(
            client.messages.create,
            model="claude-haiku-4-5-20251001",
            max_tokens=256,
            system=_NLQ_SYSTEM.format(areas=areas_list),
            messages=[{"role": "user", "content": query}],
            response_model=RentalFilters,
        )
        result = filters.model_dump(exclude_none=True)
        if "area" in result and result["area"] not in KARACHI_AREAS:
            matched = match_area(result["area"])
            result["area"] = matched if matched else result.pop("area", None)
            if result.get("area") is None:
                result.pop("area", None)

        cache_set(ck, result)
        return result
    except Exception as e:
        logger.warning(f"Instructor parse failed, falling back to regex: {e}")
        return parse_natural_query(query)
