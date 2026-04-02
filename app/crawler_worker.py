"""Core crawl logic: card scraping, detail scraping, phone API, browser simulation."""
import asyncio, hashlib, json, logging, random, re, uuid
from datetime import datetime

import httpx
from bs4 import BeautifulSoup

from app.cache import RateLimiter
from app.data import USER_AGENTS, PROPERTY_TYPES, CITY_AREAS, CRAWL_PROPERTY_TYPES
from app.database import _get_conn
from app.db_listings import upsert_listing, get_listings_needing_detail
from app.scraper import (
    parse_listings, extract_zameen_id, _is_property_photo_url, fetch_listing_contact,
    _extract_listing_geography,
)

logger = logging.getLogger("zameenrentals")

# Crawler rate limiter: adaptive, starts conservative
crawler_rate_limiter = RateLimiter(rate=1.0, burst=2)

# ── Browser profile simulation ──

def _build_browser_profile():
    """Generate a realistic browser identity for a crawl session.
    Returns (user_agent, headers_dict) that stay consistent within a session."""
    ua = random.choice(USER_AGENTS)
    is_chrome = "Chrome/" in ua and "Edg/" not in ua
    is_firefox = "Firefox/" in ua
    is_safari = "Safari/" in ua and "Chrome/" not in ua
    is_edge = "Edg/" in ua

    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": random.choice([
            "en-US,en;q=0.9",
            "en-GB,en;q=0.9,en-US;q=0.8",
            "en-US,en;q=0.9,ur;q=0.8",
        ]),
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "User-Agent": ua,
        "DNT": "1",
        "Upgrade-Insecure-Requests": "1",
    }

    if is_chrome or is_edge:
        # Extract Chrome version for sec-ch-ua
        m = re.search(r"Chrome/(\d+)", ua)
        cv = m.group(1) if m else "145"
        brand = "Google Chrome" if is_chrome else "Microsoft Edge"
        headers["sec-ch-ua"] = f'"Not:A-Brand";v="99", "{brand}";v="{cv}", "Chromium";v="{cv}"'
        headers["sec-ch-ua-mobile"] = "?1" if "Mobile" in ua else "?0"
        headers["sec-ch-ua-platform"] = (
            '"Android"' if "Android" in ua else
            '"macOS"' if "Mac" in ua else
            '"Windows"' if "Windows" in ua else
            '"Linux"'
        )
        headers["sec-fetch-dest"] = "document"
        headers["sec-fetch-mode"] = "navigate"
        headers["sec-fetch-site"] = "none"
        headers["sec-fetch-user"] = "?1"

    return ua, headers


def _api_headers(ua, referer_url):
    """Headers for Zameen.com internal API calls (showNumbers, etc.)."""
    headers = {
        "User-Agent": ua,
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Accept-Language": "en",
        "DNT": "1",
        "Referer": referer_url,
        "X-Requested-With": "XMLHttpRequest",
    }
    if "Chrome/" in ua:
        m = re.search(r"Chrome/(\d+)", ua)
        cv = m.group(1) if m else "145"
        headers["sec-ch-ua"] = f'"Not:A-Brand";v="99", "Google Chrome";v="{cv}", "Chromium";v="{cv}"'
        headers["sec-ch-ua-mobile"] = "?0"
        headers["sec-ch-ua-platform"] = '"macOS"' if "Mac" in ua else '"Windows"'
        headers["sec-fetch-dest"] = "empty"
        headers["sec-fetch-mode"] = "cors"
        headers["sec-fetch-site"] = "same-origin"
    return headers


# ── Fetch with retry + adaptive backoff ──

_consecutive_429s = 0

