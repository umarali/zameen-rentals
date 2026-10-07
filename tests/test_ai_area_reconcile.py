"""The AI parser's area choice must agree with what the query actually says.

Production 2026-10-08: "askari 5 flat" came back from Claude as
"Gulistan-e-Jauhar Askari 4", a valid area name, so nothing re-checked it.
"""
from app.parsing import _reconcile_ai_area
from app.routes import _build_parse_query_response


def test_exact_mention_overrides_a_different_ai_choice():
    result = _reconcile_ai_area("askari 5 flat", {"area": "Gulistan-e-Jauhar Askari 4"}, "karachi")
    assert result["area"] == "Cantt Malir Cantonment"


def test_ai_choice_matching_a_mention_is_kept():
    result = _reconcile_ai_area("flat in clifton block 5", {"area": "Clifton Block 5"}, "karachi")
    assert result["area"] == "Clifton Block 5"


def test_ai_choice_without_any_exact_mention_is_kept():
    result = _reconcile_ai_area("flat near the beach", {"area": "Clifton"}, "karachi")
    assert result["area"] == "Clifton"


def test_ai_path_gets_multiple_areas():
    result = _reconcile_ai_area("DHA or Clifton flat", {"area": "Clifton"}, "karachi")
    assert result["areas"] == ["DHA Defence", "Clifton"]
    assert result["area"] == "DHA Defence"


def test_fallback_area_from_ai_is_flagged_end_to_end():
    result = _reconcile_ai_area("askari 5 flat", {"area": "Gulistan-e-Jauhar Askari 4"}, "karachi")
    f = _build_parse_query_response("askari 5 flat", "karachi", {**result, "parser": "ai"})["filters"]
    assert f["area"] == "Cantt Malir Cantonment"
    assert f["area_approximate"] is True


def test_area_number_the_user_never_typed_is_approximate():
    # Misspelt, so no exact mention: the safety net in the API must catch it.
    f = _build_parse_query_response("flat in askri 5", "karachi",
                                    {"area": "Gulistan-e-Jauhar Askari 4", "parser": "ai"})["filters"]
    assert f["area_approximate"] is True


def test_area_number_the_user_typed_is_not_flagged():
    f = _build_parse_query_response("dha phase 8 flat", "karachi",
                                    {"area": "DHA Phase 8", "parser": "ai"})["filters"]
    assert "area_approximate" not in f


# --- Full AI path with a mocked Claude response -----------------------------

import asyncio

import pytest

import app.parsing as parsing


class _FakeFilters:
    def __init__(self, data):
        self._data = data

    def model_dump(self, exclude_none=True):
        return dict(self._data)


class _FakeClient:
    def __init__(self, data):
        self.messages = self
        self._data = data

    def create(self, **kwargs):
        return _FakeFilters(self._data)


@pytest.fixture
def claude_returns(monkeypatch):
    def install(data):
        monkeypatch.setattr(parsing, "_get_instructor_client", lambda: _FakeClient(data))
        monkeypatch.setattr(parsing, "cache_get", lambda key: None)
        monkeypatch.setattr(parsing, "cache_set", lambda key, value: None)
    return install


def test_ai_path_askari_5(claude_returns):
    claude_returns({"area": "Gulistan-e-Jauhar Askari 4", "property_type": "apartment"})
    result = asyncio.run(parsing.parse_query_with_claude("askari 5 flat", city="karachi"))
    assert result["area"] == "Cantt Malir Cantonment"
    f = _build_parse_query_response("askari 5 flat", "karachi", result)["filters"]
    assert f["area_approximate"] is True


def test_regex_path_askari_5():
    result = parsing.parse_natural_query("askari 5 flat", city="karachi")
    f = _build_parse_query_response("askari 5 flat", "karachi", result)["filters"]
    assert (f["area"], f["area_approximate"], f["area_query"]) == ("Cantt Malir Cantonment", True, "askari 5")


def test_ai_landmark_resolution_is_not_overridden(claude_returns):
    # No area is named literally, so Claude's landmark resolution stands.
    claude_returns({"area": "Saddar"})
    result = asyncio.run(parsing.parse_query_with_claude("flat near aga khan hospital", city="karachi"))
    assert result["area"] == "Saddar"


def test_ai_choice_among_several_mentions_is_kept(claude_returns):
    # "in dha near clifton": Claude correctly picks DHA, the second literal mention.
    claude_returns({"area": "DHA Defence"})
    result = asyncio.run(parsing.parse_query_with_claude("flat near clifton bridge in dha", city="karachi"))
    assert result["area"] == "DHA Defence"


def test_ai_resolution_of_a_roman_alias_is_kept(claude_returns):
    claude_returns({"area": "Gulshan-e-Iqbal"})
    result = asyncio.run(parsing.parse_query_with_claude("gulshan mein ghar", city="karachi"))
    assert result["area"] == "Gulshan-e-Iqbal"
