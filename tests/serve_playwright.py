"""Run browser tests with disposable data and no upstream scraping."""
import os
from pathlib import Path
import signal
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    with tempfile.TemporaryDirectory(prefix="zameen-playwright-") as directory:
        os.environ["ZAMEENRENTALS_DB_DIR"] = directory
        os.environ["ZAMEENRENTALS_PLAYWRIGHT"] = "1"
        # Credits checkout runs against the local test provider (no real money).
        # It only starts when ZR_ENV names a non-production environment.
        os.environ.setdefault("ZR_ENV", "test")
        os.environ.setdefault("PAYMENTS_PROVIDER", "test")
        from app import app, credits
        # Hundreds of isolated browsers share localhost in this suite. The real
        # network grant limit is covered by the API/SQLite tests.
        credits.STARTER_WALLETS_PER_NETWORK_DAY = 10000
        import app.routes as routes

        # Nearby queries with fewer than one page of exact pins normally enrich
        # listings upstream. Fixture URLs are synthetic: exercise the real DB
        # query without sending those URLs to Zameen.com.
        async def no_nearby_enrichment(**kwargs):
            return False

        routes._maybe_enrich_nearby_exact_locations = no_nearby_enrichment
        from app.database import init_db, close_db
        from app.personalization import init_personalization_schema
        from app.data import CITY_AREAS, PROPERTY_TYPES
        from app.db_listings import upsert_listing
        import uvicorn

        init_db()
        init_personalization_schema()
        areas = {
            "karachi": ["DHA Defence", "Clifton", "Gulshan-e-Iqbal"],
            # Specs pick the first or second autocomplete option for "DHA" and
            # "Bah"; in Lahore those are DHA 11 Rahbar and Bahria Nasheman Iris.
            "lahore": ["DHA Defence", "Gulberg", "Bahria Town",
                       "DHA 11 Rahbar", "Bahria Nasheman Iris"],
            "islamabad": ["F 10", "G 11", "Bahria Town"],
        }
        # Furnishing evidence for tests/furnishing.spec.js: positive, two
        # negative wordings, and none (only shown under "Any").
        FURNISHING_TITLES = ("Furnished", "Unfurnished", "Non Furnished", "Brand new")
        zid = 99000000
        for city, names in areas.items():
            for name in names:
                slug, _, lat, lng = CITY_AREAS[city][name]
                for kind in ("apartment", "house", "upper_portion"):
                    for i in range(12):
                        zid += 1
                        upsert_listing(
                            zameen_id=str(zid),
                            url=f"https://www.zameen.com/Property/test-{zid}-1-1.html",
                            city=city, area_name=name, area_slug=slug, lat=lat, lng=lng,
                            card_data={
                                "title": f"{FURNISHING_TITLES[i % 4]} {kind} {zid}",
                                "price": 25000 + i * 5000, "price_text": "PKR 50 Thousand",
                                "bedrooms": i % 4 + 1, "bathrooms": 2,
                                "area_size": f"{i % 3 * 5 + 5} Marla",
                                "location": f"{name}, {city.title()}",
                                "property_type": PROPERTY_TYPES[kind]["label"],
                                "image_url": "/static/favicon-512.png",
                                "added": "Added: 1 hour ago",
                            },
                            # A third of listings carry an exact pin near the
                            # area centre, so map viewport mode has pins to show.
                            search_state={
                                "latitude": lat + (i - 6) * 0.0007,
                                "longitude": lng + (i % 4 - 2) * 0.0007,
                            } if i % 3 == 0 else None,
                        )
        # Stored HTML and conflicting fields exercise the real listing API.
        upsert_listing(
            zameen_id="99000001", url="https://www.zameen.com/Property/test-99000001-1-1.html",
            city="karachi", detail_data={
                "description": "<p>Apartment on the <b>third floor</b>.</p><ul><li>No lift available.</li><li>Water only at night.</li><li>Separate entrance &amp; parking.</li></ul><script>window.descriptionInjected = true</script>",
                "details": {"Floor": "2"},
            },
        )
        close_db()
        # uvicorn re-raises SIGTERM/SIGINT after shutting down. Turn that into
        # SystemExit so the TemporaryDirectory above is removed, not leaked.
        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, lambda *_: sys.exit(0))
        uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("PLAYWRIGHT_PORT", "8000")))


if __name__ == "__main__":
    main()
