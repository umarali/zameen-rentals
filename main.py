"""
RentKarachi — Fast Zameen.com rental search API + web app.
Run: uvicorn main:app --reload --port 8000
Open: http://localhost:8000
"""
import asyncio, hashlib, json, logging, random, re, time
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode
import httpx
from bs4 import BeautifulSoup
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("zameenrentals")
app = FastAPI(title="ZameenRentals", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

KARACHI_AREAS = {
    "DHA Defence": ("Karachi_DHA_Defence", 213),
    "DHA Phase 1": ("Karachi_DHA_Defence_DHA_Phase_1", 1478),
    "DHA Phase 2 Extension": ("Karachi_DHA_Defence_DHA_Phase_2_Extension", 1672),
    "DHA Phase 7 Extension": ("Karachi_DHA_Defence_DHA_Phase_7_Extension", 1674),
    "DHA City Karachi": ("Karachi_DHA_City_Karachi", 1429),
    "Clifton": ("Karachi_Clifton", 5),
    "Clifton Block 2": ("Karachi_Clifton_Block_2", 1664),
    "Clifton Block 5": ("Karachi_Clifton_Block_5", 1667),
    "Clifton Block 8": ("Karachi_Clifton_Block_8", 1670),
    "Clifton Block 9": ("Karachi_Clifton_Block_9", 1671),
    "Sea View Apartments": ("Karachi_Sea_View_Apartments", 7292),
    "Gulshan-e-Iqbal": ("Karachi_Gulshan_e_Iqbal", 233),
    "Gulshan-e-Iqbal Town": ("Karachi_Gulshan_e_Iqbal_Town", 6858),
    "Gulistan-e-Jauhar": ("Karachi_Gulistan_e_Jauhar", 232),
    "Gulistan-e-Jauhar Block 1": ("Karachi_Gulistan_e_Jauhar_Block_1", 6823),
    "Gulistan-e-Jauhar Block 2": ("Karachi_Gulistan_e_Jauhar_Block_2", 6825),
    "Bahria Town Karachi": ("Karachi_Bahria_Town_Karachi", 8298),
    "North Nazimabad": ("Karachi_North_Nazimabad", 11),
    "North Nazimabad Block A": ("Karachi_North_Nazimabad_Block_A", 7209),
    "North Nazimabad Block H": ("Karachi_North_Nazimabad_Block_H", 7216),
    "Nazimabad": ("Karachi_Nazimabad", 278),
    "Federal B Area": ("Karachi_Federal_B._Area", 12),
    "North Karachi": ("Karachi_North_Karachi", 282),
    "Malir": ("Karachi_Malir", 476),
    "Korangi": ("Karachi_Korangi", 255),
    "Scheme 33": ("Karachi_Scheme_33", 495),
    "Saddar": ("Karachi_Saddar_Town", 7269),
    "Garden West": ("Karachi_Garden_West", 10984),
    "Shah Faisal Town": ("Karachi_Shah_Faisal_Town", 774),
    "Tariq Road": ("Karachi_Tariq_Road", 532),
    "Gulshan-e-Maymar": ("Karachi_Gulshan_e_Maymar", 440),
    "Frere Town": ("Karachi_Frere_Town", 224),
    "Bath Island": ("Karachi_Bath_Island", 198),
    "Cantt": ("Karachi_Cantt", 525),
    "Shahra-e-Faisal": ("Karachi_Shahra_e_Faisal", 310),
    "Jamshed Town": ("Karachi_Jamshed_Town", 6916),
    "Hill Park": ("Karachi_Hill_Park", 758),
    "University Road": ("Karachi_University_Road", 324),
    "Naya Nazimabad": ("Karachi_Naya_Nazimabad", 10079),
    "Gizri": ("Karachi_Gizri", 6809),
    "Old Clifton": ("Karachi_Old_Clifton", 9052),
    "Zamzama": ("Karachi_Zamzama", 416),
    "Karachi": ("Karachi", 2),
}

PROPERTY_TYPES = {
    "house": {"label": "House", "slug": "Rentals_Houses_Property"},
    "apartment": {"label": "Apartment / Flat", "slug": "Rentals_Flats_Apartments"},
    "flat": {"label": "Apartment / Flat", "slug": "Rentals_Flats_Apartments"},
    "upper_portion": {"label": "Upper Portion", "slug": "Rentals_Upper_Portions"},
    "lower_portion": {"label": "Lower Portion", "slug": "Rentals_Lower_Portions"},
    "room": {"label": "Room", "slug": "Rentals_Rooms"},
    "penthouse": {"label": "Penthouse", "slug": "Rentals_Penthouse"},
    "farm_house": {"label": "Farm House", "slug": "Rentals_Farm_Houses"},
}

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Version/17.5 Safari/605.1.15",
]

