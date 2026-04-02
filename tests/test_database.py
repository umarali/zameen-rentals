"""Integration tests for database CRUD, upsert logic, FTS, and crawl state."""
import json
import pytest
from app.database import _get_conn, init_db
from app.db_listings import (
    upsert_listing, search_listings, get_listing_by_zameen_id,
    get_listings_needing_detail, mark_stale_listings, get_crawl_stats,
    content_hash, detail_hash,
)


class TestContentHash:
    def test_deterministic(self):
        h1 = content_hash(50000, "Test Flat", 2, 1, "5 Marla")
        h2 = content_hash(50000, "Test Flat", 2, 1, "5 Marla")
        assert h1 == h2

    def test_changes_on_price(self):
        h1 = content_hash(50000, "Test Flat", 2, 1, "5 Marla")
        h2 = content_hash(60000, "Test Flat", 2, 1, "5 Marla")
        assert h1 != h2


class TestUpsertListing:
    def test_insert_new(self):
        result = upsert_listing(
            zameen_id="100001", url="https://zameen.com/Property/test-100001-1-1.html",
            city="karachi", area_name="Clifton", area_slug="Karachi_Clifton",
            card_data={"title": "Test Flat", "price": 50000, "bedrooms": 2,
                       "bathrooms": 1, "area_size": "1000 sqft", "location": "Clifton",
                       "property_type": "Apartment"}
        )
        assert result == "inserted"

    def test_update_unchanged(self):
        card = {"title": "Test Flat", "price": 50000, "bedrooms": 2,
                "bathrooms": 1, "area_size": "1000 sqft"}
        upsert_listing(zameen_id="100002", url="https://zameen.com/Property/t-100002-1-1.html",
                       city="karachi", card_data=card)
        result = upsert_listing(zameen_id="100002", url="https://zameen.com/Property/t-100002-1-1.html",
                                city="karachi", card_data=card)
        assert result == "unchanged"

    def test_update_changed_price(self):
        card1 = {"title": "Test", "price": 50000, "bedrooms": 2, "bathrooms": 1, "area_size": "5 Marla"}
        card2 = {"title": "Test", "price": 60000, "bedrooms": 2, "bathrooms": 1, "area_size": "5 Marla"}
        upsert_listing(zameen_id="100003", url="https://zameen.com/Property/t-100003-1-1.html",
                       city="karachi", card_data=card1)
        result = upsert_listing(zameen_id="100003", url="https://zameen.com/Property/t-100003-1-1.html",
                                city="karachi", card_data=card2)
        assert result == "updated"

    def test_detail_update(self):
        card = {"title": "Test", "price": 50000, "bedrooms": 2, "bathrooms": 1, "area_size": "5 Marla"}
        upsert_listing(zameen_id="100004", url="https://zameen.com/Property/t-100004-1-1.html",
                       city="karachi", card_data=card)
        result = upsert_listing(zameen_id="100004", url="https://zameen.com/Property/t-100004-1-1.html",
                                city="karachi",
                                detail_data={"phone": "+923001234567", "description": "Nice flat"})
        assert result == "updated"

    def test_reactivate_inactive(self):
        """Insert, mark inactive, then re-insert should reactivate."""
        card = {"title": "Test", "price": 50000, "bedrooms": 2, "bathrooms": 1, "area_size": "5 Marla"}
        upsert_listing(zameen_id="100005", url="https://zameen.com/Property/t-100005-1-1.html",
                       city="karachi", card_data=card)
        conn = _get_conn()
        conn.execute("UPDATE listings SET is_active = 0 WHERE zameen_id = '100005'")
        conn.commit()
        result = upsert_listing(zameen_id="100005", url="https://zameen.com/Property/t-100005-1-1.html",
                                city="karachi", card_data=card)
        assert result == "unchanged"  # Same hash, but last_seen_at updated and is_active set to 1
        row = conn.execute("SELECT is_active FROM listings WHERE zameen_id = '100005'").fetchone()
        assert row["is_active"] == 1

    def test_detail_exact_coords_override_area_centroid(self):
        upsert_listing(
            zameen_id="100006",
            url="https://www.zameen.com/Property/t-100006-1-1.html",
            city="karachi",
            area_name="Clifton",
            area_slug="Karachi_Clifton",
            lat=24.8200,
            lng=67.0300,
            card_data={"title": "Geo Test", "price": 80000, "bedrooms": 2, "bathrooms": 2, "area_size": "900 sqft"},
        )
        result = upsert_listing(
            zameen_id="100006",
            url="https://www.zameen.com/Property/t-100006-1-1.html",
            city="karachi",
            detail_data={
                "description": "Exact map point available",
                "latitude": 24.812345,
                "longitude": 67.045678,
                "location_source": "listing_exact",
            },
        )
        assert result == "updated"
        listing = get_listing_by_zameen_id("100006")
        assert listing["latitude"] == pytest.approx(24.812345)
        assert listing["longitude"] == pytest.approx(67.045678)
        assert listing["location_source"] == "listing_exact"

    def test_card_refresh_does_not_overwrite_exact_coords(self):
        upsert_listing(
            zameen_id="100007",
            url="https://www.zameen.com/Property/t-100007-1-1.html",
            city="karachi",
            area_name="Clifton",
            area_slug="Karachi_Clifton",
            lat=24.8200,
            lng=67.0300,
            card_data={"title": "Geo Stable", "price": 70000, "bedrooms": 2, "bathrooms": 2, "area_size": "950 sqft"},
        )
        upsert_listing(
            zameen_id="100007",
            url="https://www.zameen.com/Property/t-100007-1-1.html",
            city="karachi",
            detail_data={
                "description": "Now exact",
                "latitude": 24.856789,
                "longitude": 67.098765,
                "location_source": "listing_exact",
            },
        )
        upsert_listing(
            zameen_id="100007",
            url="https://www.zameen.com/Property/t-100007-1-1.html",
            city="karachi",
            area_name="Clifton",
            area_slug="Karachi_Clifton",
            lat=24.8200,
            lng=67.0300,
            card_data={"title": "Geo Stable", "price": 72000, "bedrooms": 2, "bathrooms": 2, "area_size": "950 sqft"},
        )
        listing = get_listing_by_zameen_id("100007")
        assert listing["latitude"] == pytest.approx(24.856789)
        assert listing["longitude"] == pytest.approx(67.098765)
        assert listing["location_source"] == "listing_exact"

    def test_contact_only_update_keeps_detail_stale_until_real_detail(self):
        upsert_listing(
            zameen_id="100008",
            url="https://www.zameen.com/Property/t-100008-1-1.html",
            city="karachi",
            card_data={"title": "Contact Only", "price": 60000, "bedrooms": 2, "bathrooms": 1, "area_size": "5 Marla"},
        )
        result = upsert_listing(
            zameen_id="100008",
            url="https://www.zameen.com/Property/t-100008-1-1.html",
            city="karachi",
            detail_data={"call_phone": "+923001234567", "whatsapp_phone": "+923331234567", "contact_source": "showNumbers"},
        )
        assert result == "updated"
        listing = get_listing_by_zameen_id("100008")
        assert listing["call_phone"] == "+923001234567"
        assert listing["whatsapp_phone"] == "+923331234567"
        assert listing["contact_fetched_at"] is not None
        assert listing["detail_scraped_at"] is None


