"""Integration tests for database CRUD, upsert logic, FTS, and crawl state."""
import json
import pytest
from app.database import _get_conn, init_db
from app.db_listings import (
    upsert_listing, search_listings, get_listing_by_zameen_id,
    get_listings_needing_detail, mark_stale_listings, get_crawl_stats,
    content_hash, detail_hash, search_exact_listings_in_bounds, search_nearby_listings,
    get_nearby_enrichment_candidates,
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

    def test_contact_only_update_does_not_backfill_whatsapp_from_call_phone(self):
        upsert_listing(
            zameen_id="100009",
            url="https://www.zameen.com/Property/t-100009-1-1.html",
            city="karachi",
            card_data={"title": "Call Only", "price": 65000, "bedrooms": 2, "bathrooms": 1, "area_size": "5 Marla"},
        )

        upsert_listing(
            zameen_id="100009",
            url="https://www.zameen.com/Property/t-100009-1-1.html",
            city="karachi",
            detail_data={"call_phone": "+922134567890", "whatsapp_phone": None, "contact_source": "showNumbers"},
        )

        listing = get_listing_by_zameen_id("100009")
        assert listing["call_phone"] == "+922134567890"
        assert listing["whatsapp_phone"] is None


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

    def test_viewport_search_prioritizes_results_near_map_center(self):
        upsert_listing(
            zameen_id="300010",
            url="https://zameen.com/Property/t-300010-1-1.html",
            city="karachi",
            area_name="Clifton",
            area_slug="Karachi_Clifton",
            lat=24.8201,
            lng=67.0301,
            card_data={"title": "Near focus", "price": 120000, "bedrooms": 3, "bathrooms": 2, "area_size": "1500 sqft", "property_type": "Apartment"},
        )
        upsert_listing(
            zameen_id="300011",
            url="https://zameen.com/Property/t-300011-1-1.html",
            city="karachi",
            area_name="DHA Phase 5",
            area_slug="Karachi_DHA_Phase_5",
            lat=24.7900,
            lng=67.1000,
            card_data={"title": "Far focus", "price": 90000, "bedrooms": 2, "bathrooms": 2, "area_size": "1200 sqft", "property_type": "Apartment"},
        )
        conn = _get_conn()
        conn.execute(
            "UPDATE listings SET last_seen_at = '9999-01-01T00:00:00' WHERE zameen_id = '300011'"
        )
        conn.commit()

        result = search_listings(
            city="karachi",
            area_names=["Clifton", "DHA Phase 5"],
            center_lat=24.8200,
            center_lng=67.0300,
        )

        assert result["ranking"] == "map_focus"
        assert result["results"][0]["title"] == "Near focus"
        assert result["results"][0]["distance_to_center"] < result["results"][1]["distance_to_center"]

    def test_viewport_search_keeps_explicit_sort_and_uses_distance_as_tiebreaker(self):
        upsert_listing(
            zameen_id="300012",
            url="https://zameen.com/Property/t-300012-1-1.html",
            city="karachi",
            area_name="Clifton",
            area_slug="Karachi_Clifton",
            lat=24.8201,
            lng=67.0301,
            card_data={"title": "Cheaper and near", "price": 80000, "bedrooms": 2, "bathrooms": 2, "area_size": "1200 sqft", "property_type": "Apartment"},
        )
        upsert_listing(
            zameen_id="300013",
            url="https://zameen.com/Property/t-300013-1-1.html",
            city="karachi",
            area_name="DHA Phase 5",
            area_slug="Karachi_DHA_Phase_5",
            lat=24.7900,
            lng=67.1000,
            card_data={"title": "Cheaper but far", "price": 80000, "bedrooms": 2, "bathrooms": 2, "area_size": "1200 sqft", "property_type": "Apartment"},
        )

        result = search_listings(
            city="karachi",
            area_names=["Clifton", "DHA Phase 5"],
            sort="price_low",
            center_lat=24.8200,
            center_lng=67.0300,
        )

        assert result["results"][0]["title"] == "Cheaper and near"

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


class TestNearbySearchListings:
    def test_nearby_search_returns_exact_only_results_with_distance_fields(self):
        upsert_listing(
            zameen_id="350001",
            url="https://zameen.com/Property/t-350001-1-1.html",
            city="karachi",
            area_name="Clifton",
            area_slug="Karachi_Clifton",
            lat=24.8200,
            lng=67.0300,
            card_data={"title": "Exact nearby", "price": 95000, "bedrooms": 2, "bathrooms": 2, "area_size": "1200 sqft", "property_type": "Apartment"},
        )
        upsert_listing(
            zameen_id="350001",
            url="https://zameen.com/Property/t-350001-1-1.html",
            city="karachi",
            detail_data={
                "description": "Exact nearby detail",
                "latitude": 24.8212,
                "longitude": 67.0311,
                "location_source": "listing_exact",
            },
        )
        upsert_listing(
            zameen_id="350002",
            url="https://zameen.com/Property/t-350002-1-1.html",
            city="karachi",
            area_name="Clifton",
            area_slug="Karachi_Clifton",
            lat=24.8200,
            lng=67.0300,
            card_data={"title": "Centroid only", "price": 85000, "bedrooms": 2, "bathrooms": 2, "area_size": "1100 sqft", "property_type": "Apartment"},
        )
        upsert_listing(
            zameen_id="350003",
            url="https://zameen.com/Property/t-350003-1-1.html",
            city="karachi",
            area_name="DHA Phase 5",
            area_slug="Karachi_DHA_Phase_5",
            lat=24.7900,
            lng=67.1000,
            card_data={"title": "Exact but far", "price": 120000, "bedrooms": 3, "bathrooms": 2, "area_size": "1500 sqft", "property_type": "Apartment"},
        )
        upsert_listing(
            zameen_id="350003",
            url="https://zameen.com/Property/t-350003-1-1.html",
            city="karachi",
            detail_data={
                "description": "Exact far detail",
                "latitude": 24.7900,
                "longitude": 67.1000,
                "location_source": "listing_exact",
            },
        )

        result = search_nearby_listings(
            city="karachi",
            lat=24.8200,
            lng=67.0300,
            radius_km=5,
        )

        assert result["total"] == 1
        assert result["results"][0]["title"] == "Exact nearby"
        assert result["results"][0]["distance_source"] == "listing_exact"
        assert result["results"][0]["is_distance_approximate"] is False
        assert result["results"][0]["distance_km"] < 1

    def test_nearby_search_keeps_explicit_sort_and_uses_distance_tiebreaker(self):
        for zameen_id, title, lat, lng in (
            ("350010", "Cheaper and near", 24.8202, 67.0302),
            ("350011", "Cheaper but farther", 24.8265, 67.0385),
        ):
            upsert_listing(
                zameen_id=zameen_id,
                url=f"https://zameen.com/Property/t-{zameen_id}-1-1.html",
                city="karachi",
                area_name="Clifton",
                area_slug="Karachi_Clifton",
                lat=24.8200,
                lng=67.0300,
                card_data={"title": title, "price": 80000, "bedrooms": 2, "bathrooms": 2, "area_size": "1000 sqft", "property_type": "Apartment"},
            )
            upsert_listing(
                zameen_id=zameen_id,
                url=f"https://zameen.com/Property/t-{zameen_id}-1-1.html",
                city="karachi",
                detail_data={
                    "description": title,
                    "latitude": lat,
                    "longitude": lng,
                    "location_source": "listing_exact",
                },
            )

        result = search_nearby_listings(
            city="karachi",
            lat=24.8200,
            lng=67.0300,
            radius_km=5,
            sort="price_low",
        )

        assert result["total"] == 2
        assert result["results"][0]["title"] == "Cheaper and near"
        assert result["results"][0]["distance_km"] < result["results"][1]["distance_km"]

    def test_nearby_enrichment_candidates_only_return_centroid_backed_matches(self):
        upsert_listing(
            zameen_id="350020",
            url="https://zameen.com/Property/t-350020-1-1.html",
            city="karachi",
            area_name="Clifton",
            area_slug="Karachi_Clifton",
            lat=24.8204,
            lng=67.0304,
            card_data={"title": "Centroid close", "price": 78000, "bedrooms": 2, "bathrooms": 1, "area_size": "900 sqft", "property_type": "Apartment"},
        )
        upsert_listing(
            zameen_id="350021",
            url="https://zameen.com/Property/t-350021-1-1.html",
            city="karachi",
            area_name="Clifton",
            area_slug="Karachi_Clifton",
            lat=24.8230,
            lng=67.0340,
            card_data={"title": "Centroid farther", "price": 82000, "bedrooms": 2, "bathrooms": 1, "area_size": "950 sqft", "property_type": "Apartment"},
        )
        upsert_listing(
            zameen_id="350022",
            url="https://zameen.com/Property/t-350022-1-1.html",
            city="karachi",
            area_name="Clifton",
            area_slug="Karachi_Clifton",
            lat=24.8200,
            lng=67.0300,
            card_data={"title": "Already exact", "price": 90000, "bedrooms": 2, "bathrooms": 2, "area_size": "1000 sqft", "property_type": "Apartment"},
        )
        upsert_listing(
            zameen_id="350022",
            url="https://zameen.com/Property/t-350022-1-1.html",
            city="karachi",
            detail_data={
                "description": "Exact pin",
                "latitude": 24.8208,
                "longitude": 67.0308,
                "location_source": "listing_exact",
            },
        )

        candidates = get_nearby_enrichment_candidates(
            city="karachi",
            lat=24.8200,
            lng=67.0300,
            radius_km=5,
        )

        assert [candidate["zameen_id"] for candidate in candidates] == ["350020", "350021"]
        assert candidates[0]["distance_km"] <= candidates[1]["distance_km"]

    def test_geo_index_exists_for_active_geocoded_listings(self):
        conn = _get_conn()
        indexes = conn.execute("PRAGMA index_list(listings)").fetchall()
        assert any(index["name"] == "idx_listings_geo_active" for index in indexes)


class TestViewportBoundsSearch:
    def test_exact_bounds_search_orders_results_using_latitude_corrected_center_distance(self):
        upsert_listing(
            zameen_id="360010",
            url="https://zameen.com/Property/t-360010-1-1.html",
            city="karachi",
            area_name="Clifton",
            area_slug="Karachi_Clifton",
            lat=24.8200,
            lng=67.0280,
            card_data={"title": "North of center", "price": 125000, "bedrooms": 4, "bathrooms": 3, "area_size": "500 sqft", "property_type": "House"},
        )
        upsert_listing(
            zameen_id="360010",
            url="https://zameen.com/Property/t-360010-1-1.html",
            city="karachi",
            detail_data={
                "description": "North of center",
                "latitude": 24.830000,
                "longitude": 67.030000,
                "location_source": "listing_exact",
            },
        )
        upsert_listing(
            zameen_id="360011",
            url="https://zameen.com/Property/t-360011-1-1.html",
            city="karachi",
            area_name="Clifton",
            area_slug="Karachi_Clifton",
            lat=24.8200,
            lng=67.0280,
            card_data={"title": "East but closer", "price": 125000, "bedrooms": 4, "bathrooms": 3, "area_size": "500 sqft", "property_type": "House"},
        )
        upsert_listing(
            zameen_id="360011",
            url="https://zameen.com/Property/t-360011-1-1.html",
            city="karachi",
            detail_data={
                "description": "East but closer",
                "latitude": 24.820000,
                "longitude": 67.040500,
                "location_source": "listing_exact",
            },
        )

        result = search_exact_listings_in_bounds(
            city="karachi",
            south=24.818,
            west=67.028,
            north=24.832,
            east=67.041,
            property_type="house",
            center_lat=24.820,
            center_lng=67.030,
        )

        assert result["total"] == 2
        assert result["results"][0]["title"] == "East but closer"
        assert result["results"][0]["distance_to_center"] < result["results"][1]["distance_to_center"]

    def test_exact_bounds_search_returns_visible_exact_listings(self):
        upsert_listing(
            zameen_id="360001",
            url="https://zameen.com/Property/t-360001-1-1.html",
            city="karachi",
            area_name="Clifton",
            area_slug="Karachi_Clifton",
            lat=24.8200,
            lng=67.0280,
            card_data={"title": "Visible exact house", "price": 125000, "bedrooms": 4, "bathrooms": 3, "area_size": "500 sqft", "property_type": "House"},
        )
        upsert_listing(
            zameen_id="360001",
            url="https://zameen.com/Property/t-360001-1-1.html",
            city="karachi",
            detail_data={
                "description": "Visible exact house",
                "latitude": 24.826625,
                "longitude": 67.037923,
                "location_source": "listing_exact",
            },
        )
        upsert_listing(
            zameen_id="360002",
            url="https://zameen.com/Property/t-360002-1-1.html",
            city="karachi",
            area_name="Clifton",
            area_slug="Karachi_Clifton",
            lat=24.8200,
            lng=67.0280,
            card_data={"title": "Outside bounds", "price": 110000, "bedrooms": 4, "bathrooms": 3, "area_size": "500 sqft", "property_type": "House"},
        )
        upsert_listing(
            zameen_id="360002",
            url="https://zameen.com/Property/t-360002-1-1.html",
            city="karachi",
            detail_data={
                "description": "Outside bounds",
                "latitude": 24.840000,
                "longitude": 67.060000,
                "location_source": "listing_exact",
            },
        )

        result = search_exact_listings_in_bounds(
            city="karachi",
            south=24.824,
            west=67.034,
            north=24.833,
            east=67.040,
            property_type="house",
            center_lat=24.828,
            center_lng=67.038,
        )

        assert result["total"] == 1
        assert result["results"][0]["title"] == "Visible exact house"
        assert result["area_totals"] == {"Clifton": 1}


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
