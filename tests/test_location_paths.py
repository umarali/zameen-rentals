"""Location paths: listings filed by Zameen's location hierarchy, not by crawl order."""
import json
from pathlib import Path

import pytest

import app.personalization as pers
from app.database import _get_conn
from app.data import area_names_for_location_id, canonical_area_name
from app.db_listings import count_listings_by_area, search_listings, upsert_listing

FIXTURE = Path(__file__).parent / "fixtures" / "search_state_dha_phase6.json"
CLIENT_ID = "11111111-2222-4333-8444-555555555555"


def _real_hits():
    return json.loads(FIXTURE.read_text())


def _path(*ids):
    """A stored-shape location path: city level and below."""
    names = {2: "Karachi", 213: "DHA Defence", 1483: "DHA Phase 6",
             6674: "Bukhari Commercial Area", 5: "Clifton"}
    return [{"location_id": i, "level": 2 + n, "name": names[i], "name_l1": None}
            for n, i in enumerate(ids)]


def _upsert(zid, crawl_area, path=None, **card):
    return upsert_listing(
        zameen_id=zid, url=f"https://www.zameen.com/Property/t-{zid}-1-1.html",
        city="karachi", area_name=crawl_area, area_slug=f"Karachi_{crawl_area}",
        card_data={"title": f"Flat {zid}", "price": 90000, "bedrooms": 2,
                   "bathrooms": 2, "area_size": "1000 sqft", **card},
        search_state={"location_path": path} if path else None,
    )


class TestScraperLocationPath:
    def test_extracts_city_and_lower_levels_from_real_hit(self):
        from app.scraper import enrich_from_search_state
        hit = _real_hits()[0]
        state = {"algolia": {"content": {"hits": [hit]}}}
        html = f"<script>window.state = {json.dumps(state)};</script>"
        listings = [{"url": f"https://www.zameen.com/Property/x-{hit['externalID']}-1-1.html"}]

        assert enrich_from_search_state(html, listings) == 1

        path = listings[0]["search_state"]["location_path"]
        assert [(p["location_id"], p["level"]) for p in path] == [(2, 2), (213, 3), (1483, 4)]
        assert path[-1]["name"] == "DHA Phase 6"
        assert path[-1]["name_l1"]

    def test_missing_or_malformed_location_gives_empty_path(self):
        from app.scraper import _state_location_path
        assert _state_location_path({}) == []
        assert _state_location_path({"location": [{"name": "x"}, "junk"]}) == []


class TestAreaIndex:
    def test_duplicate_lahore_ids_resolve_to_every_name(self):
        names = area_names_for_location_id("lahore", 1454)
        assert set(names) == {"Defence  DHA  Phase 3", "Defence (DHA) Phase 3"}

    def test_canonical_name_prefers_clean_spelling(self):
        assert canonical_area_name("lahore", 1454) == "Defence (DHA) Phase 3"
        assert canonical_area_name("lahore", 9) == "DHA Defence"
        assert canonical_area_name("karachi", 999999999) is None


class TestPathSearch:
    def test_parent_crawl_does_not_steal_child_listing(self):
        _upsert("700001", "DHA Phase 6", _path(2, 213, 1483))
        _upsert("700001", "DHA Defence", _path(2, 213, 1483))

        assert search_listings(city="karachi", area="DHA Phase 6")["total"] == 1
        assert search_listings(city="karachi", area="DHA Defence")["total"] == 1
        assert count_listings_by_area(city="karachi") == {"DHA Phase 6": 1}

    def test_area_name_is_deepest_known_level(self):
        # Bukhari Commercial Area isn't in areas.json, so Phase 6 is the deepest known area.
        _upsert("700002", "DHA Defence", _path(2, 213, 1483, 6674))
        row = _get_conn().execute(
            "SELECT area_name FROM listings WHERE zameen_id = '700002'").fetchone()
        assert row["area_name"] == "DHA Phase 6"

    def test_area_names_filter_uses_paths(self):
        _upsert("700003", "DHA Defence", _path(2, 213, 1483))
        result = search_listings(city="karachi", area_names=["DHA Phase 6", "Clifton"])
        assert result["total"] == 1

    def test_sibling_area_does_not_match(self):
        _upsert("700004", "DHA Defence", _path(2, 213, 1483))
        assert search_listings(city="karachi", area="Clifton")["total"] == 0

    def test_listing_without_path_falls_back_to_area_name(self):
        _upsert("700005", "Clifton")
        assert search_listings(city="karachi", area="Clifton")["total"] == 1

    def test_path_replaces_stale_rows(self):
        _upsert("700006", "Clifton", _path(2, 5))
        _upsert("700006", "DHA Phase 6", _path(2, 213, 1483))
        assert search_listings(city="karachi", area="Clifton")["total"] == 0
        assert search_listings(city="karachi", area="DHA Phase 6")["total"] == 1

    def test_locations_table_keeps_names(self):
        _upsert("700007", "DHA Phase 6", _path(2, 213, 1483))
        row = _get_conn().execute(
            "SELECT name, level, city FROM locations WHERE location_id = 1483").fetchone()
        assert (row["name"], row["level"], row["city"]) == ("DHA Phase 6", 4, "karachi")


class TestPathAlerts:
    @pytest.fixture(autouse=True)
    def _schema(self, fresh_db):
        pers.init_personalization_schema()

    def test_insert_hook_sees_path_before_matching(self):
        pers.create_alert(CLIENT_ID, label=None,
                          filters={"city": "karachi", "area": "DHA Phase 6"})
        # The parent crawl finds it first; only the path says it's in Phase 6.
        _upsert("700010", "DHA Defence", _path(2, 213, 1483))
        assert [m["zameen_id"] for m in pers.list_matches(CLIENT_ID)] == ["700010"]

    def test_pure_matcher_accepts_location_ids(self):
        row = {"city": "karachi", "area_name": "DHA Defence", "location_ids": [2, 213, 1483]}
        assert pers.listing_matches_alert(row, {"city": "karachi", "area": "DHA Phase 6"})
        assert not pers.listing_matches_alert(row, {"city": "karachi", "area": "Clifton"})