_cache = {}
CACHE_TTL = 300

def _cache_key(**kw):
    return hashlib.md5(json.dumps(kw, sort_keys=True).encode()).hexdigest()

def _cache_get(key):
    if key in _cache:
        ts, data = _cache[key]
        if time.time() - ts < CACHE_TTL: return data
        del _cache[key]
    return None

def _cache_set(key, data):
    _cache[key] = (time.time(), data)
    if len(_cache) > 200:
        for k in sorted(_cache, key=lambda k: _cache[k][0])[:50]: del _cache[k]

class RateLimiter:
    def __init__(self, rate=2.0, burst=3):
        self.rate, self.burst, self.tokens, self.last = rate, burst, float(burst), time.monotonic()
        self._lock = asyncio.Lock()
    async def acquire(self):
        async with self._lock:
            now = time.monotonic()
            self.tokens = min(self.burst, self.tokens + (now - self.last) * self.rate)
            self.last = now
            if self.tokens < 1:
                await asyncio.sleep((1 - self.tokens) / self.rate)
                self.tokens = 0
            else: self.tokens -= 1

rate_limiter = RateLimiter()

def match_area(query):
    q = query.lower().strip()
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
        if matched: area_slug, area_id = KARACHI_AREAS[matched]
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

async def fetch_page(url, client):
    for attempt in range(3):
        try:
            await rate_limiter.acquire()
            headers = {"User-Agent": random.choice(USER_AGENTS), "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8", "Accept-Language": "en-US,en;q=0.9", "Accept-Encoding": "gzip, deflate, br", "Connection": "keep-alive"}
            resp = await client.get(url, headers=headers, timeout=15, follow_redirects=True)
            if resp.status_code == 200: return resp.text
            elif resp.status_code == 429:
                await asyncio.sleep((2**attempt) + random.uniform(1,3))
            else:
                logger.warning(f"HTTP {resp.status_code} for {url}")
                await asyncio.sleep(1)
        except Exception as e:
            logger.error(f"Fetch error: {e}")
            await asyncio.sleep(2**attempt)
    return None

def parse_listings(html):
    soup = BeautifulSoup(html, "html.parser")
    listings = []
    cards = soup.select('li[role="article"]') or soup.select('[class*="listing-card"], article[aria-label]')
    for card in cards:
        listing = {}
        h2 = card.select_one("h2")
        if h2:
            a = h2.select_one("a")
            listing["title"] = (a or h2).get_text(strip=True)
            if a and a.get("href"):
                href = a["href"]
                if not href.startswith("http"): href = "https://www.zameen.com" + href
                listing["url"] = href
        if not listing.get("url"):
            a = card.select_one('a[href*="/Property/"]') or card.select_one("a[href]")
            if a:
                href = a["href"]
                if not href.startswith("http"): href = "https://www.zameen.com" + href
                listing["url"] = href
                if not listing.get("title"): listing["title"] = a.get_text(strip=True)
        price_el = card.select_one('span[aria-label="Price"]') or card.select_one('[class*="price"]')
        if price_el:
            listing["price_text"] = price_el.get_text(strip=True)
            listing["price"] = parse_price(listing["price_text"])
        for label, key in [("Beds","bedrooms"),("Baths","bathrooms")]:
            el = card.select_one(f'span[aria-label="{label}"]')
            if el:
                m = re.search(r'(\d+)', el.get_text(strip=True))
                if m: listing[key] = int(m.group(1))
        area_el = card.select_one('span[aria-label="Area"]')
        if area_el: listing["area_size"] = area_el.get_text(strip=True)
        loc_el = card.select_one('span[aria-label="Location"]')
        if loc_el:
            listing["location"] = loc_el.get_text(strip=True)
        else:
            for span in card.select("span, div"):
                t = span.get_text(strip=True)
                if ("DHA" in t or "Commercial" in t or "Karachi" in t or "Block" in t) and 5 < len(t) < 80 and "Thousand" not in t and "sqft" not in t:
                    listing["location"] = t; break
        img = card.select_one("img[src*='zameen'], img[data-src]")
        if img: listing["image_url"] = img.get("src") or img.get("data-src","")
        for span in card.select("span"):
            t = span.get_text(strip=True).lower()
            if "added" in t or "ago" in t: listing["added"] = span.get_text(strip=True); break
        if listing.get("title") or listing.get("price"): listings.append(listing)
    if not listings:
        for script in soup.select('script[type="application/ld+json"]'):
            try:
                data = json.loads(script.string or "")
                items = data if isinstance(data, list) else [data] if isinstance(data, dict) and data.get("@type") in ("RealEstateListing","Product","Offer") else [i.get("item",i) for i in data.get("itemListElement",[])] if isinstance(data, dict) else []
                for item in items:
                    l = {"title": item.get("name",""), "url": item.get("url","")}
                    if "offers" in item:
                        offer = item["offers"] if isinstance(item["offers"], dict) else item["offers"][0]
                        l["price"] = parse_price(str(offer.get("price","")))
                        l["price_text"] = str(offer.get("price",""))
                    if l.get("title"): listings.append(l)
            except: continue
    return listings