async def _fetch(url, client, headers, timeout=20):
    """Fetch a URL with retry, adaptive rate limiting, and proper backoff."""
    global _consecutive_429s

    for attempt in range(3):
        try:
            await crawler_rate_limiter.acquire()
            resp = await client.get(url, headers=headers, timeout=timeout, follow_redirects=True)

            if resp.status_code == 200:
                _consecutive_429s = max(0, _consecutive_429s - 1)
                return resp.text
            elif resp.status_code == 429:
                _consecutive_429s += 1
                # Adaptive: slow down more as 429s accumulate
                wait = (2 ** attempt) + random.uniform(2, 5) + (_consecutive_429s * 2)
                logger.warning("429 on %s (consecutive: %d), waiting %.0fs", url, _consecutive_429s, wait)
                await asyncio.sleep(wait)
                # Slow down the rate limiter if we keep getting 429s
                if _consecutive_429s >= 3:
                    crawler_rate_limiter.rate = max(0.3, crawler_rate_limiter.rate * 0.7)
                    logger.warning("Rate limiter slowed to %.2f req/sec", crawler_rate_limiter.rate)
            elif resp.status_code == 404:
                return None  # Page doesn't exist — don't retry
            elif resp.status_code == 403:
                logger.error("403 Forbidden on %s — may be blocked", url)
                await asyncio.sleep(30 + random.uniform(0, 30))
                return None
            elif resp.status_code in (301, 302):
                return None  # Redirect means area/listing no longer exists
            else:
                logger.warning("HTTP %d for %s", resp.status_code, url)
                await asyncio.sleep(1 + random.uniform(0, 2))
        except httpx.TimeoutException:
            logger.warning("Timeout on %s (attempt %d)", url, attempt + 1)
            await asyncio.sleep(2 ** attempt)
        except Exception as e:
            logger.error("Fetch error for %s: %s", url, e)
            await asyncio.sleep(2 ** attempt)
    return None


# ── Total count extraction ──

def _extract_total_count(soup):
    count_el = soup.select_one('h1, [class*="count"], [class*="total"]')
    if count_el:
        m = re.search(
            r'(\d[\d,]*)\s+(?:Flats?|Homes?|Houses?|Properties|Rooms?|Portions?|Penthouses?)',
            count_el.get_text()
        )
        if m:
            return int(m.group(1).replace(",", ""))
    return None


# ── Card crawling ──

async def _crawl_single_type(city, area_name, area_slug, area_id, lat, lng,
                             client, session_headers, type_slug=None, type_label=None):
    """Crawl pages for one area under one URL pattern. Returns (new, updated, unchanged, pages)."""
    new_count, updated_count, unchanged_count, pages_fetched = 0, 0, 0, 0
    base_slug = type_slug or "Rentals"
    default_cap = 40
    max_pages = default_cap

    for page_num in range(1, max_pages + 1):
        url = f"https://www.zameen.com/{base_slug}/{area_slug}-{area_id}-{page_num}.html"

        headers = {**session_headers}
        if page_num == 1:
            headers["Referer"] = f"https://www.zameen.com/{base_slug}/{city.capitalize()}-{CITY_AREAS.get(city, {}).get(city.capitalize(), ('', 0))[1] or 2}-1.html"
        else:
            headers["Referer"] = f"https://www.zameen.com/{base_slug}/{area_slug}-{area_id}-{page_num - 1}.html"

        html = await _fetch(url, client, headers)
        if not html:
            break

        pages_fetched += 1
        listings = parse_listings(html)
        if not listings:
            break

        if page_num == 1:
            soup = BeautifulSoup(html, "html.parser")
            total = _extract_total_count(soup)
            if total:
                needed = (total + 24) // 25
                # Dynamic cap: raise for high-density areas
                if total > 900:
                    max_pages = min(needed, 80)
                    logger.info("  High-density: %d listings, raising cap to %d pages", total, max_pages)
                else:
                    max_pages = min(needed, default_cap)
            else:
                max_pages = 1 if len(listings) < 25 else default_cap

        for listing in listings:
            listing_url = listing.get("url", "")
            zid = extract_zameen_id(listing_url)
            if not zid:
                continue

            card_data = listing
            # Override property_type when crawling type-specific URLs
            if type_label:
                card_data["property_type"] = type_label

            result = upsert_listing(
                zameen_id=zid, url=listing_url, city=city,
                area_name=area_name, area_slug=area_slug,
                lat=lat, lng=lng, card_data=card_data
            )
            if result == "inserted":
                new_count += 1
            elif result == "updated":
                updated_count += 1
            else:
                unchanged_count += 1

        if len(listings) < 25 or page_num >= max_pages:
            break

        await asyncio.sleep(random.uniform(0.5, 1.5))

    return new_count, updated_count, unchanged_count, pages_fetched


