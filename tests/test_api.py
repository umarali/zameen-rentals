"""API endpoint tests using FastAPI TestClient."""
import asyncio
import pytest
from fastapi.testclient import TestClient
from app import app
from app.database import _get_conn
from app.db_listings import upsert_listing, get_listing_by_zameen_id


@pytest.fixture
def client():
    return TestClient(app)


class TestHealthEndpoint:
    def test_health(self, client):
        res = client.get("/api/health")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "ok"
        assert data["service"] == "ZameenRentals"


class TestCitiesEndpoint:
    def test_returns_three_cities(self, client):
        res = client.get("/api/cities")
        assert res.status_code == 200
        cities = res.json()
        assert len(cities) == 3
        keys = [c["key"] for c in cities]
        assert "karachi" in keys
        assert "lahore" in keys
        assert "islamabad" in keys


class TestAreasEndpoint:
    def test_default_karachi(self, client):
        res = client.get("/api/areas")
        assert res.status_code == 200
        areas = res.json()
        assert len(areas) > 300

    def test_lahore(self, client):
        res = client.get("/api/areas?city=lahore")
        assert res.status_code == 200
        areas = res.json()
        assert len(areas) > 400

    def test_area_has_fields(self, client):
        res = client.get("/api/areas?city=karachi")
        area = res.json()[0]
        assert "name" in area
        assert "slug" in area
        assert "id" in area
        assert "lat" in area
        assert "lng" in area


class TestSearchAreasEndpoint:
    def test_fuzzy_search(self, client):
        res = client.get("/api/search-areas?q=dha&city=karachi&limit=5")
        assert res.status_code == 200
        results = res.json()
        assert len(results) > 0
        assert any("dha" in r["name"].lower() for r in results)

    def test_respects_limit(self, client):
        res = client.get("/api/search-areas?q=a&city=karachi&limit=3")
        assert len(res.json()) <= 3


class TestPropertyTypesEndpoint:
    def test_returns_types(self, client):
        res = client.get("/api/property-types")
        assert res.status_code == 200
        types = res.json()
        assert len(types) >= 7
        keys = [t["key"] for t in types]
        assert "house" in keys
        assert "apartment" in keys
        assert "flat" not in keys  # Alias excluded


class TestParseQueryEndpoint:
    def test_parse_query_timeout_falls_back_to_regex(self, client, monkeypatch):
        async def slow_parse(*args, **kwargs):
            await asyncio.sleep(0.05)
            return {"area": "Should not win"}

        monkeypatch.setattr("app.routes.parse_query_with_claude", slow_parse)
        monkeypatch.setattr("app.routes._PARSE_QUERY_TIMEOUT_SECONDS", 0.01)

        res = client.get("/api/parse-query?q=2+bed+in+Clifton&city=karachi")

        assert res.status_code == 200
        data = res.json()
        assert data["filters"]["bedrooms"] == 2
        assert data["filters"]["area"] == "Clifton"


class TestSearchEndpoint:
    def _seed_listings(self):
        for i in range(5):
            upsert_listing(
                zameen_id=str(800000 + i),
                url=f"https://zameen.com/Property/t-{800000+i}-1-1.html",
                city="karachi", area_name="DHA Phase 5",
                card_data={"title": f"Flat {i}", "price": 50000 + i * 10000,
                           "bedrooms": 2, "bathrooms": 1, "area_size": "1000 sqft",
                           "property_type": "Apartment"}
            )

    def test_search_returns_local_results(self, client):
        self._seed_listings()
        res = client.get("/api/search?city=karachi&area=DHA+Phase+5")
        assert res.status_code == 200
        data = res.json()
        assert data["source"] == "local"
        assert data["total"] == 5

    def test_search_with_filters(self, client):
        self._seed_listings()
        res = client.get("/api/search?city=karachi&bedrooms=2&price_max=70000")
        data = res.json()
        assert data["total"] >= 1
        for r in data["results"]:
            assert r["bedrooms"] == 2

    def test_search_empty_city(self, client):
        res = client.get("/api/search?city=lahore")
        data = res.json()
        # Either local empty → falls back to live, or returns empty local results
        assert "total" in data or "results" in data

    def test_search_rejects_inverted_price_range(self, client):
        res = client.get("/api/search?city=karachi&price_min=100000&price_max=50000")

        assert res.status_code == 400
        assert "price_min" in res.json()["detail"]


