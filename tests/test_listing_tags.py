"""Jev listing tags: what gets tagged, what search shows, and confidence gating."""
import pytest
from fastapi.testclient import TestClient

from app import app
from app.database import _get_conn
from app.db_listings import search_listings, upsert_listing
from app.decisions import Answer, Decision, DecisionError
from app.listing_tags import (
    QUESTIONS, listing_state, listings_needing_tags, public_tags, save_tags, tag_listings,
)


def _listing(zameen_id, *, title="10 Marla Upper Portion", description=None, price=65000,
             city="lahore", amenities=None):
    url = f"https://www.zameen.com/Property/test-{zameen_id}-1-1.html"
    upsert_listing(zameen_id=zameen_id, url=url, city=city, area_name="Johar Town",
                   card_data={"title": title, "price": price, "bedrooms": 3,
                              "bathrooms": 2, "area_size": "10 Marla",
                              "property_type": "Upper Portion"})
    if description or amenities:
        upsert_listing(zameen_id=zameen_id, url=url, city=city,
                       detail_data={"description": description, "amenities": amenities or []})
    return _row(zameen_id)


def _row(zameen_id):
    return _get_conn().execute("SELECT * FROM listings WHERE zameen_id = ?", (zameen_id,)).fetchone()


def _decision(tenant="bachelor", tenant_conf=0.9, backup=0.95, separate=0.1, new=0.5):
    return Decision(model="jev-1.13.0", input_tokens=150, answers={
        "tenant_fit": Answer("choice", tenant, tenant_conf),
        "backup_power": Answer("noul", backup, abs(backup - 0.5) * 2),
        "separate_entrance": Answer("noul", separate, abs(separate - 0.5) * 2),
        "newly_built": Answer("noul", new, abs(new - 0.5) * 2),
    })


class FakeProvider:
    def __init__(self, decision=None, error=None):
        self.decision = decision or _decision()
        self.error = error
        self.states = []

    async def decide(self, state, questions):
        assert questions is QUESTIONS
        self.states.append(state)
        if self.error:
            raise self.error
        return self.decision


class TestListingState:
    def test_includes_facts_title_description_and_amenities(self):
        row = _listing("700001", description="Only for   bachelors.\nSolar installed.",
                       amenities=["Electricity Backup", "Parking"])
        state = listing_state(row)
        assert "Rental listing in Lahore, Johar Town." in state
        assert "Rent: PKR 65,000/month" in state
        assert "Title: 10 Marla Upper Portion" in state
        assert "Description: Only for bachelors. Solar installed." in state
        assert "Amenities: Electricity Backup, Parking" in state

    def test_truncates_long_descriptions(self):
        row = _listing("700002", description="word " * 1000)
        desc_line = [l for l in listing_state(row).splitlines() if l.startswith("Description:")][0]
        assert len(desc_line) <= len("Description: ") + 800


class TestListingsNeedingTags:
    def test_skips_title_only_listings_by_default(self):
        _listing("700010")
        _listing("700011", description="Family only")
        assert [r["zameen_id"] for r in listings_needing_tags(limit=10)] == ["700011"]
        assert len(listings_needing_tags(limit=10, include_title_only=True)) == 2

    def test_tagged_listing_is_rescored_only_after_a_change(self):
        row = _listing("700012", description="Family only")
        save_tags(row, _decision())
        assert listings_needing_tags(limit=10) == []
        _listing("700012", description="Family only", price=70000)  # content_hash changes
        assert [r["zameen_id"] for r in listings_needing_tags(limit=10)] == ["700012"]

    def test_title_only_tag_is_redone_when_description_arrives(self):
        row = _listing("700013")
        save_tags(row, _decision())
        assert listings_needing_tags(limit=10, include_title_only=True) == []
        _listing("700013", description="Bachelors welcome")
        assert [r["zameen_id"] for r in listings_needing_tags(limit=10)] == ["700013"]


class TestPublicTags:
    def _tag_row(self, decision, zameen_id="700020"):
        save_tags(_listing(zameen_id, description="x"), decision)
        return _get_conn().execute("SELECT * FROM listing_tags WHERE zameen_id = ?", (zameen_id,)).fetchone()

    def test_confident_answers_are_shown(self):
        tags = public_tags(self._tag_row(_decision()))
        assert tags == {"tenant_fit": "bachelor", "backup_power": True,
                        "separate_entrance": None, "newly_built": None}

    def test_unsure_tenant_and_unclear_are_hidden(self):
        assert public_tags(self._tag_row(_decision(tenant_conf=0.5)))["tenant_fit"] is None
        assert public_tags(self._tag_row(_decision(tenant="unclear"), "700021"))["tenant_fit"] is None

    def test_low_probability_means_unknown_not_no(self):
        assert public_tags(self._tag_row(_decision(backup=0.02)))["backup_power"] is None


class TestTagListings:
    @pytest.mark.asyncio
    async def test_tags_and_reports_usage(self):
        _listing("700030", description="Bachelors welcome, solar")
        stats = await tag_listings(FakeProvider(), limit=10)
        assert stats["tagged"] == 1 and stats["input_tokens"] == 150
        assert listings_needing_tags(limit=10) == []

    @pytest.mark.asyncio
    async def test_stops_on_non_retryable_error(self):
        for i in range(10):
            _listing(f"70004{i}", description="x")
        provider = FakeProvider(error=DecisionError("HTTP 401", retryable=False))
        stats = await tag_listings(provider, limit=10, concurrency=1)
        assert stats["aborted"] and stats["tagged"] == 0
        assert len(provider.states) == 1


class TestSearchFilters:
    def _seed(self):
        save_tags(_listing("700050", description="Bachelors"), _decision("bachelor"))
        save_tags(_listing("700051", description="Family"), _decision("family", backup=0.1))
        save_tags(_listing("700052", description="Anyone"), _decision("either", separate=0.9))
        save_tags(_listing("700053", description="Unsure"), _decision("bachelor", tenant_conf=0.4))
        _listing("700054", description="Not tagged yet")

    def _ids(self, **kwargs):
        return sorted(r["zameen_id"] for r in search_listings(city="lahore", **kwargs)["results"])

    def test_tenant_filter_includes_either_and_skips_unsure(self):
        self._seed()
        assert self._ids(tenant="bachelor") == ["700050", "700052"]
        assert self._ids(tenant="family") == ["700051", "700052"]

    def test_feature_filters(self):
        self._seed()
        assert self._ids(backup_power=True) == ["700050", "700052", "700053"]
        assert self._ids(separate_entrance=True) == ["700052"]

    def test_no_filter_returns_everything_with_tags_attached(self):
        self._seed()
        results = {r["zameen_id"]: r for r in search_listings(city="lahore")["results"]}
        assert len(results) == 5
        assert results["700050"]["tags"]["tenant_fit"] == "bachelor"
        assert "tags" not in results["700054"]

    def test_api_param_and_no_live_fallback(self):
        self._seed()
        client = TestClient(app)
        res = client.get("/api/search", params={"city": "lahore", "tenant": "bachelor"})
        assert res.status_code == 200
        assert sorted(r["zameen_id"] for r in res.json()["results"]) == ["700050", "700052"]
        # Zameen can't filter on tags, so an empty tag search stays local.
        res = client.get("/api/search", params={"city": "karachi", "backup_power": "true"})
        assert res.json()["source"] == "local" and res.json()["total"] == 0
        assert client.get("/api/search", params={"tenant": "students"}).status_code == 422
