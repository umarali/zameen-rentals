"""
Crawler entry point — scheduled crawl cycles with rest periods.

Architecture:
- Cycle-based: full card crawl → detail backfill → phone refresh → rest
- robots.txt compliant
- Adaptive rate limiting (backs off on 429s, recovers when clear)
- Session rotation (new browser profile each cycle)
- Smart area prioritization (popular areas first, failing areas deprioritized)
- Graceful shutdown on SIGTERM/SIGINT

Run: python -m app.crawler
"""
import asyncio, logging, random, signal, sys, time
from datetime import datetime

import httpx

from app.database import _get_conn, init_db
from app.data import CITIES, CITY_AREAS
from app.db_listings import mark_stale_listings, get_crawl_stats
from app.crawler_worker import (
    crawl_area_cards, crawl_detail_batch, refresh_phones_batch,
    _build_browser_profile, crawler_rate_limiter,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("zameenrentals.crawler")

_shutdown = False

# ── Crawl schedule configuration ──
CARD_CYCLE_INTERVAL_HOURS = 4    # Full card re-crawl every 4 hours
DETAIL_BATCH_SIZE = 15           # Detail pages per iteration
PHONE_BATCH_SIZE = 25            # Phone API calls per iteration
INTER_AREA_DELAY = (1.0, 3.0)   # Random delay between areas (seconds)
CYCLE_REST_MINUTES = 15          # Rest between full cycles
MAX_CONSECUTIVE_ERRORS = 5       # Pause crawling after this many errors in a row


def _handle_signal(sig, frame):
    global _shutdown
    logger.info("Shutdown signal received, finishing current task...")
    _shutdown = True


signal.signal(signal.SIGINT, _handle_signal)
signal.signal(signal.SIGTERM, _handle_signal)


# ── robots.txt compliance ──

_robots_cache = {}

async def check_robots_txt(client, ua):
    """Fetch and cache robots.txt, check if we're allowed to crawl."""
    if "zameen.com" in _robots_cache:
        return _robots_cache["zameen.com"]

    try:
        resp = await client.get(
            "https://www.zameen.com/robots.txt",
            headers={"User-Agent": ua},
            timeout=10,
        )
        if resp.status_code == 200:
            text = resp.text
            _robots_cache["zameen.com"] = text

            # Parse only the User-agent: * section
            in_all_agents = False
            disallowed = []
            crawl_delay = None
            for line in text.split("\n"):
                line = line.strip()
                if line.lower().startswith("user-agent: *"):
                    in_all_agents = True
                elif line.lower().startswith("user-agent:"):
                    in_all_agents = False
                elif in_all_agents:
                    if line.lower().startswith("crawl-delay:"):
                        try:
                            crawl_delay = float(line.split(":", 1)[1].strip())
                        except ValueError:
                            pass
                    elif line.lower().startswith("disallow:"):
                        path = line.split(":", 1)[1].strip()
                        if path:
                            disallowed.append(path)

            # Respect crawl-delay but cap at a reasonable maximum
            if crawl_delay and crawl_delay > 0:
                effective_delay = min(crawl_delay, 5.0)  # Cap at 5 seconds max
                crawler_rate_limiter.rate = 1.0 / effective_delay
                logger.info("robots.txt Crawl-delay: %.0fs (using %.1fs, rate: %.2f/sec)",
                            crawl_delay, effective_delay, crawler_rate_limiter.rate)

            for path in disallowed:
                if path in ("/Rentals/", "/Property/", "/"):
                    logger.warning("robots.txt disallows %s — respecting directive", path)
                    return None
            logger.info("robots.txt allows crawling /Rentals/ and /Property/")
            return text
    except Exception as e:
        logger.warning("Could not fetch robots.txt: %s", e)
    return "allow"


# ── Crawl state management ──

def init_crawl_state():
    """Populate crawl_state table from area JSON files (idempotent)."""
    conn = _get_conn()
    for city_key, city_info in CITIES.items():
        areas = CITY_AREAS.get(city_key, {})
        city_name = city_info["name"]
        for area_name, (slug, area_id, lat, lng) in areas.items():
            if area_name == city_name:
                continue
            conn.execute("""
                INSERT OR IGNORE INTO crawl_state (city, area_name, area_slug, area_id, priority)
                VALUES (?, ?, ?, ?, ?)
            """, (city_key, area_name, slug, area_id, 50))
    conn.commit()
    total = conn.execute("SELECT COUNT(*) FROM crawl_state").fetchone()[0]
    logger.info("Crawl state initialized: %d areas across %d cities", total, len(CITIES))


def update_area_priorities():
    """Recalculate crawl priorities based on search history + error rate."""
    conn = _get_conn()
    conn.execute("UPDATE crawl_state SET priority = 50")
    # Boost frequently searched areas
    conn.execute("""
        UPDATE crawl_state SET priority = 10
        WHERE area_name IN (
            SELECT area FROM search_history
            WHERE searched_at > datetime('now', '-7 days') AND area IS NOT NULL
            GROUP BY area HAVING COUNT(*) >= 5
        )
    """)
    conn.execute("""
        UPDATE crawl_state SET priority = 30
        WHERE priority = 50 AND area_name IN (
            SELECT area FROM search_history
            WHERE searched_at > datetime('now', '-7 days') AND area IS NOT NULL
            GROUP BY area HAVING COUNT(*) >= 1
        )
    """)
    # Deprioritize areas that keep erroring
    conn.execute("""
        UPDATE crawl_state SET priority = 90
        WHERE crawl_status = 'error' AND error_message IS NOT NULL
    """)
    conn.commit()
    logger.info("Area priorities updated")


def pick_next_area():
    """Pick the next area to crawl: never-crawled first, then by priority + staleness."""
    conn = _get_conn()
    row = conn.execute("""
        SELECT * FROM crawl_state
        WHERE crawl_status != 'in_progress'
        ORDER BY
            CASE WHEN last_crawl_at IS NULL THEN 0 ELSE 1 END,
            priority ASC,
            last_crawl_at ASC
        LIMIT 1
    """).fetchone()
    return dict(row) if row else None


def all_areas_crawled_recently(hours=4):
    """Check if all areas have been crawled within the given window."""
    conn = _get_conn()
    stale = conn.execute(
        "SELECT COUNT(*) FROM crawl_state WHERE last_crawl_at IS NULL OR last_crawl_at < datetime('now', ?)",
        (f'-{hours} hours',)
    ).fetchone()[0]
    return stale == 0


# ── Main crawl loop ──

async def run_crawler():
    """Main crawler loop with scheduled cycles and rest periods."""
    init_db()
    init_crawl_state()

    cycle_count = 0
    total_new, total_updated = 0, 0
    consecutive_errors = 0

    logger.info("=== Crawler v2 starting ===")
    stats = get_crawl_stats()
    logger.info("DB: %d listings, %d/%d areas crawled, %.1f%% with detail",
                stats["total_listings"], stats["areas_crawled"],
                stats["areas_total"], stats["detail_coverage"])

    while not _shutdown:
        cycle_count += 1
        cycle_start = time.monotonic()

        # New browser profile for each cycle (rotate identity)
        session_ua, session_headers = _build_browser_profile()
        logger.info("=== Cycle %d | UA: %s... ===", cycle_count, session_ua[:60])

        # Check robots.txt at start of each cycle
        async with httpx.AsyncClient() as client:
            robots = await check_robots_txt(client, session_ua)
            if robots is None:
                logger.error("Crawling disallowed by robots.txt — sleeping 1 hour")
                await asyncio.sleep(3600)
                continue

        # Reset rate limiter to base speed at cycle start (recover from previous 429 slowdowns)
        # robots.txt check above may have set a lower rate — that's preserved via the check
        crawler_rate_limiter.rate = min(1.0, max(crawler_rate_limiter.rate, 0.2))

        # Update priorities at cycle start
        update_area_priorities()

        iteration = 0

        async with httpx.AsyncClient() as client:
            # ── Phase A: Card crawl (all stale areas) ──
            logger.info("[Phase A] Card crawling...")
            phase_a_new, phase_a_updated = 0, 0

            while not _shutdown:
                area = pick_next_area()
                if not area:
                    break

                # Check if this area was already crawled recently
                if area.get("last_crawl_at"):
                    from datetime import datetime as dt
                    try:
                        last = dt.fromisoformat(area["last_crawl_at"])
                        age_hours = (dt.utcnow() - last).total_seconds() / 3600
                        if age_hours < CARD_CYCLE_INTERVAL_HOURS:
                            break  # All remaining areas are fresh enough
                    except (ValueError, TypeError):
                        pass

                conn = _get_conn()
                conn.execute("UPDATE crawl_state SET crawl_status = 'in_progress' WHERE id = ?", (area["id"],))
                conn.commit()

                city = area["city"]
                area_name = area["area_name"]
                iteration += 1

                try:
                    area_info = CITY_AREAS.get(city, {}).get(area_name)
                    lat = area_info[2] if area_info else None
                    lng = area_info[3] if area_info else None

                    new, updated, unchanged, pages = await crawl_area_cards(
                        city, area_name, area["area_slug"], area["area_id"],
                        lat, lng, client, session_headers
                    )

                    phase_a_new += new
                    phase_a_updated += updated
                    consecutive_errors = 0

                    conn.execute("""
                        UPDATE crawl_state SET
                            crawl_status = 'completed', last_crawl_at = datetime('now'),
                            pages_crawled = ?, listings_found = ?,
                            new_listings = ?, updated_listings = ?, error_message = NULL
                        WHERE id = ?
                    """, (pages, new + updated + unchanged, new, updated, area["id"]))
                    conn.commit()

                    if iteration % 25 == 0:
                        logger.info("  [%d areas] %d new, %d updated so far", iteration, phase_a_new, phase_a_updated)

                except Exception as e:
                    consecutive_errors += 1
                    logger.exception("Error crawling %s/%s", city, area_name)
                    conn.execute(
                        "UPDATE crawl_state SET crawl_status = 'error', error_message = ? WHERE id = ?",
                        (str(e)[:500], area["id"])
                    )
                    conn.commit()

                    if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                        logger.error("Too many consecutive errors (%d) — pausing 5 minutes", consecutive_errors)
                        await asyncio.sleep(300)
                        consecutive_errors = 0

                if _shutdown:
                    break

                # Human-like delay between areas
                await asyncio.sleep(random.uniform(*INTER_AREA_DELAY))

            total_new += phase_a_new
            total_updated += phase_a_updated
            logger.info("[Phase A complete] %d areas, %d new, %d updated", iteration, phase_a_new, phase_a_updated)

            if _shutdown:
                break

            # ── Phase B: Detail backfill ──
            logger.info("[Phase B] Detail backfill...")
            detail_total = 0
            for _ in range(20):  # Up to 20 batches per cycle
                if _shutdown:
                    break
                count = await crawl_detail_batch(
                    limit=DETAIL_BATCH_SIZE, client=client, session_ua=session_ua
                )
                if count == 0:
                    break
                detail_total += count
                await asyncio.sleep(random.uniform(1, 3))

            logger.info("[Phase B complete] %d listings enriched with details", detail_total)

            if _shutdown:
                break

            # ── Phase C: Phone refresh via API ──
            logger.info("[Phase C] Phone number refresh...")
            phone_total = 0
            for _ in range(10):  # Up to 10 batches per cycle
                if _shutdown:
                    break
                count = await refresh_phones_batch(
                    limit=PHONE_BATCH_SIZE, client=client, session_ua=session_ua
                )
                if count == 0:
                    break
                phone_total += count
                await asyncio.sleep(random.uniform(2, 5))

            logger.info("[Phase C complete] %d phone numbers refreshed", phone_total)

            if _shutdown:
                break

            # ── Phase D: Staleness cleanup ──
            mark_stale_listings(days=7)

        # ── Cycle summary ──
        cycle_duration = (time.monotonic() - cycle_start) / 60
        stats = get_crawl_stats()
        logger.info(
            "=== Cycle %d complete (%.0f min) | DB: %d listings, %.1f%% with detail, rate: %.2f/sec ===",
            cycle_count, cycle_duration,
            stats["total_listings"], stats["detail_coverage"],
            crawler_rate_limiter.rate
        )

        if _shutdown:
            break

        # ── Rest between cycles ──
        if all_areas_crawled_recently(CARD_CYCLE_INTERVAL_HOURS):
            rest_seconds = CYCLE_REST_MINUTES * 60 + random.uniform(0, 300)
            logger.info("All areas fresh — resting %.0f minutes until next cycle", rest_seconds / 60)
            # Sleep in small increments so we can respond to shutdown
            for _ in range(int(rest_seconds / 5)):
                if _shutdown:
                    break
                await asyncio.sleep(5)
        else:
            # Some areas still need crawling, short rest
            await asyncio.sleep(30)

    logger.info("=== Crawler stopped. Session total: %d new, %d updated ===",
                total_new, total_updated)


def main():
    asyncio.run(run_crawler())


if __name__ == "__main__":
    main()
