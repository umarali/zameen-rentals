"""Furnishing has three states: furnished (True), unfurnished (False), and no
preference (None/absent). False is a filter, not the absence of one.

Regression for the 2026-10-09 release audit: after "furnished apartment in
Gulberg Lahore", searching "unfurnished apartment in Gulberg Lahore" still
returned furnished-only results.

A listing counts as furnished or unfurnished only on evidence. Listings that
say nothing, or contradict themselves, match neither and stay under "Any".
"""
import asyncio
import json
import sqlite3
from unittest.mock import AsyncMock, Mock
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app import app, parsing
from app.db_listings import furnishing_sql, furnishing_status, search_listings, upsert_listing
from app.parsing import parse_natural_query


# zameen_id: (title, detail data, expected status)
LISTINGS = {
    "930001": ("Fully Furnished Apartment For Rent", {}, True),
    "930002": ("2 Bed Apartment", {"amenities": ["Lift", "Furnished"]}, True),
    "930003": ("Semi Furnished Apartment", {}, True),
    "930004": ("Very Well Maintained (Unfurnished) Flat For Rent", {}, False),
    "930005": ("Non Furnished Apartment For Rent", {}, False),
    "930006": ("Apartment, Not Furnished", {}, False),
    "930007": ("3 Bed Apartment", {"details": {"Furnished": "No"}}, False),
    "930008": ("Brand New Apartment For Rent", {}, None),
    "930009": ("Apartment", {"details": {"Furnished": None}}, None),
    "930010": ("Furnished And Unfurnished Units Available", {}, None),
    "930011": ("Non-Furnished Apartment", {"amenities": ["Furnished"]}, None),
}
BY_STATUS = {status: {title for title, _, s in LISTINGS.values() if s is status}
             for status in (True, False, None)}
FURNISHED, UNFURNISHED = BY_STATUS[True], BY_STATUS[False]
ALL = {title for title, _, _ in LISTINGS.values()}

# The variants the query parser reads as "unfurnished".
NEGATIVE_QUERIES = [
    "unfurnished apartment in Gulberg Lahore", "un-furnished flat", "un furnished flat",
    "non furnished house", "non-furnished house", "not furnished flat", "flat without furniture",
    "no furniture flat", "bina furniture flat", "furniture ke baghair ghar", "ان فرنشڈ فلیٹ",
    "غیر فرنشڈ فلیٹ", "فرنیچر کے بغیر گھر",
]


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def _fresh_rate_limits():
    # These tests call /api/search more often than its per-minute limit allows
    # when the whole suite shares one limiter.
    app.state.limiter.reset()
    yield


def _seed(exact=False):
    for zid, (title, detail, _) in LISTINGS.items():
        url = f"https://www.zameen.com/Property/t-{zid}-1-1.html"
        upsert_listing(
            zameen_id=zid, url=url, city="lahore", area_name="Gulberg", area_slug="Lahore_Gulberg",
            lat=31.5204, lng=74.3487,
            card_data={"title": title, "price": 90000, "bedrooms": 2, "bathrooms": 2,
                       "area_size": "1100 sqft", "property_type": "Apartment"},
        )
        if exact:
            detail = {**detail, "latitude": 31.5210, "longitude": 74.3490,
                      "location_source": "listing_exact"}
        if detail:
            upsert_listing(zameen_id=zid, url=url, city="lahore", detail_data=detail)


def _titles(data):
    return {r["title"] for r in data["results"]}


class TestListingEvidence:
    @pytest.mark.parametrize("zid", LISTINGS)
    def test_status(self, zid):
        title, detail, expected = LISTINGS[zid]
        amenities = json.dumps(detail["amenities"]) if "amenities" in detail else None
        details = json.dumps(detail["details"]) if "details" in detail else None
        assert furnishing_status(title, amenities, details) is expected

    @pytest.mark.parametrize("text", NEGATIVE_QUERIES)
    def test_every_parser_negative_is_negative_listing_evidence(self, text):
        assert furnishing_status(text) is False

    def test_sql_matches_python_for_reviewer_reproduction(self):
        titles = ["Apartment for rent", "Unfurnished apartment", "Not furnished apartment", "Furnished apartment"]
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE l (title TEXT, amenities_json TEXT, details_json TEXT)")
        conn.executemany("INSERT INTO l (title) VALUES (?)", [(t,) for t in titles])
        for value in (True, False):
            got = [r[0] for r in conn.execute(f"SELECT title FROM l WHERE {furnishing_sql(value, 'l')}")]
            assert got == [t for t in titles if furnishing_status(t) is value]
        assert furnishing_status("Not furnished apartment") is False
        assert furnishing_status("Apartment for rent") is None