class TestCrawlStatusEndpoint:
    def test_returns_stats(self, client):
        res = client.get("/api/crawl-status")
        assert res.status_code == 200
        data = res.json()
        assert "total_listings" in data
        assert "detail_coverage" in data
        assert "areas_crawled" in data
        assert "areas_total" in data

    def test_city_filter(self, client):
        res = client.get("/api/crawl-status?city=karachi")
        assert res.status_code == 200


class TestListingDetailEndpoint:
    def test_invalid_url_rejected(self, client):
        res = client.get("/api/listing-detail?url=https://evil.com/page")
        assert res.status_code == 400

    def test_local_detail_returned(self, client):
        upsert_listing(
            zameen_id="900001",
            url="https://www.zameen.com/Property/test-900001-1-1.html",
            city="karachi",
            card_data={"title": "Test", "price": 50000, "bedrooms": 2,
                       "bathrooms": 1, "area_size": "5 Marla"}
        )
        upsert_listing(
            zameen_id="900001",
            url="https://www.zameen.com/Property/test-900001-1-1.html",
            city="karachi",
            detail_data={"phone": "+923001234567", "description": "Nice flat",
                         "features": ["AC"], "amenities": ["Parking"]}
        )
        res = client.get("/api/listing-detail?url=https://www.zameen.com/Property/test-900001-1-1.html")
        assert res.status_code == 200
        data = res.json()
        assert data.get("source") == "local"
        assert data["phone"] == "+923001234567"

    def test_local_detail_preserves_distinct_phone_and_call_phone(self, client):
        upsert_listing(
            zameen_id="900007",
            url="https://www.zameen.com/Property/test-900007-1-1.html",
            city="karachi",
            card_data={"title": "Distinct contact", "price": 51000, "bedrooms": 2, "bathrooms": 1, "area_size": "5 Marla"},
        )
        upsert_listing(
            zameen_id="900007",
            url="https://www.zameen.com/Property/test-900007-1-1.html",
            city="karachi",
            detail_data={
                "phone": "+923001234567",
                "call_phone": "+922134567890",
                "description": "Distinct contact",
                "latitude": 24.8112,
                "longitude": 67.0445,
                "location_source": "listing_exact",
            },
        )

        res = client.get("/api/listing-detail?url=https://www.zameen.com/Property/test-900007-1-1.html")

        assert res.status_code == 200
        data = res.json()
        assert data["phone"] == "+923001234567"
        assert data["call_phone"] == "+922134567890"

    def test_local_detail_does_not_fallback_whatsapp_to_call_phone(self, client):
        upsert_listing(
            zameen_id="900005",
            url="https://www.zameen.com/Property/test-900005-1-1.html",
            city="karachi",
            card_data={"title": "Call only", "price": 50000, "bedrooms": 2, "bathrooms": 1, "area_size": "5 Marla"},
        )
        upsert_listing(
            zameen_id="900005",
            url="https://www.zameen.com/Property/test-900005-1-1.html",
            city="karachi",
            detail_data={"call_phone": "+922134567890", "whatsapp_phone": None, "description": "Call only"},
        )

        res = client.get("/api/listing-detail?url=https://www.zameen.com/Property/test-900005-1-1.html")

        assert res.status_code == 200
        data = res.json()
        assert data["call_phone"] == "+922134567890"
        assert data["whatsapp_phone"] is None

    def test_local_detail_ignores_corrupt_json_payloads(self, client):
        upsert_listing(
            zameen_id="900008",
            url="https://www.zameen.com/Property/test-900008-1-1.html",
            city="karachi",
            card_data={"title": "Corrupt detail JSON", "price": 52000, "bedrooms": 2, "bathrooms": 1, "area_size": "5 Marla"},
        )
        upsert_listing(
            zameen_id="900008",
            url="https://www.zameen.com/Property/test-900008-1-1.html",
            city="karachi",
            detail_data={
                "description": "Stored locally",
                "latitude": 24.8113,
                "longitude": 67.0446,
                "location_source": "listing_exact",
            },
        )
        conn = _get_conn()
        conn.execute(
            """
            UPDATE listings
            SET features_json = '[broken-json',
                amenities_json = '[broken-json',
                details_json = '{broken-json',
                detail_images_json = '[broken-json'
            WHERE zameen_id = '900008'
            """
        )
        conn.commit()

        res = client.get("/api/listing-detail?url=https://www.zameen.com/Property/test-900008-1-1.html")

        assert res.status_code == 200
        data = res.json()
        assert data["features"] == []
        assert data["amenities"] == []
        assert data["details"] == {}
        assert data["images"] == []

    def test_local_detail_includes_exact_geography(self, client):
        upsert_listing(
            zameen_id="900003",
            url="https://www.zameen.com/Property/test-900003-1-1.html",
            city="karachi",
            area_name="Clifton",
            area_slug="Karachi_Clifton",
            lat=24.82,
            lng=67.03,
            card_data={"title": "Pinned", "price": 90000, "bedrooms": 3, "bathrooms": 2, "area_size": "8 Marla"},
        )
        upsert_listing(
            zameen_id="900003",
            url="https://www.zameen.com/Property/test-900003-1-1.html",
            city="karachi",
            detail_data={
                "phone": "+923001111111",
                "description": "Exact detail",
                "latitude": 24.8111,
                "longitude": 67.0444,
                "location_source": "listing_exact",
            },
        )
        res = client.get("/api/listing-detail?url=https://www.zameen.com/Property/test-900003-1-1.html")
        assert res.status_code == 200
        data = res.json()
        assert data["has_exact_geography"] is True
        assert data["latitude"] == pytest.approx(24.8111)
        assert data["longitude"] == pytest.approx(67.0444)

    def test_live_detail_persists_exact_geography_when_local_detail_is_only_area_level(self, client, monkeypatch):
        upsert_listing(
            zameen_id="900004",
            url="https://www.zameen.com/Property/test-900004-1-1.html",
            city="karachi",
            area_name="Clifton",
            area_slug="Karachi_Clifton",
            lat=24.82,
            lng=67.03,
            card_data={"title": "Needs refresh", "price": 91000, "bedrooms": 3, "bathrooms": 2, "area_size": "8 Marla"},
        )
        upsert_listing(
            zameen_id="900004",
            url="https://www.zameen.com/Property/test-900004-1-1.html",
            city="karachi",
            detail_data={"description": "Old detail"},
        )

        async def fake_fetch_listing_detail(url):
            return {
                "description": "Fresh detail",
                "latitude": 24.8222,
                "longitude": 67.0555,
                "location_source": "listing_exact",
                "has_exact_geography": True,
            }

        monkeypatch.setattr("app.routes.fetch_listing_detail", fake_fetch_listing_detail)

        res = client.get("/api/listing-detail?url=https://www.zameen.com/Property/test-900004-1-1.html")
        assert res.status_code == 200
        data = res.json()
        assert data["has_exact_geography"] is True
        listing = get_listing_by_zameen_id("900004")
        assert listing["location_source"] == "listing_exact"
        assert listing["latitude"] == pytest.approx(24.8222)
        assert listing["longitude"] == pytest.approx(67.0555)


