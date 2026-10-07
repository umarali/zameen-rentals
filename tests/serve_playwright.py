"""Run browser tests with disposable data and no upstream scraping."""
import os
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    with tempfile.TemporaryDirectory(prefix="zameen-playwright-") as directory:
        os.environ["ZAMEENRENTALS_DB_DIR"] = directory
        os.environ["ZAMEENRENTALS_PLAYWRIGHT"] = "1"
        from app import app
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
                                "title": f"Furnished {kind} {zid}",
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
        close_db()
        uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("PLAYWRIGHT_PORT", "8000")))


if __name__ == "__main__":
    main()