class TestLocalSearch:
    def test_states_need_evidence(self):
        _seed()
        assert _titles(search_listings(city="lahore", furnished=True)) == FURNISHED
        assert _titles(search_listings(city="lahore", furnished=False)) == UNFURNISHED
        assert _titles(search_listings(city="lahore", furnished=None)) == ALL

    def test_api_furnished_then_unfurnished(self, client):
        _seed()
        base = "/api/search?city=lahore&area=Gulberg&property_type=apartment"
        assert _titles(client.get(base + "&furnished=true").json()) == FURNISHED
        assert _titles(client.get(base + "&furnished=false").json()) == UNFURNISHED
        assert _titles(client.get(base).json()) == ALL

    def test_unfurnished_never_falls_back_to_unfiltered_live_results(self, client, monkeypatch):
        async def unexpected_scrape(**kwargs):
            pytest.fail("Live scraping cannot honor an unfurnished filter")

        monkeypatch.setattr("app.routes.search_zameen", unexpected_scrape)
        res = client.get("/api/search?city=lahore&furnished=false")
        assert res.status_code == 200
        assert res.json()["total"] == 0

    def test_map_search_enforces_unfurnished(self, client):
        _seed()
        res = client.get("/api/map-search?city=lahore&areas=Gulberg&furnished=false")
        assert res.status_code == 200
        data = res.json()
        assert _titles(data) == UNFURNISHED
        assert data["area_totals"] == {"Gulberg": len(UNFURNISHED)}

    def test_map_search_exact_bounds_enforces_unfurnished(self, client):
        _seed(exact=True)
        res = client.get("/api/map-search?city=lahore&furnished=false"
                         "&south=31.51&west=74.34&north=31.53&east=74.36")
        assert res.json()["scope"] == "exact_bounds"
        assert _titles(res.json()) == UNFURNISHED

    def test_nearby_search_enforces_unfurnished(self, client, monkeypatch):
        async def no_detail(url):
            return None

        monkeypatch.setattr("app.routes.fetch_listing_detail", no_detail)
        _seed(exact=True)
        nearby = "/api/nearby-search?city=lahore&lat=31.521&lng=74.349&radius_km=5"
        assert _titles(client.get(nearby + "&furnished=false").json()) == UNFURNISHED
        assert _titles(client.get(nearby + "&furnished=true").json()) == FURNISHED

    def test_search_history_records_unfurnished(self, client):
        from app.database import _get_conn
        _seed()
        client.get("/api/search?city=lahore&furnished=false")
        row = _get_conn().execute("SELECT furnished FROM search_history ORDER BY id DESC LIMIT 1").fetchone()
        assert row["furnished"] == 0


class TestRegexParser:
    @pytest.mark.parametrize("query", NEGATIVE_QUERIES)
    def test_explicit_unfurnished_is_false(self, query):
        assert parse_natural_query(query, city="lahore")["furnished"] is False

    @pytest.mark.parametrize("query", ["furnished apartment in Gulberg Lahore", "semi-furnished flat", "فرنشڈ فلیٹ"])
    def test_furnished_is_true(self, query):
        assert parse_natural_query(query, city="lahore")["furnished"] is True

    def test_no_mention_is_absent(self):
        assert "furnished" not in parse_natural_query("2 bed flat in Gulberg", city="lahore")

    def test_unfurnished_keeps_the_area(self):
        result = parse_natural_query("unfurnished apartment in Gulberg Lahore", city="lahore")
        assert result["area"] == "Gulberg"
        assert result["property_type"] == "apartment"


class TestParseQueryRoute:
    def test_sequential_queries_return_true_then_false(self, client, monkeypatch):
        async def regex_only(q, city="lahore"):
            return parse_natural_query(q, city=city)

        monkeypatch.setattr("app.routes.parse_query_with_claude", regex_only)
        first = client.get("/api/parse-query?city=lahore&q=furnished apartment in Gulberg Lahore").json()
        second = client.get("/api/parse-query?city=lahore&q=unfurnished apartment in Gulberg Lahore").json()
        assert first["filters"]["furnished"] is True
        assert second["filters"]["furnished"] is False
        assert not second["filters"].get("area_approximate")


@pytest.fixture
def provider(monkeypatch):
    client = Mock()
    create = AsyncMock()

    async def create_with_completion(**kwargs):
        return await create(**kwargs), SimpleNamespace(usage=None)

    client.messages.create_with_completion = create_with_completion
    monkeypatch.setattr(parsing, "_get_instructor_client", lambda: client)
    monkeypatch.setattr(parsing, "_nl_cache_get", lambda key: None)
    monkeypatch.setattr(parsing, "_nl_cache_set", Mock())
    return create


class TestClaudeFurnishing:
    def test_model_false_for_unfurnished_is_kept(self, provider):
        provider.return_value = parsing.RentalFilters(area="Gulberg", property_type="apartment", furnished=False)
        result = asyncio.run(parsing.parse_query_with_claude("unfurnished apartment in Gulberg Lahore", city="lahore"))
        assert result["furnished"] is False
        assert result["parser"] == "ai"

    def test_explicit_unfurnished_overrides_model_true(self, provider):
        provider.return_value = parsing.RentalFilters(area="Gulberg", furnished=True)
        result = asyncio.run(parsing.parse_query_with_claude("unfurnished flat in Gulberg", city="lahore"))
        assert result["furnished"] is False

    def test_explicit_unfurnished_fills_a_missing_model_value(self, provider):
        provider.return_value = parsing.RentalFilters(area="Gulberg")
        result = asyncio.run(parsing.parse_query_with_claude("unfurnished flat in Gulberg", city="lahore"))
        assert result["furnished"] is False

    @pytest.mark.parametrize("value", [True, False])
    def test_furnishing_the_query_never_mentions_is_dropped(self, provider, value):
        provider.return_value = parsing.RentalFilters(area="Gulberg", bedrooms=2, furnished=value)
        result = asyncio.run(parsing.parse_query_with_claude("2 bed flat in Gulberg", city="lahore"))
        assert "furnished" not in result

    def test_model_false_for_other_negations_is_kept(self, provider):
        provider.return_value = parsing.RentalFilters(area="Gulberg", furnished=False)
        result = asyncio.run(parsing.parse_query_with_claude("flat in Gulberg, furniture nahi chahiye", city="lahore"))
        assert result["furnished"] is False