def _get_empty_types(city, area_slug):
    """Get property types that previously returned 0 results for this area."""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT property_type FROM crawl_type_state WHERE city = ? AND area_slug = ? AND is_empty = 1",
        (city, area_slug)
    ).fetchall()
    return {r["property_type"] for r in rows}


def _update_type_state(city, area_slug, property_type, listings_found):
    """Track results per (area, property_type) combo."""
    conn = _get_conn()
    now = datetime.utcnow().isoformat()
    conn.execute("""
        INSERT INTO crawl_type_state (city, area_slug, property_type, last_crawl_at, listings_found, is_empty)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(city, area_slug, property_type) DO UPDATE SET
            last_crawl_at = ?, listings_found = ?, is_empty = ?
    """, (city, area_slug, property_type, now, listings_found, 1 if listings_found == 0 else 0,
          now, listings_found, 1 if listings_found == 0 else 0))
    conn.commit()


async def crawl_area_cards(city, area_name, area_slug, area_id, lat, lng, client, session_headers):
    """Crawl all search result pages for one area across all property types.
    Returns (new, updated, unchanged, pages)."""
    total_new, total_updated, total_unchanged, total_pages = 0, 0, 0, 0

    # 1. Crawl generic /Rentals/ first (catches everything, sets baseline)
    new, updated, unchanged, pages = await _crawl_single_type(
        city, area_name, area_slug, area_id, lat, lng,
        client, session_headers
    )
    total_new += new
    total_updated += updated
    total_unchanged += unchanged
    total_pages += pages

    # 2. Crawl each property-type-specific URL
    empty_types = _get_empty_types(city, area_slug)

    for type_slug, type_label in CRAWL_PROPERTY_TYPES:
        if type_slug in empty_types:
            continue  # Skip types that previously returned 0 for this area

        # Small delay between type crawls
        await asyncio.sleep(random.uniform(0.5, 2.0))

        new, updated, unchanged, pages = await _crawl_single_type(
            city, area_name, area_slug, area_id, lat, lng,
            client, session_headers,
            type_slug=type_slug, type_label=type_label
        )

        # Track results for smart skipping
        _update_type_state(city, area_slug, type_slug, new + updated + unchanged)

        total_new += new
        total_updated += updated
        total_unchanged += unchanged
        total_pages += pages

    return total_new, total_updated, total_unchanged, total_pages


# ── Phone extraction via showNumbers API ──

async def fetch_phone_via_api(zameen_id, listing_url, client, ua):
    """Fetch phone number using Zameen.com's internal showNumbers API.
    This is the same API the browser calls when you click 'Call'."""
    try:
        return await fetch_listing_contact(listing_url, client=client, user_agent=ua)
    except Exception as e:
        logger.error("showNumbers error for %s: %s", zameen_id, e)
        return None


# ── Detail page scraping (description, features, amenities — NOT phone) ──

