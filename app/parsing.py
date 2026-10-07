"""NLP query parsing, area matching, price parsing, and URL building."""
import asyncio, logging, os, re
from difflib import SequenceMatcher
from typing import Literal, Optional
from urllib.parse import urlencode

import anthropic
import instructor
from pydantic import BaseModel, Field

from app.data import (
    KARACHI_AREAS, PROPERTY_TYPES, CITIES, CITY_AREAS, get_areas,
    URDU_AREAS, ROMAN_URDU_AREAS,
    URDU_TYPES, ROMAN_URDU_TYPES,
    ROMAN_URDU_AREAS_BY_CITY, LANDMARKS,
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


def resolve_landmark(query: str, city: str = "lahore") -> Optional[str]:
    """Return area name if query contains a known landmark for this city."""
    city_landmarks = LANDMARKS.get(city, {})
    ql = query.lower()
    # Try longest-match first to avoid partial matches.
    # Use word boundary for short landmarks to prevent false positives
    # (e.g. "uet" inside "bouquet", "qau" inside other words).
    for landmark in sorted(city_landmarks, key=len, reverse=True):
        if len(landmark) <= 4:
            if re.search(r'\b' + re.escape(landmark) + r'\b', ql):
                return city_landmarks[landmark]
        else:
            if landmark in ql:
                return city_landmarks[landmark]
    return None


_AREA_NOISE = frozenset({
    'furnished', 'furnish', 'cheap', 'sasta', 'mehenga', 'naya', 'studio',
    'bedroom', 'bedrooms', 'bed', 'beds', 'br', 'bhk',
    'flat', 'house', 'ghar', 'makan', 'makaan', 'kamra', 'room',
    'apartment', 'portion', 'upper', 'lower', 'bala', 'nichla',
    'ooper', 'upar', 'uper', 'neechay', 'neeche', 'nichay',
    'luxury', 'premium', 'budget', 'affordable', 'expensive',
    'newest', 'latest', 'new', 'recent',
    'under', 'below', 'above', 'over', 'upto', 'from', 'tak',
    'mein', 'me', 'main', 'ka', 'ke', 'ki', 'in', 'for', 'se',
    'rent', 'rental', 'rentals',
    'marla', 'kanal', 'hazar', 'hazaar', 'lac', 'lakh', 'lacs', 'crore',
    'gaz', 'gaj', 'guz', 'gajj', 'yard', 'yards', 'sqyd', 'sq', 'square',
    'near', 'thousand', 'to', 'or', 'and', 'aur', 'ya', 'the', 'with', 'wala', 'wali',
})


def _strip_noise_tokens(text: str, keep_digits: bool = False) -> str:
    """Remove known filter-noise tokens from text, leaving potential area words.

    ``keep_digits`` keeps bare numbers such as the 5 in "clifton blok 5";
    match_area only lets a number decide between areas that contain one.
    """
    return ' '.join(
        t for t in text.split()
        if t not in _AREA_NOISE and (t.isdigit() and keep_digits or not t.isdigit() and len(t) > 1)
    )


_BED_RANGE_RE = re.compile(r'(\d+)\s*(?:-|to|se)\s*(\d+)\s*(?:bed(?:room)?s?|br|bhk|kamr[eao]|کمر[ےوں]|بیڈ)')
_BED_SINGLE_RE = re.compile(r'(\d+)\s*(?:bed(?:room)?s?|br|bhk|kamr[eao]|کمر[ےوں]|بیڈ)')

# Units: marla/kanal (Punjab) + square-yard family / gaz (Karachi). Longer forms
# are listed before "yards?" so they match fully.
# Bare "yards" is intentionally excluded — it's ambiguous with distance
# ("100 yards from beach"). Karachi size is captured via gaz / sq yd / square yards.
_SIZE_UNIT_PAT = r'(kanal|marla|gaz|gaj|guz|gajj|square\s*yards?|sq\.?\s*yards?|sq\.?\s*yd)'
_SIZE_RANGE_RE = re.compile(
    rf'([\d.]+)\s*{_SIZE_UNIT_PAT}\s*(?:se|to|-)\s*([\d.]+)\s*{_SIZE_UNIT_PAT}', re.I
)
_SIZE_SINGLE_RE = re.compile(rf'([\d.]+)\s*{_SIZE_UNIT_PAT}', re.I)

# Square-yard family — all mean "sq yd". 1 Marla = 25 Sq Yd (matches the backend
# area_size conversion), so sq-yd values are divided by 25 to reach marla.
_SQYD_UNITS = {'gaz', 'gaj', 'guz', 'gajj', 'yard', 'yards',
               'sqyd', 'sqyard', 'sqyards', 'squareyard', 'squareyards'}


def _parse_size_value(num: str, unit: str) -> Optional[float]:
    """Convert a number + unit (marla/kanal/square-yard) to marla."""
    try:
        v = float(num)
    except ValueError:
        return None
    u = re.sub(r'[\s.]', '', unit.lower())  # "sq. yd" -> "sqyd"
    if u == 'kanal':
        return v * 20
    if u in _SQYD_UNITS:
        return v / 25.0
    return v


# --- Spoken numbers --------------------------------------------------------
# Voice search transcribes "two bed" as "do bed" / "دو بیڈ" and "50 thousand"
# as "pachas hazar" / "پچاس ہزار". Number words become digits only when a bed,
# room, size or money unit follows, so "saath" ("with") and "do" stay words.
_NUMBER_WORDS = {
    # Roman Urdu
    "ek": 1, "aik": 1, "do": 2, "teen": 3, "tin": 3, "char": 4, "chaar": 4,
    "panch": 5, "paanch": 5, "chay": 6, "chhe": 6, "che": 6, "saat": 7, "aath": 8, "ath": 8,
    "das": 10, "pandrah": 15, "bees": 20, "pachees": 25, "tees": 30, "paintees": 35,
    "chalees": 40, "chalis": 40, "paintalees": 45, "pachas": 50, "pachaas": 50,
    "pachpan": 55, "saath": 60, "sath": 60, "painsath": 65, "sattar": 70, "pachattar": 75,
    "assi": 80, "assee": 80, "nabbe": 90, "nabbay": 90, "sau": 100,
    # English
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
    "nine": 9, "ten": 10, "fifteen": 15, "twenty": 20, "twenty-five": 25, "thirty": 30,
    "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
    "hundred": 100,
    # Urdu script
    "ایک": 1, "دو": 2, "تین": 3, "چار": 4, "پانچ": 5, "چھ": 6, "سات": 7, "آٹھ": 8, "نو": 9,
    "دس": 10, "پندرہ": 15, "بیس": 20, "پچیس": 25, "تیس": 30, "پینتیس": 35, "چالیس": 40,
    "پینتالیس": 45, "پچاس": 50, "پچپن": 55, "ساٹھ": 60, "پینسٹھ": 65, "ستر": 70,
    "پچھتر": 75, "اسی": 80, "نوے": 90, "سو": 100,
}
# Words that are a number on their own: dedh = 1.5, dhai = 2.5.
_FRACTION_WORDS = {"dedh": 1.5, "derh": 1.5, "ڈیڑھ": 1.5, "dhai": 2.5, "adhai": 2.5, "ڈھائی": 2.5}
# Modifiers before a number word: sade teen = 3.5, sawa do = 2.25.
_NUMBER_MODIFIERS = {"sade": 0.5, "saade": 0.5, "ساڑھے": 0.5, "sawa": 0.25, "سوا": 0.25}
_URDU_UNITS = {"ہزار": "hazar", "لاکھ": "lakh", "کروڑ": "crore"}
_NUMBER_UNIT = (r"(?:bed(?:room)?s?|br|bhk|kamr\w*|rooms?|hazar|hazaar|thousand|k\b|"
                r"lakh|lac|lacs|laakh|crore|cr\b|marla|kanal|بیڈ|کمر\w*|مرلہ|کنال)")
_DIGIT_TABLE = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def _format_number(value):
    return str(int(value)) if value == int(value) else f"{value:g}"


def _normalize_number_words(text: str) -> str:
    """Rewrite spoken numbers as digits when a unit follows ("do bed" -> "2 bed")."""
    text = text.translate(_DIGIT_TABLE)
    for urdu, roman in _URDU_UNITS.items():
        text = text.replace(urdu, f" {roman} ")
    words = "|".join(re.escape(w) for w in sorted(_NUMBER_WORDS, key=len, reverse=True))
    fractions = "|".join(re.escape(w) for w in _FRACTION_WORDS)
    modifiers = "|".join(re.escape(w) for w in _NUMBER_MODIFIERS)
    number = rf"(?:(?:({modifiers})\s+)?({words})|({fractions}))"
    # A number word followed by a unit, or by "se/to/-" and a second number + unit.
    pattern = re.compile(
        rf"(?<!\w){number}(?=\s*(?:(?:se|to|-|سے)\s*(?:{number}|\d+)\s*)?{_NUMBER_UNIT})",
        re.I,
    )

    def value(mod, word, frac):
        if frac:
            return _FRACTION_WORDS[frac.lower()]
        return _NUMBER_WORDS[word.lower()] + (_NUMBER_MODIFIERS[mod.lower()] if mod else 0)

    def repl(m):
        return _format_number(value(m.group(1), m.group(2), m.group(3)))

    # Run twice so both ends of a range ("tees se pachas hazar") are rewritten.
    for _ in range(2):
        text = pattern.sub(repl, text)
    return re.sub(r"\s+", " ", text).strip()


def parse_natural_query(query: str, city: str = "lahore") -> dict:
    """Parse a natural language rental query into structured filters.
    Supports English, Roman Urdu, and Urdu script."""
    result = {}
    q = _normalize_number_words(query.strip())
    if not q:
        return result
    ql = q.lower()
    areas = get_areas(city)

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

    # --- Bedrooms (with range support) ---
    # Strip matched bed tokens from ql so price regex doesn't consume "2-3" from "2-3 bed"
    m = _BED_RANGE_RE.search(ql)
    if m:
        result['bedrooms'] = min(int(m.group(1)), 10)
        result['bedrooms_max'] = min(int(m.group(2)), 10)
        if result['bedrooms_max'] <= result['bedrooms']:
            result.pop('bedrooms_max', None)
        ql = ql[:m.start()] + ' ' + ql[m.end():]
    else:
        m = _BED_SINGLE_RE.search(ql)
        if m:
            result['bedrooms'] = min(int(m.group(1)), 10)
            ql = ql[:m.start()] + ' ' + ql[m.end():]
        elif re.search(r'\b(?:studio|اسٹوڈیو)\b', q, re.I):
            result['bedrooms'] = 1

    # --- Size (marla/kanal) — strip matched tokens so price regex won't consume them ---
    sm = _SIZE_RANGE_RE.search(ql)
    if sm:
        v1 = _parse_size_value(sm.group(1), sm.group(2))
        v2 = _parse_size_value(sm.group(3), sm.group(4))
        if v1 is not None:
            result['size_marla_min'] = v1
        if v2 is not None:
            result['size_marla_max'] = v2
        ql = ql[:sm.start()] + ' ' + ql[sm.end():]
    else:
        sm = _SIZE_SINGLE_RE.search(ql)
        if sm:
            v = _parse_size_value(sm.group(1), sm.group(2))
            if v is not None:
                result['size_marla_min'] = v
            ql = ql[:sm.start()] + ' ' + ql[sm.end():]

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
    m2 = None
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
            else:
                # "house for 45000", "budget 60k": a plain amount is a ceiling.
                # Needs 4+ digits or a unit so "flat for 2 people" isn't a price.
                m = re.search(r'\b(?:for|budget(?:\s*of)?)\s*(?:rs\.?\s*)?(\d{4,9}|[\d.]+\s*(?:k|lac|lakh|lacs|laakh|hazar|hazaar|crore|cr)\b)', ql)
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
    # Exact Urdu names, Roman Urdu aliases and area names, longest match first,
    # so "clifton block 5" beats the shorter alias "clifton".
    spans = _area_spans(q.lower(), city)
    if spans:
        result['area'] = spans[0][2]
    # Landmark resolution
    if 'area' not in result:
        lm = resolve_landmark(q, city=city)
        if lm:
            result['area'] = lm
    # Last resort: fuzzy match via match_area on stripped query
    if 'area' not in result:
        # Remove only amounts actually consumed by the price parser. A budget
        # must not compete with the block number in a fuzzy area query.
        area_text = ql
        for price_match in sorted((match for match in (m, m2) if match),
                                  key=lambda match: match.start(), reverse=True):
            area_text = area_text[:price_match.start()] + ' ' + area_text[price_match.end():]
        stripped = _strip_noise_tokens(area_text, keep_digits=True)
        if len(stripped) >= 3:
            candidate = match_area(stripped, city=city)
            if candidate:
                result['area'] = candidate

    # "DHA or Clifton": several named areas joined by or/and/ya/aur/comma.
    # Search the unconsumed query: `ql` has had bed/size/furnished text cut
    # out, so its offsets don't line up with spans found in the original.
    mentioned = _area_mentions(q.lower(), city)
    if len(mentioned) >= 2:
        result['areas'] = mentioned
        result['area'] = mentioned[0]

    return result


_AREA_JOINER_RE = re.compile(r'^\s*(?:,|/|&|\bor\b|\band\b|\bya\b|\baur\b|\bphir\b|یا|اور)[\s,]*(?:\bor\b|\bthen\b)?\s*$')


def _area_mentions(text, city):
    """Distinct areas named in ``text``, in order, when joined like 'X or Y'.

    Only exact aliases and area names count; fuzzy matches never add a second
    area. Every span and joiner check indexes ``text``, one lowercased string.
    """
    kept = _area_spans(text, city)
    areas = []
    for i, (start, end, name) in enumerate(kept):
        if i and not _AREA_JOINER_RE.match(text[kept[i - 1][1]:start]):
            break
        if name not in areas:
            areas.append(name)
    return areas


_UNIT_AFTER_NUMBER_RE = re.compile(
    r'\s*(?:marla|kanal|gaz|gaj|guz|gajj|sq|square|yards?|bed|beds|bedroom|bedrooms|br|bhk|kamr'
    r'|lac|lacs|lakh|laakh|k\b|hazar|hazaar|thousand|crore|cr\b|بیڈ|کمر|مرلہ)'
)


def _area_spans(text, city):
    """Non-overlapping exact area mentions in ``text`` as (start, end, area), in order.

    Overlapping matches keep the longest (so 'dha phase 6' beats 'dha').
    """
    spans = []
    roman_map = ROMAN_URDU_AREAS_BY_CITY.get(city, {})
    for alias, area_name in roman_map.items():
        for m in re.finditer(r'\b' + re.escape(alias) + r'\b', text):
            spans.append((m.start(), m.end(), area_name))
    for name in get_areas(city):
        nl = ' '.join(name.lower().split())
        if len(nl) < 3:
            continue
        for m in re.finditer(r'\b' + re.escape(nl) + r'\b', text):
            spans.append((m.start(), m.end(), name))
    if city == "karachi":
        for ur_area, en_area in URDU_AREAS.items():
            for m in re.finditer(re.escape(ur_area), text):
                spans.append((m.start(), m.end(), en_area))
    # "askari 5 marla": the 5 is a size, so the area is Askari, not Askari 5.
    spans = [
        (start, end, name) for start, end, name in spans
        if not (text[start:end].split()[-1].isdigit() and _UNIT_AFTER_NUMBER_RE.match(text, end))
    ]
    # Longest first, then drop anything overlapping a kept span.
    kept = []
    for start, end, name in sorted(spans, key=lambda s: (-(s[1] - s[0]), s[0])):
        if all(end <= ks or start >= ke for ks, ke, _ in kept):
            kept.append((start, end, name))
    kept.sort()
    return kept


def match_area(query, city="lahore"):
    areas = get_areas(city)
    q = query.strip()
    if not q:
        return None
    # 1. Exact Urdu match (Karachi only for now)
    if city == "karachi":
        for ur, en in URDU_AREAS.items():
            if ur == q: return en
        # 2. Fuzzy Urdu match
        for ur, en in URDU_AREAS.items():
            if q in ur or ur in q: return en
    ql = q.lower()
    qn = _norm(ql)
    # An exact area name always wins over aliases that merely contain it.
    for name in areas:
        if _norm(name) == qn: return name
    # 3. Roman Urdu alias match (city-aware)
    roman_map = ROMAN_URDU_AREAS_BY_CITY.get(city, {})
    if roman_map:
        if ql in roman_map:
            return roman_map[ql]
        for alias, area_name in sorted(roman_map.items(), key=lambda x: -len(x[0])):
            if alias in ql or ql in alias:
                return area_name
    # 5. Substring match — prefer shorter (more specific) matches
    candidates = []
    for name in areas:
        nl = _norm(name)
        if (len(qn) >= 3 and qn in nl) or (len(nl) >= 3 and nl in qn):
            candidates.append(name)
    if candidates:
        candidates.sort(key=lambda n: abs(len(n) - len(q)))
        return candidates[0]
    # 6. Distinctive-token match. Generic words ("town", "block") never decide
    # the area on their own: "johr town" must not become "Agrics Town".
    q_tokens = _distinctive_tokens(qn)
    if q_tokens:
        best, best_score = None, 0.0
        for name in areas:
            n_tokens = _distinctive_tokens(_norm(name))
            if not n_tokens:
                continue
            # A number must match exactly in a numbered area ("block 5" is
            # never "Block 1") and is ignored for unnumbered ones (a price).
            n_numbered = any(t.isdigit() for t in n_tokens)
            considered = [t for t in q_tokens if n_numbered or not t.isdigit()]
            if not considered:
                continue
            matched = [max(_token_ratio(t, nt) for nt in n_tokens) for t in considered]
            if min(matched) < _TOKEN_MATCH_MIN:
                continue
            score = sum(matched) / max(len(considered), len(n_tokens))
            if score > best_score:
                best_score, best = score, name
        if best_score >= 0.5:
            return best
    # 7. Whole-string similarity, strict: a wrong area is worse than none.
    best, best_ratio = None, 0.0
    for name in areas:
        r = SequenceMatcher(None, qn, _norm(name)).ratio()
        if r > best_ratio: best_ratio, best = r, name
    return best if best_ratio >= 0.8 else None


# Words shared by many area names; they can't identify an area by themselves.
_GENERIC_AREA_TOKENS = frozenset({
    'town', 'block', 'phase', 'sector', 'society', 'colony', 'city', 'scheme',
    'housing', 'road', 'area', 'garden', 'gardens', 'park', 'enclave', 'extension',
    'ext', 'commercial', 'cooperative', 'co', 'operative', 'the', 'new', 'old',
    'e', 'i', 'of', 'and', 'amp', 'residency', 'homes', 'villas', 'avenue',
    'blok', 'blk', 'sec',
})
_TOKEN_MATCH_MIN = 0.8


def _norm(text):
    """Lowercase and collapse whitespace ('Defence  DHA  Phase 6' -> 'defence dha phase 6')."""
    return ' '.join(text.lower().split())


def _distinctive_tokens(text):
    return {t for t in re.findall(r'\w+', text) if t not in _GENERIC_AREA_TOKENS}


def _token_ratio(a, b):
    if a == b:
        return 1.0
    if a.isdigit() or b.isdigit():
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def suggest_areas(query, city="lahore", limit=3):
    """Closest area names for a "did you mean" prompt when match_area finds nothing."""
    qn = _norm(query)
    q_tokens = _distinctive_tokens(qn)
    if not q_tokens:
        return []
    scored = []
    for name in get_areas(city):
        nn = _norm(name)
        n_tokens = _distinctive_tokens(nn)
        if not n_tokens:
            continue
        token_score = sum(max(_token_ratio(t, nt) for nt in n_tokens) for t in q_tokens) / len(q_tokens)
        score = max(token_score, SequenceMatcher(None, qn, nn).ratio())
        if score >= 0.6:
            scored.append((-score, len(name), name))
    return [name for _, _, name in sorted(scored)[:limit]]


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


def build_url(area=None, property_type=None, bedrooms=None, bedrooms_max=None, price_min=None, price_max=None, furnished=None, page=1, sort=None, city="lahore"):
    ptype_slug = "Rentals"
    if property_type and property_type.lower() in PROPERTY_TYPES:
        ptype_slug = PROPERTY_TYPES[property_type.lower()]["slug"]
    city_info = CITIES.get(city, CITIES["lahore"])
    areas = get_areas(city)
    area_slug, area_id = city_info["name"], city_info["id"]
    if area:
        matched = match_area(area, city=city)
        if matched: area_slug, area_id = areas[matched][:2]
    url = f"https://www.zameen.com/{ptype_slug}/{area_slug}-{area_id}-{page}.html"
    params = {}
    if bedrooms is not None:
        if bedrooms_max is not None and bedrooms_max > bedrooms:
            params["beds_in"] = ",".join(str(b) for b in range(bedrooms, bedrooms_max + 1))
        else:
            params["beds_in"] = str(bedrooms)
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
    area: Optional[str] = Field(None, description="Area name (use exact English name from AVAILABLE AREAS list)")
    property_type: Optional[Literal["house", "apartment", "upper_portion", "lower_portion", "room", "penthouse", "farm_house"]] = Field(None, description="Property type key")
    bedrooms: Optional[int] = Field(None, ge=1, le=10, description="Minimum (or exact) number of bedrooms")
    bedrooms_max: Optional[int] = Field(None, ge=1, le=10, description="Maximum bedrooms for range queries like '2-3 beds'. Omit for single values.")
    price_min: Optional[int] = Field(None, ge=0, description="Minimum monthly rent in PKR")
    price_max: Optional[int] = Field(None, ge=0, description="Maximum monthly rent in PKR")
    size_marla_min: Optional[float] = Field(None, ge=0, description="Minimum property size in marla. 1 kanal = 20 marla.")
    size_marla_max: Optional[float] = Field(None, ge=0, description="Maximum property size in marla.")
    furnished: Optional[bool] = Field(None, description="Whether the property must be furnished")
    sort: Optional[Literal["price_low", "price_high", "newest"]] = Field(None, description="Sort order")
    city_hint: Optional[Literal["karachi", "lahore", "islamabad"]] = Field(None, description="Only set if query explicitly names a city or an area unambiguously tied to one city. Omit if ambiguous.")


_NLQ_SYSTEM = """\
You are a rental property search assistant for Pakistan. \
Extract structured search filters from the user's query. \
The user may write in English, Roman Urdu, or Urdu script.

CURRENT CITY: {city}
AVAILABLE AREAS FOR THIS CITY: {areas}

FIELD RULES:
area: Pick the closest match from AVAILABLE AREAS. If the user mentions a sub-block not in the list, return the parent area. Return the exact English name only.

property_type: house | apartment | upper_portion | lower_portion | room | penthouse | farm_house
  Roman Urdu: ghar/makan=house, flat/apartment=apartment, bala hissa/ooper portion/upar ka portion=upper_portion, nichla hissa/neechay portion=lower_portion, kamra=room
  Urdu: گھر=house, فلیٹ=apartment, بالا حصہ=upper_portion, نچلا حصہ=lower_portion, کمرہ=room

bedrooms / bedrooms_max: "2 bed" => bedrooms=2. "2-3 bed" => bedrooms=2, bedrooms_max=3. "studio" => bedrooms=1.

price_min / price_max (monthly rent in PKR): 50k=50000, 1.5lac=150000, 50hazar=50000, 1crore=10000000. "under 50k" => price_max=50000. "30k to 60k" => price_min=30000, price_max=60000.

size_marla_min / size_marla_max (property size; 1 kanal = 20 marla): "5 marla" => size_marla_min=5. "1 kanal" => size_marla_min=20. "5-10 marla" => size_marla_min=5, size_marla_max=10.

furnished: true only if explicitly requested.
sort: price_low (sasta/cheap/budget), price_high (expensive/mehenga/luxury), newest (naya/latest/recent).
city_hint: Return "karachi"/"lahore"/"islamabad" ONLY when the query explicitly names a city or references an area unambiguously tied to one city.

EXAMPLES:
Q: "gulshan e iqbal block 13 mein ooper ka portion 150k tak"
A: {{"area":"Gulshan-e-Iqbal","property_type":"upper_portion","price_max":150000}}

Q: "DHA phase 8 mein 250 se 300k tak ka neechay ka portion"
A: {{"area":"DHA Phase 8","property_type":"lower_portion","price_min":250000,"price_max":300000}}

Q: "2-3 bed flat in Clifton under 80k"
A: {{"area":"Clifton","property_type":"apartment","bedrooms":2,"bedrooms_max":3,"price_max":80000}}

Q: "5 marla furnished house in Bahria Town Lahore under 60k"
A: {{"area":"Bahria Town","property_type":"house","furnished":true,"price_max":60000,"size_marla_min":5,"city_hint":"lahore"}}

Q: "1 kanal house in DHA Lahore"
A: {{"area":"DHA Defence","property_type":"house","size_marla_min":20,"city_hint":"lahore"}}

Q: "F-8 mein 2 bed flat 40 se 70 hazar"
A: {{"area":"F 8","property_type":"apartment","bedrooms":2,"price_min":40000,"price_max":70000}}

Q: "G-11 main sasta kamra"
A: {{"area":"G 11","property_type":"room","sort":"price_low"}}

Q: "3 bed furnished apartment Gulberg Lahore below 1.2lac"
A: {{"area":"Gulberg","property_type":"apartment","bedrooms":3,"furnished":true,"price_max":120000,"city_hint":"lahore"}}

Q: "naya flat Johar Town 2 kamray"
A: {{"area":"Johar Town","property_type":"apartment","bedrooms":2,"sort":"newest"}}

Q: "5 se 10 marla ghar Defence Karachi 40k to 80k"
A: {{"area":"DHA Defence","property_type":"house","size_marla_min":5,"size_marla_max":10,"price_min":40000,"price_max":80000}}

Q: "studio apartment in Islamabad under 35k"
A: {{"property_type":"apartment","bedrooms":1,"price_max":35000,"city_hint":"islamabad"}}

Q: "mehenga furnished penthouse clifton"
A: {{"area":"Clifton","property_type":"penthouse","furnished":true,"sort":"price_high"}}

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


async def parse_query_with_claude(query: str, city: str = "lahore") -> dict:
    """Use Instructor + Claude Haiku to parse a natural language rental query."""
    client = _get_instructor_client()
    if client is None:
        return parse_natural_query(query, city=city)

    ck = cache_key(nlq=query, city=city)
    cached = cache_get(ck)
    if cached is not None:
        return cached

    areas = get_areas(city)
    areas_list = ", ".join(sorted(areas.keys()))

    try:
        filters = await asyncio.to_thread(
            client.messages.create,
            model="claude-haiku-4-5-20251001",
            max_tokens=256,
            system=_NLQ_SYSTEM.format(city=city.capitalize(), areas=areas_list),
            messages=[{"role": "user", "content": query}],
            response_model=RentalFilters,
        )
        result = filters.model_dump(exclude_none=True)

        # If city_hint differs, re-target area normalization to the hinted city
        effective_city = city
        if "city_hint" in result and result["city_hint"] in CITIES and result["city_hint"] != city:
            effective_city = result["city_hint"]
            areas = get_areas(effective_city)

        # Area normalization
        if "area" in result and result["area"] not in areas:
            matched = match_area(result["area"], city=effective_city)
            result["area"] = matched if matched else result.pop("area", None)
            if result.get("area") is None:
                result.pop("area", None)

        # Landmark fallback if Claude found no area
        if "area" not in result:
            lm = resolve_landmark(query, city=effective_city)
            if lm:
                result["area"] = lm

        # Validate bedrooms_max > bedrooms
        if "bedrooms_max" in result and "bedrooms" in result:
            if result["bedrooms_max"] <= result["bedrooms"]:
                result.pop("bedrooms_max", None)

        # Validate size_marla_max > size_marla_min
        if "size_marla_max" in result and "size_marla_min" in result:
            if result["size_marla_max"] <= result["size_marla_min"]:
                result.pop("size_marla_max", None)

        # Validate city_hint
        if "city_hint" in result and result["city_hint"] not in CITIES:
            result.pop("city_hint", None)

        result["parser"] = "ai"
        cache_set(ck, result)
        return result
    except Exception as e:
        logger.warning(f"Instructor parse failed, falling back to regex: {e}")
        return parse_natural_query(query, city=city)