class TestListingPhoneEndpoint:
    def test_invalid_url(self, client):
        res = client.get("/api/listing-phone?url=https://evil.com/page")
        assert res.status_code == 400

    def test_returns_phone_from_db(self, client):
        upsert_listing(
            zameen_id="900002",
            url="https://www.zameen.com/Property/test-900002-1-1.html",
            city="karachi",
            card_data={"title": "Test", "price": 50000, "bedrooms": 2,
                       "bathrooms": 1, "area_size": "5 Marla"}
        )
        upsert_listing(
            zameen_id="900002",
            url="https://www.zameen.com/Property/test-900002-1-1.html",
            city="karachi",
            detail_data={"phone": "+923009876543", "description": "Test"}
        )
        res = client.get("/api/listing-phone?url=https://www.zameen.com/Property/test-900002-1-1.html")
        data = res.json()
        assert data["phone"] == "+923009876543"


class TestListingContactEndpoint:
    def test_local_contact_does_not_fallback_whatsapp_to_call_phone(self, client):
        upsert_listing(
            zameen_id="900006",
            url="https://www.zameen.com/Property/test-900006-1-1.html",
            city="karachi",
            card_data={"title": "Call only", "price": 60000, "bedrooms": 2, "bathrooms": 1, "area_size": "5 Marla"},
        )
        upsert_listing(
            zameen_id="900006",
            url="https://www.zameen.com/Property/test-900006-1-1.html",
            city="karachi",
            detail_data={"call_phone": "+922134567891", "whatsapp_phone": None, "contact_source": "showNumbers"},
        )

        res = client.get("/api/listing-contact?url=https://www.zameen.com/Property/test-900006-1-1.html")

        assert res.status_code == 200
        data = res.json()
        assert data["call_phone"] == "+922134567891"
        assert data["whatsapp_phone"] is None

    def test_local_contact_preserves_distinct_phone_and_call_phone(self, client):
        upsert_listing(
            zameen_id="900009",
            url="https://www.zameen.com/Property/test-900009-1-1.html",
            city="karachi",
            card_data={"title": "Distinct contact", "price": 62000, "bedrooms": 2, "bathrooms": 1, "area_size": "5 Marla"},
        )
        upsert_listing(
            zameen_id="900009",
            url="https://www.zameen.com/Property/test-900009-1-1.html",
            city="karachi",
            detail_data={
                "phone": "+923009876543",
                "call_phone": "+922134567892",
                "contact_source": "showNumbers",
            },
        )

        res = client.get("/api/listing-contact?url=https://www.zameen.com/Property/test-900009-1-1.html")

        assert res.status_code == 200
        data = res.json()
        assert data["phone"] == "+923009876543"
        assert data["call_phone"] == "+922134567892"