def _parse_detail_html(soup, html=None, zameen_id=None):
    """Parse detail page HTML for everything EXCEPT phone (which comes from API)."""
    result = {"description": None, "features": [], "amenities": [],
              "agent_name": None, "agent_agency": None, "images": [], "details": {}}

    # Description
    desc_el = soup.select_one('[aria-label="Description"] div, [class*="description"] p, [class*="body"] p')
    if not desc_el:
        for sel in ['div[class*="Description"] span', 'div[class*="description"]', 'section p']:
            desc_el = soup.select_one(sel)
            if desc_el and len(desc_el.get_text(strip=True)) > 30:
                break
    if desc_el:
        result["description"] = desc_el.get_text("\n", strip=True)[:2000]

    # Images — extract ALL property photos from the gallery
    # Zameen.com uses media.zameen.com/thumbnails/{ID}-{WxH}.jpeg
    # Photos appear as img tags and picture/source elements
    images, seen_ids = [], set()

    def _add_image(url):
        """Normalize image URL to 800x600 and deduplicate by image ID."""
        if not url or "svg" in url:
            return
        if not _is_property_photo_url(url):
            return
        # Extract unique image ID (e.g., "295194207" from "295194207-800x600.jpeg")
        m = re.search(r'/(\d{6,12})-\d+x\d+\.', url)
        img_id = m.group(1) if m else url
        if img_id in seen_ids:
            return
        seen_ids.add(img_id)
        # Normalize to 800x600
        normalized = re.sub(r'-\d+x\d+\.', '-800x600.', url)
        # Prefer jpeg over webp for broader compat
        normalized = re.sub(r'\.webp$', '.jpeg', normalized)
        images.append(normalized)

    # 1. All img tags with media.zameen.com or zameen-media
    for img in soup.select('img[src*="media.zameen.com"], img[src*="zameen-media"], img[aria-label="Listing photo"], img[aria-label="Cover Photo"]'):
        _add_image(img.get("src") or img.get("data-src") or "")

    # 2. picture/source elements (often have webp versions)
    for source in soup.select('picture source[srcset*="media.zameen.com"], picture source[srcset*="zameen-media"]'):
        for part in source.get("srcset", "").split(","):
            _add_image(part.strip().split(" ")[0])

    # 3. Thumbnail strip images (120x90 thumbnails reveal photos not shown in main gallery)
    # But skip agent/agency logos
    for img in soup.select('img[src*="media.zameen.com"]'):
        aria = (img.get("aria-label") or "").lower()
        if "agency" in aria or "agent" in aria or "logo" in aria or "fallback" in aria:
            continue
        _add_image(img.get("src") or "")

    if images:
        result["images"] = images

    # Features
    for li in soup.select('ul[class*="feature"] li, ul[class*="detail"] li, [aria-label="Features"] li'):
        text = li.get_text(strip=True)
        if text and len(text) < 100:
            result["features"].append(text)

    # Amenities
    for el in soup.select('[class*="amenity"] span, [class*="amenity"] li, [aria-label="Amenities"] li, [aria-label="Amenities"] span'):
        text = el.get_text(strip=True)
        if text and len(text) < 60 and text not in result["amenities"]:
            result["amenities"].append(text)

    # Details key-value
    for row in soup.select('[class*="detail"] li, table tr, [aria-label*="detail"] div'):
        texts = [t.get_text(strip=True) for t in row.select("span, td, th, dt, dd") if t.get_text(strip=True)]
        if len(texts) == 2 and len(texts[0]) < 40 and len(texts[1]) < 80:
            result["details"][texts[0]] = texts[1]

    # Agent
    agent_el = soup.select_one('[class*="agent-name"], [class*="AgentName"], [aria-label*="agent"] [class*="name"]')
    if agent_el:
        result["agent_name"] = agent_el.get_text(strip=True)
    agency_el = soup.select_one('[class*="agency-name"], [class*="AgencyName"], [aria-label*="agency"]')
    if agency_el:
        result["agent_agency"] = agency_el.get_text(strip=True)

    # JSON-LD enrichment
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            data = json.loads(script.string or "")
            if isinstance(data, dict):
                if not result["description"] and data.get("description"):
                    result["description"] = str(data["description"])[:2000]
                if data.get("image"):
                    imgs = data["image"] if isinstance(data["image"], list) else [data["image"]]
                    for img_url in imgs:
                        if isinstance(img_url, str):
                            _add_image(img_url)
                seller = data.get("offeredBy") or data.get("seller") or {}
                if isinstance(seller, dict) and not result["agent_name"] and seller.get("name"):
                    result["agent_name"] = seller["name"]
        except Exception:
            continue

    geography = _extract_listing_geography(html or "", zameen_id)
    if geography:
        result.update(geography)

    return result


# ── Detail + phone batch processing ──