class TestSearchListings:
    def _seed(self, n=5):
        for i in range(n):
            upsert_listing(
                zameen_id=str(200000 + i),
                url=f"https://zameen.com/Property/t-{200000+i}-1-1.html",
                city="karachi", area_name="Clifton", area_slug="Karachi_Clifton",
                card_data={"title": f"Flat {i}", "price": 50000 + i * 10000,
                           "bedrooms": 2 + (i % 3), "bathrooms": 1,
                           "area_size": "1000 sqft", "property_type": "Apartment"}
            )

    def test_search_by_city(self):
        self._seed()
        result = search_listings(city="karachi")
        assert result["total"] == 5
        assert len(result["results"]) == 5

    def test_search_by_area(self):
        self._seed()
        result = search_listings(city="karachi", area="Clifton")
        assert result["total"] == 5

    def test_search_by_bedrooms(self):
        self._seed()
        result = search_listings(city="karachi", bedrooms=2)
        assert result["total"] >= 1
        for r in result["results"]:
            assert r["bedrooms"] == 2

    def test_search_by_price_range(self):
        self._seed()
        result = search_listings(city="karachi", price_min=60000, price_max=80000)
        for r in result["results"]:
            assert 60000 <= r["price"] <= 80000

    def test_sort_price_low(self):
        self._seed()
        result = search_listings(city="karachi", sort="price_low")
        prices = [r["price"] for r in result["results"] if r["price"]]
        assert prices == sorted(prices)

    def test_sort_price_high(self):
        self._seed()
        result = search_listings(city="karachi", sort="price_high")
        prices = [r["price"] for r in result["results"] if r["price"]]
        assert prices == sorted(prices, reverse=True)

    def test_pagination(self):
        self._seed(30)
        page1 = search_listings(city="karachi", page=1, per_page=10)
        page2 = search_listings(city="karachi", page=2, per_page=10)
        assert page1["total"] == 30
        assert len(page1["results"]) == 10
        assert len(page2["results"]) == 10
        ids1 = {r["url"] for r in page1["results"]}
        ids2 = {r["url"] for r in page2["results"]}
        assert ids1.isdisjoint(ids2)  # No overlap

    def test_empty_results(self):
        result = search_listings(city="lahore")
        assert result["total"] == 0
        assert result["results"] == []

    def test_fts_search(self):
        upsert_listing(
            zameen_id="300001", url="https://zameen.com/Property/t-300001-1-1.html",
            city="karachi", area_name="DHA Phase 5",
            card_data={"title": "Beautiful sea facing apartment", "price": 100000,
                       "bedrooms": 3, "bathrooms": 2, "area_size": "1500 sqft",
                       "property_type": "Apartment"}
        )
        result = search_listings(city="karachi", q="sea facing")
        assert result["total"] >= 1
        assert "sea" in result["results"][0]["title"].lower()


