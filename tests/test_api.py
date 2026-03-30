"""API endpoint tests using FastAPI TestClient."""
import pytest
from fastapi.testclient import TestClient
from app import app
from app.db_listings import upsert_listing


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


class TestFrontendServing:
    def test_serves_html(self, client):
        res = client.get("/")
        assert res.status_code == 200
        assert "ZameenRentals" in res.text
        assert "<!DOCTYPE html>" in res.text
