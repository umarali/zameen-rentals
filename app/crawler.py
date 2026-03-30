"""
Crawler entry point — continuous loop that scrapes all areas across all cities.

Run: python -m app.crawler
"""
import asyncio, logging, signal, sys
from datetime import datetime

import httpx

from app.database import _get_conn, init_db
from app.data import CITIES, CITY_AREAS
from app.db_listings import mark_stale_listings, get_crawl_stats
from app.crawler_worker import crawl_area_cards, crawl_detail_batch

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("zameenrentals.crawler")

_shutdown = False


def _handle_signal(sig, frame):
    global _shutdown
    logger.info("Shutdown signal received, finishing current task...")
    _shutdown = True


signal.signal(signal.SIGINT, _handle_signal)
signal.signal(signal.SIGTERM, _handle_signal)


def init_crawl_state():
    """Populate crawl_state table from area JSON files (idempotent)."""
    conn = _get_conn()
    for city_key, city_info in CITIES.items():
        areas = CITY_AREAS.get(city_key, {})
        city_name = city_info["name"]
        for area_name, (slug, area_id, lat, lng) in areas.items():
            if area_name == city_name:
                continue  # Skip the city-level entry
            conn.execute("""
                INSERT OR IGNORE INTO crawl_state (city, area_name, area_slug, area_id, priority)
                VALUES (?, ?, ?, ?, ?)
            """, (city_key, area_name, slug, area_id, 50))
    conn.commit()
    total = conn.execute("SELECT COUNT(*) FROM crawl_state").fetchone()[0]
    logger.info("Crawl state initialized: %d areas across %d cities", total, len(CITIES))


def update_area_priorities():
    """Recalculate crawl priorities based on search history popularity."""
    conn = _get_conn()
    # Reset all to default
    conn.execute("UPDATE crawl_state SET priority = 50")
    # Boost areas searched in the last 7 days
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
    conn.commit()
    logger.info("Area priorities updated from search history")


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


def start_crawl_log(crawl_type):
    """Create a new crawl_log entry and return its ID."""
    conn = _get_conn()
    cursor = conn.execute(
        "INSERT INTO crawl_log (crawl_type) VALUES (?)", (crawl_type,)
    )
    conn.commit()
    return cursor.lastrowid


def finish_crawl_log(log_id, **kwargs):
    """Update a crawl_log entry with results."""
    conn = _get_conn()
    sets = ", ".join(f"{k} = ?" for k in kwargs)
    conn.execute(
        f"UPDATE crawl_log SET finished_at = datetime('now'), {sets} WHERE id = ?",
        list(kwargs.values()) + [log_id]
    )
    conn.commit()


async def run_crawler():
    """Main crawler loop — runs continuously until shutdown signal."""
    init_db()
    init_crawl_state()

    iteration = 0
    total_new, total_updated = 0, 0

    logger.info("=== Crawler starting ===")
    stats = get_crawl_stats()
    logger.info("Current DB: %d listings, %d/%d areas crawled",
                stats["total_listings"], stats["areas_crawled"], stats["areas_total"])

    async with httpx.AsyncClient() as client:
        while not _shutdown:
            iteration += 1

            # Recalculate priorities every 50 iterations
            if iteration % 50 == 1:
                update_area_priorities()

            # ── Phase A: Crawl card pages for one area ──
            area = pick_next_area()
            if area:
                conn = _get_conn()
                conn.execute(
                    "UPDATE crawl_state SET crawl_status = 'in_progress' WHERE id = ?",
                    (area["id"],)
                )
                conn.commit()

                city = area["city"]
                area_name = area["area_name"]
                logger.info("[%d] Crawling cards: %s / %s", iteration, city, area_name)

                try:
                    # Get lat/lng from CITY_AREAS
                    area_info = CITY_AREAS.get(city, {}).get(area_name)
                    lat = area_info[2] if area_info else None
                    lng = area_info[3] if area_info else None

                    new, updated, unchanged, pages = await crawl_area_cards(
                        city, area_name, area["area_slug"], area["area_id"],
                        lat, lng, client
                    )

                    total_new += new
                    total_updated += updated

                    conn.execute("""
                        UPDATE crawl_state SET
                            crawl_status = 'completed', last_crawl_at = datetime('now'),
                            pages_crawled = ?, listings_found = ?,
                            new_listings = ?, updated_listings = ?, error_message = NULL
                        WHERE id = ?
                    """, (pages, new + updated + unchanged, new, updated, area["id"]))
                    conn.commit()

                    logger.info("  -> %d new, %d updated, %d unchanged (%d pages)",
                                new, updated, unchanged, pages)

                except Exception as e:
                    logger.exception("Error crawling %s/%s", city, area_name)
                    conn.execute(
                        "UPDATE crawl_state SET crawl_status = 'error', error_message = ? WHERE id = ?",
                        (str(e)[:500], area["id"])
                    )
                    conn.commit()

            if _shutdown:
                break

            # ── Phase B: Detail backfill (10 listings per iteration) ──
            try:
                detail_count = await crawl_detail_batch(limit=10, client=client)
                if detail_count:
                    logger.info("  Detail backfill: %d listings enriched", detail_count)
            except Exception:
                logger.exception("Error in detail backfill")

            if _shutdown:
                break

            # ── Phase C: Staleness cleanup (every 100 iterations) ──
            if iteration % 100 == 0:
                mark_stale_listings(days=7)
                stats = get_crawl_stats()
                logger.info("=== Stats: %d listings, %d/%d areas, %.1f%% with detail ===",
                            stats["total_listings"], stats["areas_crawled"],
                            stats["areas_total"], stats["detail_coverage"])

            # Brief pause between iterations
            await asyncio.sleep(1)

    logger.info("=== Crawler stopped. Total this session: %d new, %d updated ===",
                total_new, total_updated)


def main():
    asyncio.run(run_crawler())


if __name__ == "__main__":
    main()