class TestGetListingByZameenId:
    def test_existing(self):
        upsert_listing(zameen_id="400001", url="https://zameen.com/Property/t-400001-1-1.html",
                       city="karachi", card_data={"title": "Test", "price": 50000,
                                                  "bedrooms": 2, "bathrooms": 1, "area_size": "5 Marla"})
        listing = get_listing_by_zameen_id("400001")
        assert listing is not None
        assert listing["zameen_id"] == "400001"

    def test_nonexistent(self):
        assert get_listing_by_zameen_id("999999") is None


class TestGetListingsNeedingDetail:
    def test_returns_listings_without_detail(self):
        upsert_listing(zameen_id="500001", url="https://zameen.com/Property/t-500001-1-1.html",
                       city="karachi", card_data={"title": "Test", "price": 50000,
                                                  "bedrooms": 2, "bathrooms": 1, "area_size": "5 Marla"})
        listings = get_listings_needing_detail(limit=10)
        assert len(listings) >= 1
        assert listings[0]["zameen_id"] == "500001"

    def test_returns_listings_without_exact_location(self):
        upsert_listing(
            zameen_id="500002",
            url="https://www.zameen.com/Property/t-500002-1-1.html",
            city="karachi",
            area_name="Clifton",
            area_slug="Karachi_Clifton",
            lat=24.8200,
            lng=67.0300,
            card_data={"title": "Needs exact pin", "price": 65000, "bedrooms": 2, "bathrooms": 1, "area_size": "5 Marla"},
        )
        upsert_listing(
            zameen_id="500002",
            url="https://www.zameen.com/Property/t-500002-1-1.html",
            city="karachi",
            detail_data={"description": "Scraped detail but no exact point yet"},
        )
        listings = get_listings_needing_detail(limit=10)
        assert any(item["zameen_id"] == "500002" for item in listings)


class TestMarkStaleListings:
    def test_marks_old_listings_inactive(self):
        upsert_listing(zameen_id="600001", url="https://zameen.com/Property/t-600001-1-1.html",
                       city="karachi", card_data={"title": "Old", "price": 50000,
                                                  "bedrooms": 2, "bathrooms": 1, "area_size": "5 Marla"})
        conn = _get_conn()
        conn.execute("UPDATE listings SET last_seen_at = datetime('now', '-10 days') WHERE zameen_id = '600001'")
        conn.commit()
        count = mark_stale_listings(days=7)
        assert count >= 1
        row = conn.execute("SELECT is_active FROM listings WHERE zameen_id = '600001'").fetchone()
        assert row["is_active"] == 0


class TestGetCrawlStats:
    def test_empty_db(self):
        stats = get_crawl_stats()
        assert stats["total_listings"] == 0
        assert stats["detail_coverage"] == 0

    def test_with_data(self):
        upsert_listing(zameen_id="700001", url="https://zameen.com/Property/t-700001-1-1.html",
                       city="karachi", card_data={"title": "Test", "price": 50000,
                                                  "bedrooms": 2, "bathrooms": 1, "area_size": "5 Marla"})
        stats = get_crawl_stats("karachi")
        assert stats["total_listings"] == 1

    def test_city_filter(self):
        upsert_listing(zameen_id="700002", url="https://zameen.com/Property/t-700002-1-1.html",
                       city="karachi", card_data={"title": "K", "price": 50000,
                                                  "bedrooms": 2, "bathrooms": 1, "area_size": "5"})
        upsert_listing(zameen_id="700003", url="https://zameen.com/Property/t-700003-1-1.html",
                       city="lahore", card_data={"title": "L", "price": 60000,
                                                 "bedrooms": 3, "bathrooms": 2, "area_size": "10"})
        assert get_crawl_stats("karachi")["total_listings"] == 1
        assert get_crawl_stats("lahore")["total_listings"] == 1
        assert get_crawl_stats()["total_listings"] == 2


class TestCrawlTypeState:
    def test_table_exists(self):
        conn = _get_conn()
        row = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='crawl_type_state'").fetchone()
        assert row is not None

    def test_insert_and_query(self):
        from app.crawler_worker import _update_type_state, _get_empty_types
        _update_type_state("karachi", "Karachi_Clifton", "Rentals_Rooms", 0)
        _update_type_state("karachi", "Karachi_Clifton", "Rentals_Houses_Property", 25)
        empty = _get_empty_types("karachi", "Karachi_Clifton")
        assert "Rentals_Rooms" in empty
        assert "Rentals_Houses_Property" not in empty