async def crawl_detail_batch(limit=10, client=None, session_ua=None):
    """Scrape detail pages and fetch phone numbers via API for listings that need enrichment."""
    listings = get_listings_needing_detail(limit)
    if not listings:
        return 0

    own_client = client is None
    if own_client:
        client = httpx.AsyncClient()

    ua = session_ua or random.choice(USER_AGENTS)
    updated = 0

    try:
        for listing in listings:
            url = listing["url"]
            zid = listing["zameen_id"]

            # 1. Fetch detail page HTML (for description, features, amenities, images)
            detail_headers = _api_headers(ua, "https://www.zameen.com/")
            detail_headers["Accept"] = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
            detail_headers["sec-fetch-dest"] = "document"
            detail_headers["sec-fetch-mode"] = "navigate"
            detail_headers.pop("X-Requested-With", None)
            detail_headers.pop("Content-Type", None)

            html = await _fetch(url, client, detail_headers)
            detail_data = {}
            if html:
                soup = BeautifulSoup(html, "html.parser")
                detail_data = _parse_detail_html(soup, html=html, zameen_id=zid)

            # 2. Fetch phone via showNumbers API (separate call, like a real browser click)
            await asyncio.sleep(random.uniform(0.3, 1.0))  # Simulate user reading page before clicking
            phone_data = await fetch_phone_via_api(zid, url, client, ua)
            if phone_data:
                detail_data["phone"] = phone_data.get("phone")
                detail_data["call_phone"] = phone_data.get("call_phone")
                detail_data["whatsapp_phone"] = phone_data.get("whatsapp_phone")
                detail_data["contact_payload"] = phone_data.get("contact_payload")
                detail_data["contact_source"] = phone_data.get("contact_source")
                if phone_data.get("agent_agency") and not detail_data.get("agent_agency"):
                    detail_data["agent_agency"] = phone_data["agent_agency"]

            # 3. Upsert detail data
            if detail_data:
                result = upsert_listing(
                    zameen_id=zid, url=url, city="",
                    detail_data=detail_data
                )
                if result == "updated":
                    updated += 1

            # Random delay between listings
            await asyncio.sleep(random.uniform(0.5, 2.0))

    finally:
        if own_client:
            await client.aclose()

    return updated


# ── Phone-only batch (for refreshing phones without re-scraping detail pages) ──

async def refresh_phones_batch(limit=20, client=None, session_ua=None):
    """Refresh phone numbers via API for listings with stale or missing phones."""
    conn = _get_conn()
    rows = conn.execute("""
        SELECT zameen_id, url, call_phone, whatsapp_phone FROM listings
        WHERE is_active = 1 AND (
            contact_fetched_at IS NULL
            OR contact_fetched_at < datetime('now', '-3 days')
        )
        ORDER BY contact_fetched_at ASC NULLS FIRST
        LIMIT ?
    """, (limit,)).fetchall()

    if not rows:
        return 0

    own_client = client is None
    if own_client:
        client = httpx.AsyncClient()

    ua = session_ua or random.choice(USER_AGENTS)
    updated = 0
    now = datetime.utcnow().isoformat()

    try:
        for row in rows:
            zid, url = row["zameen_id"], row["url"]
            phone_data = await fetch_phone_via_api(zid, url, client, ua)

            if phone_data:
                call_phone = phone_data.get("call_phone") or row["call_phone"]
                whatsapp_phone = (
                    phone_data.get("whatsapp_phone")
                    if "whatsapp_phone" in phone_data
                    else row["whatsapp_phone"]
                )
                conn.execute("""
                    UPDATE listings
                    SET phone = ?, call_phone = ?, whatsapp_phone = ?,
                        contact_payload_json = ?, contact_fetched_at = ?, contact_source = ?,
                        agent_agency = COALESCE(?, agent_agency)
                    WHERE zameen_id = ?
                """, (
                    call_phone, call_phone, whatsapp_phone,
                    json.dumps(phone_data.get("contact_payload")) if phone_data.get("contact_payload") else None,
                    now, phone_data.get("contact_source"), phone_data.get("agent_agency"), zid,
                ))
                conn.commit()
                updated += 1

            await asyncio.sleep(random.uniform(1.0, 3.0))  # Spread phone API calls
    finally:
        if own_client:
            await client.aclose()

    return updated