class TestMapSearchEndpoint:
    def test_map_search_orders_results_near_viewport_center(self, client):
        upsert_listing(
            zameen_id="910001",
            url="https://www.zameen.com/Property/test-910001-1-1.html",
            city="karachi",
            area_name="Clifton",
            area_slug="Karachi_Clifton",
            lat=24.8201,
            lng=67.0301,
            card_data={"title": "Near viewport", "price": 85000, "bedrooms": 2, "bathrooms": 2, "area_size": "5 Marla", "property_type": "Apartment"},
        )
        upsert_listing(
            zameen_id="910002",
            url="https://www.zameen.com/Property/test-910002-1-1.html",
            city="karachi",
            area_name="DHA Phase 5",
            area_slug="Karachi_DHA_Phase_5",
            lat=24.7900,
            lng=67.1000,
            card_data={"title": "Far viewport", "price": 86000, "bedrooms": 2, "bathrooms": 2, "area_size": "5 Marla", "property_type": "Apartment"},
        )

        res = client.get(
            "/api/map-search?city=karachi&areas=Clifton&areas=DHA+Phase+5&center_lat=24.82&center_lng=67.03"
        )
        assert res.status_code == 200
        data = res.json()
        assert data["mode"] == "viewport"
        assert data["ranking"] == "map_focus"
        assert data["focus_center"] == {"lat": 24.82, "lng": 67.03}
        assert data["results"][0]["title"] == "Near viewport"

    def test_map_search_accepts_explicit_distance_sort_and_returns_distance_fields(self, client):
        upsert_listing(
            zameen_id="910003",
            url="https://www.zameen.com/Property/test-910003-1-1.html",
            city="karachi",
            area_name="Clifton",
            area_slug="Karachi_Clifton",
            lat=24.8230,
            lng=67.0340,
            card_data={"title": "Approximate viewport distance", "price": 87000, "bedrooms": 2, "bathrooms": 2, "area_size": "5 Marla", "property_type": "Apartment"},
        )

        res = client.get(
            "/api/map-search?city=karachi&areas=Clifton&center_lat=24.82&center_lng=67.03&sort=distance"
        )

        assert res.status_code == 200
        data = res.json()
        assert data["results"][0]["title"] == "Approximate viewport distance"
        assert data["results"][0]["distance_source"] == "area_centroid"
        assert data["results"][0]["is_distance_approximate"] is True
        assert data["results"][0]["distance_km"] > 0

    def test_map_search_rejects_excessive_area_count(self, client):
        query = "&".join(f"areas=A{i}" for i in range(501))

        res = client.get(f"/api/map-search?city=karachi&{query}")

        assert res.status_code == 400
        assert "Too many areas" in res.json()["detail"]

    def test_map_search_rejects_partial_bounds(self, client):
        res = client.get("/api/map-search?city=karachi&south=24.82&north=24.83")

        assert res.status_code == 400
        assert "required together" in res.json()["detail"]

    def test_map_search_rejects_inverted_bounds(self, client):
        res = client.get("/api/map-search?city=karachi&south=24.83&west=67.03&north=24.82&east=67.04")

        assert res.status_code == 400
        assert "south must be less than north" in res.json()["detail"]

    def test_map_search_uses_exact_bounds_results_even_without_visible_area_centroids(self, client):
        upsert_listing(
            zameen_id="910010",
            url="https://www.zameen.com/Property/test-910010-1-1.html",
            city="karachi",
            area_name="Clifton",
            area_slug="Karachi_Clifton",
            lat=24.8200,
            lng=67.0280,
            card_data={"title": "Exact in bounds", "price": 125000, "bedrooms": 4, "bathrooms": 3, "area_size": "5 Marla", "property_type": "House"},
        )
        upsert_listing(
            zameen_id="910010",
            url="https://www.zameen.com/Property/test-910010-1-1.html",
            city="karachi",
            detail_data={
                "description": "Exact in bounds",
                "latitude": 24.826625,
                "longitude": 67.037923,
                "location_source": "listing_exact",
            },
        )

        res = client.get(
            "/api/map-search?city=karachi&property_type=house&center_lat=24.828&center_lng=67.038&south=24.824&west=67.034&north=24.833&east=67.040"
        )

        assert res.status_code == 200
        data = res.json()
        assert data["mode"] == "viewport"
        assert data["scope"] == "exact_bounds"
        assert data["total"] == 1
        assert data["results"][0]["title"] == "Exact in bounds"
        assert data["area_totals"] == {"Clifton": 1}
        assert data["attempted_exact_bounds"] is True
        assert data["exact_bounds_total"] == 1

    def test_map_search_reports_empty_exact_bounds_before_falling_back_to_area_coverage(self, client):
        upsert_listing(
            zameen_id="910020",
            url="https://www.zameen.com/Property/test-910020-1-1.html",
            city="karachi",
            area_name="Clifton",
            area_slug="Karachi_Clifton",
            lat=24.8100,
            lng=67.0200,
            card_data={"title": "Area coverage fallback", "price": 95000, "bedrooms": 3, "bathrooms": 2, "area_size": "5 Marla", "property_type": "House"},
        )

        res = client.get(
            "/api/map-search?city=karachi&areas=Clifton&property_type=house&center_lat=24.828&center_lng=67.038&south=24.824&west=67.034&north=24.833&east=67.040"
        )

        assert res.status_code == 200
        data = res.json()
        assert data["mode"] == "viewport"
        assert data["scope"] == "area_coverage"
        assert data["attempted_exact_bounds"] is True
        assert data["exact_bounds_total"] == 0
        assert data["total"] == 1
        assert data["results"][0]["title"] == "Area coverage fallback"

    def test_map_search_returns_empty_exact_bounds_scope_when_no_visible_areas_exist(self, client):
        res = client.get(
            "/api/map-search?city=karachi&center_lat=24.828&center_lng=67.038&south=24.824&west=67.034&north=24.833&east=67.040"
        )

        assert res.status_code == 200
        data = res.json()
        assert data["mode"] == "viewport"
        assert data["scope"] == "exact_bounds"
        assert data["attempted_exact_bounds"] is True
        assert data["exact_bounds_total"] == 0
        assert data["total"] == 0
        assert data["area_totals"] == {}


