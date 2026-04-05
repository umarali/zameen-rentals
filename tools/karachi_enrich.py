#!/usr/bin/env python3
"""One-shot script to enrich all Karachi listings (details + phones) ASAP.

Usage: python -m tools.karachi_enrich
"""
import asyncio
import sys
import os
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import init_db
from app.crawler_worker import crawl_detail_batch, refresh_phones_batch, _build_browser_profile
from app.db_listings import _get_conn

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("karachi_enrich")


async def main():
    init_db()
    conn = _get_conn()

    # Check what needs doing
    missing_detail = conn.execute(
        "SELECT COUNT(*) FROM listings WHERE city='karachi' AND is_active=1 AND detail_scraped_at IS NULL"
    ).fetchone()[0]
    missing_phone = conn.execute(
        "SELECT COUNT(*) FROM listings WHERE city='karachi' AND is_active=1 AND (call_phone IS NULL AND whatsapp_phone IS NULL)"
    ).fetchone()[0]

    logger.info("Karachi gaps: %d missing details, %d missing phones", missing_detail, missing_phone)

    import httpx
    ua, headers = _build_browser_profile()

    async with httpx.AsyncClient() as client:
        # Phase 1: Details — batch through all missing
        total_detail = 0
        while True:
            count = await crawl_detail_batch(limit=30, client=client, session_ua=ua)
            if count == 0:
                break
            total_detail += count
            logger.info("  Details enriched: %d (total: %d)", count, total_detail)
            await asyncio.sleep(0.5)

        # Phase 2: Phones — batch through all missing
        total_phone = 0
        while True:
            count = await refresh_phones_batch(limit=50, client=client, session_ua=ua)
            if count == 0:
                break
            total_phone += count
            logger.info("  Phones refreshed: %d (total: %d)", count, total_phone)
            await asyncio.sleep(0.5)

    # Final check
    still_no_detail = conn.execute(
        "SELECT COUNT(*) FROM listings WHERE city='karachi' AND is_active=1 AND detail_scraped_at IS NULL"
    ).fetchone()[0]
    still_no_phone = conn.execute(
        "SELECT COUNT(*) FROM listings WHERE city='karachi' AND is_active=1 AND (call_phone IS NULL AND whatsapp_phone IS NULL)"
    ).fetchone()[0]

    logger.info("=== Done. Enriched %d details, %d phones ===", total_detail, total_phone)
    logger.info("Remaining gaps: %d no detail, %d no phone", still_no_detail, still_no_phone)


if __name__ == "__main__":
    asyncio.run(main())
