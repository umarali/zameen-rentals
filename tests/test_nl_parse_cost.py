"""Claude parse path: model setting, candidate areas, prompt caching, spend controls."""
import asyncio

import pytest

import app.parsing as parsing
from app.data import get_areas


class _Filters:
    def __init__(self, data):
        self._data = data

    def model_dump(self, exclude_none=True):
        return dict(self._data)


class _Usage:
    input_tokens, output_tokens = 900, 60
    cache_creation_input_tokens, cache_read_input_tokens = 0, 1500


class _Completion:
    usage = _Usage()


class _Client:
    def __init__(self, data):
        self.messages = self
        self.data = data
        self.calls = []

    def create_with_completion(self, **kwargs):
        self.calls.append(kwargs)
        return _Filters(self.data), _Completion()


@pytest.fixture
def claude(monkeypatch):
    def install(data):
        client = _Client(data)
        monkeypatch.setattr(parsing, "_get_instructor_client", lambda: client)
        return client
    return install


def _parse(query, city="karachi"):
    return asyncio.run(parsing.parse_query_with_claude(query, city=city))


class TestCandidateAreas:
    def test_exact_mention_comes_first(self):
        cands = parsing._candidate_areas("dha phase 6 flat", "karachi")
        assert cands[0] == "DHA Phase 6"

    def test_typo_still_reaches_the_right_area(self):
        assert "Johar Town" in parsing._candidate_areas("johr town mein 2 kamray ka flat", "lahore")

    def test_landmark_area_is_included(self):
        landmark_area = parsing.resolve_landmark("flat near lums", city="lahore")
        if landmark_area:
            assert landmark_area in parsing._candidate_areas("flat near lums", "lahore")

    def test_no_place_named_sends_no_areas(self):
        assert parsing._candidate_areas("2 bed flat under 50k", "karachi") == []

    def test_candidates_are_a_small_fraction_of_the_city(self):
        for city, q in [("karachi", "gulshan 2 bed flat"), ("lahore", "bahria town 10 marla house"),
                        ("islamabad", "f-8 mein do bed flat")]:
            cands = parsing._candidate_areas(q, city)
            assert 0 < len(cands) <= parsing.PARSE_CANDIDATE_LIMIT
            assert len(cands) < len(get_areas(city)) / 5
            assert all(c in get_areas(city) for c in cands)


class TestPromptLayout:
    def test_static_rules_are_cached_and_identical_across_queries(self):
        a = parsing._nlq_system("dha phase 6 flat", "karachi")
        b = parsing._nlq_system("johar town house", "lahore")
        assert a[0] == b[0]
        assert a[0]["cache_control"] == {"type": "ephemeral"}
        assert "cache_control" not in a[1]
        assert "CURRENT CITY: Karachi" in a[1]["text"] and "DHA Phase 6" in a[1]["text"]

    def test_call_uses_configured_model_and_blocks(self, claude):
        client = claude({"area": "Clifton", "property_type": "apartment"})
        result = _parse("flat in clifton")
        assert result["area"] == "Clifton" and result["parser"] == "ai"
        call = client.calls[0]
        assert call["model"] == parsing.PARSE_MODEL == "claude-haiku-5-5"
        assert call["system"][0]["cache_control"] == {"type": "ephemeral"}


class TestSpendControls:
    def test_usage_and_cost_are_recorded(self, claude):
        claude({"area": "Clifton"})
        _parse("flat in clifton")
        # 900 in at $0.10, 1500 cache reads at $0.01, 60 out at $0.50 per million.
        assert parsing.last_call["cost_usd"] == pytest.approx(0.000135)
        assert parsing.nl_spend_today() == pytest.approx(0.000135)

    def test_repeat_query_is_served_from_cache(self, claude):
        client = claude({"area": "Clifton"})
        first = _parse("flat in clifton")
        second = _parse("Flat  in   CLIFTON")
        assert second == first
        assert len(client.calls) == 1
        assert parsing.last_call.get("cached") is True

    def test_budget_exhausted_falls_back_to_regex_without_calling(self, claude, monkeypatch):
        client = claude({"area": "Clifton"})
        monkeypatch.setattr(parsing, "NL_DAILY_BUDGET_USD", 0.0001)
        _parse("flat in clifton")  # spends 0.000135, over the cap
        result = _parse("house in dha phase 6")
        assert result.get("parser", "regex") == "regex"
        assert len(client.calls) == 1
        assert parsing.last_call.get("budget_exhausted") is True

    def test_api_failure_falls_back_to_regex(self, monkeypatch):
        class Broken:
            messages = None
            def __init__(self):
                self.messages = self
            def create_with_completion(self, **kwargs):
                raise RuntimeError("credit balance is too low")
        monkeypatch.setattr(parsing, "_get_instructor_client", lambda: Broken())
        result = _parse("2 bed flat in clifton")
        assert result["area"] == "Clifton" and result.get("parser", "regex") == "regex"
        assert "credit balance" in parsing.last_call["error"]


class TestAreaNumberBedrooms:
    def test_number_in_area_name_is_not_bedrooms(self, claude):
        claude({"area": "Cantt", "property_type": "apartment", "bedrooms": 5})
        assert "bedrooms" not in _parse("askari 5 flat")

    def test_number_followed_by_bed_is_bedrooms(self, claude):
        claude({"area": "Cantt", "bedrooms": 5})
        assert _parse("askari 5 bed flat")["bedrooms"] == 5

    def test_separate_bed_count_survives_a_numbered_area(self, claude):
        claude({"area": "DHA Phase 6", "bedrooms": 2})
        assert _parse("dha phase 6 mein 2 bed flat")["bedrooms"] == 2

    def test_studio_keeps_one_bedroom(self, claude):
        claude({"area": "Clifton", "bedrooms": 1})
        assert _parse("studio in clifton")["bedrooms"] == 1


class TestUnknownPlaces:
    def test_place_that_is_not_an_area_is_dropped_not_kept_as_text(self, claude):
        claude({"area": "Kemari", "property_type": "room"})
        result = _parse("room for rent in kemari")
        assert "area" not in result or result["area"] in get_areas("karachi")

    def test_unknown_place_falls_back_to_landmark_area(self, claude):
        claude({"area": "NIPA", "property_type": "room"})
        result = _parse("sasta kamra near nipa")
        landmark = parsing.resolve_landmark("sasta kamra near nipa", city="karachi")
        assert result.get("area") == landmark


class TestRegexNumbers:
    def test_number_words_come_from_the_regex_parser(self, claude):
        claude({"area": "DHA Defence", "property_type": "house", "price_max": 300000})
        assert _parse("sade teen lakh tak bungalow dha")["price_max"] == 350000

    def test_square_yards_convert_to_marla(self, claude):
        claude({"area": "Clifton", "property_type": "house", "size_marla_min": 24.0})
        assert _parse("240 sq yd house in clifton")["size_marla_min"] == pytest.approx(9.6)

    def test_missed_bedrooms_are_filled(self, claude):
        claude({"area": "DHA Defence", "property_type": "apartment", "price_max": 50000})
        assert _parse("do bed flat dha mein pachas hazar tak")["bedrooms"] == 2

    def test_model_numbers_stay_when_regex_finds_none(self, claude):
        claude({"area": "Clifton", "price_max": 80000})
        assert _parse("flat in clifton, budget is about eighty thousand")["price_max"] == 80000
