"""Zameen.com scraping: HTTP fetching, HTML parsing, and search orchestration."""
import asyncio, json, logging, random, re

import httpx
from bs4 import BeautifulSoup
from fastapi import HTTPException

from app.data import USER_AGENTS
from app.cache import cache_key, cache_get, cache_set, rate_limiter
from app.parsing import build_url, parse_price

logger = logging.getLogger("zameenrentals")


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


def _is_property_photo_url(url):
    """Check if a URL looks like a property photo rather than an agent avatar/logo."""
    # Skip agent/profile/avatar images
    if re.search(r'(agent|user|profile|avatar|logo|brand|company)', url, re.I):
        return False
    # Skip small images — agent logos/avatars are typically small (< 300px)
    m = re.search(r'/(\d+)x(\d+)/', url)
    if m and (int(m.group(1)) < 300 or int(m.group(2)) < 300):
        return False
    return True


def _extract_images(card):
    """Extract property photos only (not agent logos/avatars) from a listing card."""
    images = []
    seen = set()
    # Zameen.com marks property photos with aria-label="Listing photo"
    for img in card.select('img[aria-label="Listing photo"]'):
        for attr in ("src", "data-src", "data-original", "data-lazy-src"):
            url = img.get(attr, "")
            if url and url not in seen and not url.endswith(".svg"):
                url = re.sub(r'/(\d+)x(\d+)/', '/800x600/', url)
                seen.add(url)
                images.append(url)
    # Fallback: picture/source elements (usually property photos)
    if not images:
        for source in card.select("picture source"):
            srcset = source.get("srcset", "")
            for part in srcset.split(","):
                url = part.strip().split(" ")[0]
                if url and "zameen" in url and url not in seen and _is_property_photo_url(url):
                    seen.add(url)
                    images.append(url)
    # Last resort: first img inside the main link (property image area, not agent section)
    if not images:
        # Property photos are typically inside the first <a> tag of the card
        main_link = card.select_one('a[href*="/Property/"]') or card.select_one('a[href]')
        if main_link:
            for img in main_link.select("img"):
                url = img.get("src", "") or img.get("data-src", "")
                if url and url not in seen and not url.endswith(".svg") and _is_property_photo_url(url):
                    url = re.sub(r'/(\d+)x(\d+)/', '/800x600/', url)
                    seen.add(url)
                    images.append(url)
                    break
    return images


def _extract_property_type(card):
    """Try to detect property type from listing card content."""
    text = card.get_text(" ", strip=True).lower()
    # Use regex patterns — order matters: specific types first, generic last
    type_patterns = [
        (r"penthouse", "Penthouse"),
        (r"farm\s*house", "Farm House"),
        (r"upper\s+portion", "Upper Portion"),
        (r"lower\s+portion", "Lower Portion"),
        (r"studio", "Room"),
        (r"\bflat\b", "Apartment"), (r"\bapartment\b", "Apartment"),
        (r"\bhouse\b", "House"), (r"\bbungalow\b", "House"), (r"\bvilla\b", "House"),
        # "room" must come after flat/house/apartment and use word boundary
        # to avoid matching "bedroom"
        (r"(?<!\w)room(?!\w)", "Room"),
    ]
    for pattern, label in type_patterns:
        if re.search(pattern, text):
            return label
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
            # Use only direct text nodes to avoid pulling in nested area-size numbers
            loc_text = "".join(loc_el.find_all(string=True, recursive=False)).strip()
            if not loc_text:
                loc_text = loc_el.get_text(strip=True)
            # Strip trailing digits that may bleed in from adjacent elements
            loc_text = re.sub(r'\d+\s*$', '', loc_text).strip().rstrip(',')
            listing["location"] = loc_text
        else:
            for span in card.select("span, div"):
                t = span.get_text(strip=True)
                if ("DHA" in t or "Commercial" in t or "Karachi" in t or "Block" in t) and 5 < len(t) < 80 and "Thousand" not in t and "sqft" not in t:
                    listing["location"] = t; break
        # Extract all images
        images = _extract_images(card)
        if images:
            listing["image_url"] = images[0]
            if len(images) > 1:
                listing["images"] = images
        # Property type detection
        ptype = _extract_property_type(card)
        if ptype:
            listing["property_type"] = ptype
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
                    # Try to get images from structured data
                    img = item.get("image", "")
                    if isinstance(img, list):
                        l["image_url"] = img[0] if img else ""
                        if len(img) > 1: l["images"] = img
                    elif img:
                        l["image_url"] = img
                    if l.get("title"): listings.append(l)
            except: continue
    return listings


async def search_zameen(area=None, property_type=None, bedrooms=None, price_min=None, price_max=None, furnished=None, page=1, sort=None):
    ck = cache_key(area=area, property_type=property_type, bedrooms=bedrooms, price_min=price_min, price_max=price_max, furnished=furnished, page=page, sort=sort)
    cached = cache_get(ck)
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
    cache_set(ck, result)
    return result
