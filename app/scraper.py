"""Zameen.com scraping: HTTP fetching, HTML parsing, and search orchestration."""
import asyncio, json, logging, random, re

import httpx
from bs4 import BeautifulSoup
from fastapi import HTTPException

from app.data import USER_AGENTS, PROPERTY_TYPES
from app.cache import cache_key, cache_get, cache_set, rate_limiter
from app.parsing import build_url, parse_price

logger = logging.getLogger("zameenrentals")


def extract_zameen_id(url: str) -> str | None:
    """Extract the numeric Zameen.com listing ID from a property URL.
    URL pattern: .../Property/slug-{LISTING_ID}-{AREA_ID}-{PAGE}.html
    E.g. '...dha_phase_5_apartment-53921288-1482-4.html' -> '53921288'
    """
    m = re.search(r'-(\d{5,10})-\d+-\d+\.html', url or "")
    return m.group(1) if m else None


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
            # Strip area-size that bleeds in (e.g. "DHA Phase 845292 Sq. Yd.")
            loc_text = re.sub(r'[\d,]+\s*(?:Sq\.?\s*(?:Yd|Ft|M)\.?|Marla|Kanal).*$', '', loc_text, flags=re.I).strip()
            # Strip trailing digits that may bleed in from adjacent elements
            loc_text = re.sub(r'\d+\s*$', '', loc_text).strip().rstrip(',')
            listing["location"] = loc_text
        else:
            for span in card.select("span, div"):
                t = span.get_text(strip=True)
                if ("DHA" in t or "Commercial" in t or "Karachi" in t or "Lahore" in t or "Islamabad" in t or "Block" in t) and 5 < len(t) < 80 and "Thousand" not in t and "sqft" not in t:
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


