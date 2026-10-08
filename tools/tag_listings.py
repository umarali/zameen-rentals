"""
Tag crawled listings with Jev (who may rent, backup power, separate entrance,
new build). Safe to run on a timer next to the crawler: it only scores listings
that are new or changed since their last tag, and writes its own table.

Usage:
  python tools/tag_listings.py --dry-run             # what would run, and its cost
  python tools/tag_listings.py --limit 2000
  python tools/tag_listings.py --city lahore --include-title-only

Needs TYPESAFE_API_KEY. ZAMEENRENTALS_DB_DIR picks the database, as for the app.
"""
import argparse
import asyncio
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from app.database import close_db  # noqa: E402
from app.decisions import JEV_MODEL, JEV_USD_PER_MILLION_INPUT, jev_from_env  # noqa: E402
from app.listing_tags import (  # noqa: E402
    QUESTIONS, init_listing_tags_schema, listing_state, listings_needing_tags, tag_listings,
)


def _approx_tokens(text):
    return len(text) // 4 + 1


def _cost(tokens):
    return tokens / 1_000_000 * JEV_USD_PER_MILLION_INPUT


def dry_run(args):
    rows = listings_needing_tags(limit=args.limit, city=args.city,
                                 include_title_only=args.include_title_only)
    question_tokens = _approx_tokens(str(QUESTIONS))
    tokens = sum(_approx_tokens(listing_state(r)) + question_tokens for r in rows)
    print(f"{len(rows)} listings need tags (limit {args.limit}); "
          f"~{tokens:,} input tokens, ~${_cost(tokens):.4f} on {JEV_MODEL}")
    if rows:
        print("\nExample state:\n" + listing_state(rows[0]))


async def run(args):
    provider = jev_from_env()
    if provider is None:
        sys.exit("TYPESAFE_API_KEY is not set")
    try:
        stats = await tag_listings(provider, limit=args.limit, concurrency=args.concurrency,
                                   city=args.city, include_title_only=args.include_title_only)
    finally:
        await provider.aclose()
    lat = sorted(stats["latencies_ms"])
    p50 = statistics.median(lat) if lat else 0
    p95 = lat[int(len(lat) * 0.95) - 1] if len(lat) >= 20 else (lat[-1] if lat else 0)
    print(f"tagged {stats['tagged']}/{stats['candidates']}, failed {stats['failed']}; "
          f"{stats['input_tokens']:,} input tokens, ${_cost(stats['input_tokens']):.4f}; "
          f"latency p50 {p50:.0f}ms p95 {p95:.0f}ms")
    if stats["aborted"]:
        sys.exit(f"stopped early: {stats['aborted']}")


def main():
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--city", choices=["karachi", "lahore", "islamabad"])
    parser.add_argument("--include-title-only", action="store_true",
                        help="also tag listings without a description (weaker tags)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    init_listing_tags_schema()
    try:
        if args.dry_run:
            dry_run(args)
        else:
            asyncio.run(run(args))
    finally:
        close_db()


if __name__ == "__main__":
    main()