async def search_zameen(area=None, property_type=None, bedrooms=None, price_min=None, price_max=None, furnished=None, page=1, sort=None):
    ck = _cache_key(area=area, property_type=property_type, bedrooms=bedrooms, price_min=price_min, price_max=price_max, furnished=furnished, page=page, sort=sort)
    cached = _cache_get(ck)
    if cached: return cached
    url = build_url(area, property_type, bedrooms, price_min, price_max, furnished, page, sort)
    logger.info(f"Fetching: {url}")
    async with httpx.AsyncClient() as client:
        html = await fetch_page(url, client)
    if not html: raise HTTPException(status_code=502, detail="Could not fetch results from Zameen.com. Try again shortly.")
    listings = parse_listings(html)
    total = len(listings)
    soup = BeautifulSoup(html, "html.parser")
    count_el = soup.select_one('h1, [class*="count"], [class*="total"]')
    if count_el:
        m = re.search(r'(\d[\d,]*)\s+(?:Flats?|Homes?|Houses?|Properties|Rooms?|Portions?|Penthouses?)', count_el.get_text())
        if m: total = int(m.group(1).replace(",",""))
    result = {"total": total, "page": page, "url": url, "results": listings}
    _cache_set(ck, result)
    return result

@app.get("/api/health")
async def health(): return {"status": "ok", "service": "ZameenRentals", "version": "1.0.0"}

@app.get("/api/areas")
async def get_areas():
    return [{"name": n, "slug": s, "id": i} for n, (s, i) in sorted(KARACHI_AREAS.items())]

@app.get("/api/property-types")
async def get_property_types():
    seen, types = set(), []
    for key, info in PROPERTY_TYPES.items():
        if key == "flat": continue
        if info["slug"] not in seen: seen.add(info["slug"]); types.append({"key": key, "label": info["label"]})
    return types

@app.get("/api/search")
async def search(area: Optional[str]=Query(None), property_type: Optional[str]=Query(None), bedrooms: Optional[int]=Query(None, ge=1, le=10), price_min: Optional[int]=Query(None, ge=0), price_max: Optional[int]=Query(None, ge=0), furnished: Optional[bool]=Query(None), page: int=Query(1, ge=1), sort: Optional[str]=Query(None)):
    try: return await search_zameen(area=area, property_type=property_type, bedrooms=bedrooms, price_min=price_min, price_max=price_max, furnished=furnished, page=page, sort=sort)
    except HTTPException: raise
    except Exception as e: logger.error(f"Search error: {e}"); raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
async def serve_frontend():
    p = Path(__file__).parent / "index.html"
    return FileResponse(p, media_type="text/html") if p.exists() else HTMLResponse("<h1>RentKarachi</h1><p>index.html not found</p>")

if __name__ == "__main__":
    import uvicorn; uvicorn.run(app, host="0.0.0.0", port=8000)