async def fetch_listing_detail(listing_url):
    """Fetch enriched detail from an individual Zameen.com listing page.
    Returns dict with: description, features, amenities, agent, phone, images, details."""
    ck = cache_key(detail_url=listing_url)
    cached = cache_get(ck)
    if cached is not None:
        return cached

    async with httpx.AsyncClient() as client:
        html = await fetch_page(listing_url, client)
    if not html:
        return None

    soup = BeautifulSoup(html, "html.parser")
    result = {"phone": None, "description": None, "features": [], "amenities": [],
              "agent_name": None, "agent_agency": None, "images": [], "details": {}}

    # --- Phone extraction ---
    phone = None
    tel_link = soup.select_one('a[href^="tel:"]')
    if tel_link:
        phone = tel_link["href"].replace("tel:", "").strip()
    if not phone:
        for script in soup.select('script[type="application/ld+json"]'):
            try:
                data = json.loads(script.string or "")
                items = [data] if isinstance(data, dict) else data if isinstance(data, list) else []
                for item in items:
                    t = item.get("telephone") or item.get("phone")
                    if t: phone = str(t).strip(); break
                    for key in ("seller", "agent", "broker", "offeredBy"):
                        nested = item.get(key, {})
                        if isinstance(nested, dict):
                            t = nested.get("telephone") or nested.get("phone")
                            if t: phone = str(t).strip(); break
                    if phone: break
            except Exception:
                continue
    if not phone:
        for el in soup.select('[aria-label*="phone" i], [aria-label*="call" i], [aria-label*="mobile" i], [class*="phone"], [class*="contact-number"]'):
            text = el.get_text(strip=True)
            m = re.search(r'(\+?92[\d\s-]{9,13}|0\d{2,3}[\s-]?\d{7,8})', text)
            if m: phone = m.group(1).strip(); break
    if not phone:
        body = soup.select_one("body")
        if body:
            text = body.get_text(" ", strip=True)
            m = re.search(r'(\+92[\d\s-]{9,13}|03\d{2}[\s-]?\d{7})', text)
            if m: phone = m.group(1).strip()
    if phone:
        phone = re.sub(r'[\s-]', '', phone)
    result["phone"] = phone

    # --- Description ---
    desc_el = soup.select_one('[aria-label="Description"] div, [class*="description"] p, [class*="body"] p')
    if not desc_el:
        # Try common Zameen.com patterns
        for sel in ['div[class*="Description"] span', 'div[class*="description"]', 'section p']:
            desc_el = soup.select_one(sel)
            if desc_el and len(desc_el.get_text(strip=True)) > 30:
                break
    if desc_el:
        result["description"] = desc_el.get_text("\n", strip=True)[:2000]

    # --- All images (detail page has more than search results) ---
    images = []
    seen = set()
    for img in soup.select('img[src*="media.zameen.com"], img[src*="zameen-media"], img[src*="/property/"], img[aria-label="Listing photo"], img[aria-label="Cover Photo"]'):
        src = img.get("src") or img.get("data-src") or ""
        if not src or not _is_property_photo_url(src):
            continue
        src = re.sub(r'-\d+x\d+\.', '-800x600.', src)
        src = re.sub(r'/\d+x\d+/', '/800x600/', src)
        if src not in seen:
            seen.add(src)
            images.append(src)
    for source in soup.select('picture source[srcset*="media.zameen.com"], picture source[srcset*="zameen-media"], picture source[srcset*="/property/"]'):
        srcset = source.get("srcset", "")
        for part in srcset.split(","):
            url = part.strip().split(" ")[0]
            if url and _is_property_photo_url(url):
                url = re.sub(r'-\d+x\d+\.', '-800x600.', url)
                url = re.sub(r'/\d+x\d+/', '/800x600/', url)
                if url not in seen:
                    seen.add(url)
                    images.append(url)
    if images:
        result["images"] = images

    # --- Features / key details ---
    for li in soup.select('ul[class*="feature"] li, ul[class*="detail"] li, [aria-label="Features"] li'):
        text = li.get_text(strip=True)
        if text and len(text) < 100:
            result["features"].append(text)

    # --- Amenities ---
    for el in soup.select('[class*="amenity"] span, [class*="amenity"] li, [aria-label="Amenities"] li, [aria-label="Amenities"] span'):
        text = el.get_text(strip=True)
        if text and len(text) < 60 and text not in result["amenities"]:
            result["amenities"].append(text)

    # --- Property details (key-value pairs) ---
    for row in soup.select('[class*="detail"] li, table tr, [aria-label*="detail"] div'):
        texts = [t.get_text(strip=True) for t in row.select("span, td, th, dt, dd") if t.get_text(strip=True)]
        if len(texts) == 2 and len(texts[0]) < 40 and len(texts[1]) < 80:
            result["details"][texts[0]] = texts[1]

    # --- Agent info ---
    agent_el = soup.select_one('[class*="agent-name"], [class*="AgentName"], [aria-label*="agent"] [class*="name"]')
    if agent_el:
        result["agent_name"] = agent_el.get_text(strip=True)
    agency_el = soup.select_one('[class*="agency-name"], [class*="AgencyName"], [aria-label*="agency"]')
    if agency_el:
        result["agent_agency"] = agency_el.get_text(strip=True)

    # --- JSON-LD enrichment ---
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            data = json.loads(script.string or "")
            if isinstance(data, dict):
                if not result["description"] and data.get("description"):
                    result["description"] = str(data["description"])[:2000]
                if data.get("image"):
                    imgs = data["image"] if isinstance(data["image"], list) else [data["image"]]
                    for img_url in imgs:
                        if isinstance(img_url, str) and img_url not in seen:
                            seen.add(img_url)
                            result["images"].append(img_url)
                seller = data.get("offeredBy") or data.get("seller") or {}
                if isinstance(seller, dict):
                    if not result["agent_name"] and seller.get("name"):
                        result["agent_name"] = seller["name"]
        except Exception:
            continue

    cache_set(ck, result)
    return result


async def fetch_phone_number(listing_url):
    """Fetch phone number from an individual Zameen.com listing page (uses detail cache)."""
    detail = await fetch_listing_detail(listing_url)
    return detail.get("phone") if detail else None


async def search_zameen(area=None, property_type=None, bedrooms=None, price_min=None, price_max=None, furnished=None, page=1, sort=None, city="karachi"):
    ck = cache_key(city=city, area=area, property_type=property_type, bedrooms=bedrooms, price_min=price_min, price_max=price_max, furnished=furnished, page=page, sort=sort)
    cached = cache_get(ck)
    if cached: return cached
    url = build_url(area, property_type, bedrooms, price_min, price_max, furnished, page, sort, city=city)
    logger.info(f"Fetching: {url}")
    async with httpx.AsyncClient() as client:
        html = await fetch_page(url, client)
    if not html: raise HTTPException(status_code=502, detail="Could not fetch results from Zameen.com. Try again shortly.")
    listings = parse_listings(html)
    if property_type and property_type.lower() in PROPERTY_TYPES:
        label = PROPERTY_TYPES[property_type.lower()]["label"]
        for listing in listings:
            listing["property_type"] = label
    total = len(listings)
    soup = BeautifulSoup(html, "html.parser")
    count_el = soup.select_one('h1, [class*="count"], [class*="total"]')
    if count_el:
        m = re.search(r'(\d[\d,]*)\s+(?:Flats?|Homes?|Houses?|Properties|Rooms?|Portions?|Penthouses?)', count_el.get_text())
        if m: total = int(m.group(1).replace(",",""))
    result = {"total": total, "page": page, "url": url, "results": listings}
    cache_set(ck, result)
    return result
