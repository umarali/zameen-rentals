"""Core crawl logic: card scraping, detail scraping, DB upserts."""
import asyncio, json, logging, re
from datetime import datetime

import httpx
from bs4 import BeautifulSoup

from app.cache import RateLimiter
from app.data import USER_AGENTS, PROPERTY_TYPES, CITY_AREAS
from app.database import _get_conn
from app.db_listings import upsert_listing, get_listings_needing_detail
from app.scraper import (
    fetch_page, parse_listings, fetch_listing_detail,
    extract_zameen_id, _extract_images
)
from app.parsing import build_url

logger = logging.getLogger("zameenrentals")

# Crawler uses its own slower rate limiter (1 req/sec, no burst)
crawler_rate_limiter = RateLimiter(rate=1.0, burst=1)


async def _fetch_page_crawl(url, client):
    """fetch_page variant that uses the crawler's own rate limiter."""
    import random
    for attempt in range(3):
        try:
            await crawler_rate_limiter.acquire()
            headers = {
                "User-Agent": random.choice(USER_AGENTS),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
                "Connection": "keep-alive",
            }
            resp = await client.get(url, headers=headers, timeout=20, follow_redirects=True)
            if resp.status_code == 200:
                return resp.text
            elif resp.status_code == 429:
                wait = (2 ** attempt) + 2
                logger.warning("Rate limited (429) on %s, waiting %ds", url, wait)
                await asyncio.sleep(wait)
            else:
                logger.warning("HTTP %d for %s", resp.status_code, url)
                await asyncio.sleep(1)
        except Exception as e:
            logger.error("Crawl fetch error for %s: %s", url, e)
            await asyncio.sleep(2 ** attempt)
    return None


def _extract_total_count(soup):
    """Extract total listing count from search results page."""
    count_el = soup.select_one('h1, [class*="count"], [class*="total"]')
    if count_el:
        m = re.search(
            r'(\d[\d,]*)\s+(?:Flats?|Homes?|Houses?|Properties|Rooms?|Portions?|Penthouses?)',
            count_el.get_text()
        )
        if m:
            return int(m.group(1).replace(",", ""))
    return None


async def crawl_area_cards(city, area_name, area_slug, area_id, lat, lng, client):
    """Crawl all search result pages for one area. Returns (new, updated, unchanged, pages)."""
    new_count, updated_count, unchanged_count, pages_fetched = 0, 0, 0, 0
    max_pages = 40  # Cap at 1000 listings per area

    for page_num in range(1, max_pages + 1):
        url = f"https://www.zameen.com/Rentals/{area_slug}-{area_id}-{page_num}.html"
        html = await _fetch_page_crawl(url, client)
        if not html:
            break

        pages_fetched += 1
        listings = parse_listings(html)
        if not listings:
            break

        # On first page, check total to estimate pages needed
        if page_num == 1:
            soup = BeautifulSoup(html, "html.parser")
            total = _extract_total_count(soup)
            if total:
                needed_pages = min((total + 24) // 25, max_pages)
            else:
                needed_pages = 1 if len(listings) < 25 else max_pages
        else:
            needed_pages = max_pages

        for listing in listings:
            listing_url = listing.get("url", "")
            zid = extract_zameen_id(listing_url)
            if not zid:
                continue

            result = upsert_listing(
                zameen_id=zid, url=listing_url, city=city,
                area_name=area_name, area_slug=area_slug,
                lat=lat, lng=lng, card_data=listing
            )
            if result == "inserted":
                new_count += 1
            elif result == "updated":
                updated_count += 1
            else:
                unchanged_count += 1

        # Stop if we've seen all pages
        if len(listings) < 25 or page_num >= needed_pages:
            break

    return new_count, updated_count, unchanged_count, pages_fetched


async def crawl_detail_batch(limit=10, client=None):
    """Scrape detail pages for listings that need it. Returns count of updated listings."""
    listings = get_listings_needing_detail(limit)
    if not listings:
        return 0

    own_client = client is None
    if own_client:
        client = httpx.AsyncClient()

    updated = 0
    try:
        for listing in listings:
            url = listing["url"]
            zid = listing["zameen_id"]

            await crawler_rate_limiter.acquire()
            html = await _fetch_page_crawl(url, client)
            if not html:
                continue

            # Parse detail page using the existing logic but without caching
            soup = BeautifulSoup(html, "html.parser")
            detail = _parse_detail_html(soup)

            result = upsert_listing(
                zameen_id=zid, url=url, city="",  # city not needed for detail update
                detail_data=detail
            )
            if result == "updated":
                updated += 1
    finally:
        if own_client:
            await client.aclose()

    return updated


def _parse_detail_html(soup):
    """Parse detail page HTML into a dict. Mirrors fetch_listing_detail logic."""
    import re
    from app.scraper import _is_property_photo_url

    result = {"phone": None, "description": None, "features": [], "amenities": [],
              "agent_name": None, "agent_agency": None, "images": [], "details": {}}

    # Phone
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
                    if t:
                        phone = str(t).strip()
                        break
                    for key in ("seller", "agent", "broker", "offeredBy"):
                        nested = item.get(key, {})
                        if isinstance(nested, dict):
                            t = nested.get("telephone") or nested.get("phone")
                            if t:
                                phone = str(t).strip()
                                break
                    if phone:
                        break
            except Exception:
                continue
    if not phone:
        for el in soup.select('[aria-label*="phone" i], [aria-label*="call" i], [class*="phone"], [class*="contact-number"]'):
            text = el.get_text(strip=True)
            m = re.search(r'(\+?92[\d\s-]{9,13}|0\d{2,3}[\s-]?\d{7,8})', text)
            if m:
                phone = m.group(1).strip()
                break
    if phone:
        phone = re.sub(r'[\s-]', '', phone)
    result["phone"] = phone

    # Description
    desc_el = soup.select_one('[aria-label="Description"] div, [class*="description"] p, [class*="body"] p')
    if not desc_el:
        for sel in ['div[class*="Description"] span', 'div[class*="description"]', 'section p']:
            desc_el = soup.select_one(sel)
            if desc_el and len(desc_el.get_text(strip=True)) > 30:
                break
    if desc_el:
        result["description"] = desc_el.get_text("\n", strip=True)[:2000]

    # Images
    images, seen = [], set()
    for img in soup.select('img[src*="/property/"], img[src*="zameen-media"], img[aria-label="Listing photo"]'):
        src = img.get("src") or img.get("data-src") or ""
        if not src or not _is_property_photo_url(src):
            continue
        src = re.sub(r'/\d+x\d+/', '/800x600/', src)
        if src not in seen:
            seen.add(src)
            images.append(src)
    for source in soup.select('picture source[srcset*="zameen-media"], picture source[srcset*="/property/"]'):
        srcset = source.get("srcset", "")
        for part in srcset.split(","):
            url = part.strip().split(" ")[0]
            if url and _is_property_photo_url(url):
                url = re.sub(r'/\d+x\d+/', '/800x600/', url)
                if url not in seen:
                    seen.add(url)
                    images.append(url)
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
                        if isinstance(img_url, str) and img_url not in seen:
                            seen.add(img_url)
                            result["images"].append(img_url)
                seller = data.get("offeredBy") or data.get("seller") or {}
                if isinstance(seller, dict) and not result["agent_name"] and seller.get("name"):
                    result["agent_name"] = seller["name"]
        except Exception:
            continue

    return result