class TestNearbySearchEndpoint:
    def test_nearby_search_returns_exact_only_results(self, client):
        upsert_listing(
            zameen_id="920001",
            url="https://www.zameen.com/Property/test-920001-1-1.html",
            city="karachi",
            area_name="Clifton",
            area_slug="Karachi_Clifton",
            lat=24.8200,
            lng=67.0300,
            card_data={"title": "Near me exact", "price": 88000, "bedrooms": 2, "bathrooms": 2, "area_size": "5 Marla", "property_type": "Apartment"},
        )
        upsert_listing(
            zameen_id="920001",
            url="https://www.zameen.com/Property/test-920001-1-1.html",
            city="karachi",
            detail_data={
                "description": "Exact nearby detail",
                "latitude": 24.8210,
                "longitude": 67.0310,
                "location_source": "listing_exact",
            },
        )
        upsert_listing(
            zameen_id="920002",
            url="https://www.zameen.com/Property/test-920002-1-1.html",
            city="karachi",
            area_name="Clifton",
            area_slug="Karachi_Clifton",
            lat=24.8205,
            lng=67.0305,
            card_data={"title": "Centroid only", "price": 76000, "bedrooms": 2, "bathrooms": 1, "area_size": "4 Marla", "property_type": "Apartment"},
        )
        upsert_listing(
            zameen_id="920003",
            url="https://www.zameen.com/Property/test-920003-1-1.html",
            city="karachi",
            area_name="DHA Phase 5",
            area_slug="Karachi_DHA_Phase_5",
            lat=24.7900,
            lng=67.1000,
            card_data={"title": "Far away exact", "price": 120000, "bedrooms": 3, "bathrooms": 2, "area_size": "8 Marla", "property_type": "Apartment"},
        )
        upsert_listing(
            zameen_id="920003",
            url="https://www.zameen.com/Property/test-920003-1-1.html",
            city="karachi",
            detail_data={
                "description": "Far detail",
                "latitude": 24.7900,
                "longitude": 67.1000,
                "location_source": "listing_exact",
            },
        )

        res = client.get("/api/nearby-search?city=karachi&lat=24.82&lng=67.03&radius_km=5")

        assert res.status_code == 200
        data = res.json()
        assert data["source"] == "local"
        assert data["mode"] == "nearby"
        assert data["radius_km"] == 5
        assert data["focus_center"] == {"lat": 24.82, "lng": 67.03}
        assert data["total"] == 1
        assert data["results"][0]["title"] == "Near me exact"
        assert data["results"][0]["distance_source"] == "listing_exact"
        assert data["results"][0]["is_distance_approximate"] is False
        assert data["results"][0]["distance_km"] < 1

    def test_nearby_search_rejects_unsupported_city(self, client):
        res = client.get("/api/nearby-search?city=lahore&lat=31.52&lng=74.35&radius_km=5")

        assert res.status_code == 400
        assert "Karachi" in res.json()["detail"]

    def test_nearby_search_rejects_invalid_radius(self, client):
        res = client.get("/api/nearby-search?city=karachi&lat=24.82&lng=67.03&radius_km=25")

        assert res.status_code == 400
        assert "between 1 and 20 km" in res.json()["detail"]

    def test_nearby_search_rejects_invalid_latitude(self, client):
        res = client.get("/api/nearby-search?city=karachi&lat=124.82&lng=67.03&radius_km=5")

        assert res.status_code == 400
        assert "Latitude" in res.json()["detail"]

    def test_nearby_search_rejects_inverted_price_range(self, client):
        res = client.get("/api/nearby-search?city=karachi&lat=24.82&lng=67.03&radius_km=5&price_min=100000&price_max=50000")

        assert res.status_code == 400
        assert "price_min" in res.json()["detail"]

    def test_nearby_search_enriches_sparse_exact_results(self, client, monkeypatch):
        upsert_listing(
            zameen_id="920010",
            url="https://www.zameen.com/Property/test-920010-1-1.html",
            city="karachi",
            area_name="Clifton",
            area_slug="Karachi_Clifton",
            lat=24.8204,
            lng=67.0304,
            card_data={"title": "Upgradeable nearby", "price": 84000, "bedrooms": 2, "bathrooms": 2, "area_size": "5 Marla", "property_type": "Apartment"},
        )

        async def fake_fetch_listing_detail(url):
            assert "test-920010" in url
            return {
                "description": "Fresh exact detail",
                "latitude": 24.8208,
                "longitude": 67.0309,
                "location_source": "listing_exact",
                "has_exact_geography": True,
            }

        monkeypatch.setattr("app.routes.fetch_listing_detail", fake_fetch_listing_detail)

        res = client.get("/api/nearby-search?city=karachi&lat=24.82&lng=67.03&radius_km=5")

        assert res.status_code == 200
        data = res.json()
        assert data["total"] == 1
        assert data["results"][0]["title"] == "Upgradeable nearby"
        listing = get_listing_by_zameen_id("920010")
        assert listing["location_source"] == "listing_exact"
        assert listing["latitude"] == pytest.approx(24.8208)
        assert listing["longitude"] == pytest.approx(67.0309)


class TestFrontendServing:
    def test_serves_html(self, client):
        res = client.get("/")
        assert res.status_code == 200
        assert "ZameenRentals" in res.text
        assert "<!DOCTYPE html>" in res.text
