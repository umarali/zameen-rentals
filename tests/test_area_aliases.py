"""Every alias the parser can return must name a real area in that city's area file."""
import pytest

from app.data import (
    LANDMARKS, ROMAN_URDU_AREAS_BY_CITY, URDU_AREAS, _ENGLISH_TO_URDU, get_areas,
)
from app.parsing import parse_natural_query

CITIES = ("karachi", "lahore", "islamabad")


@pytest.mark.parametrize("city", CITIES)
def test_roman_urdu_alias_targets_exist(city):
    areas = get_areas(city)
    missing = {a: t for a, t in ROMAN_URDU_AREAS_BY_CITY[city].items() if t not in areas}
    assert missing == {}


def test_urdu_alias_targets_exist():
    areas = get_areas("karachi")
    assert {a: t for a, t in URDU_AREAS.items() if t not in areas} == {}


@pytest.mark.parametrize("city", CITIES)
def test_landmark_targets_exist(city):
    areas = get_areas(city)
    assert {a: t for a, t in LANDMARKS.get(city, {}).items() if t not in areas} == {}


@pytest.mark.parametrize("query,area", [
    ("fb area mein flat", "Federal B. Area"),
    ("فیڈرل بی ایریا میں فلیٹ", "Federal B. Area"),
    ("surjani town house", "Gadap Town Surjani Town"),
    ("saadi town portion", "Scheme 33 Saadi Town"),
    ("flat in shaheed e millat", "Shaheed Millat Road"),
    ("buffer zone ghar", "North Buffer Zone"),
])
def test_remapped_aliases_resolve(query, area):
    assert parse_natural_query(query, city="karachi")["area"] == area


def test_unknown_neighbourhood_is_not_returned_as_an_area():
    assert parse_natural_query("flat in kemari", city="karachi").get("area") != "Kemari"


def test_parent_fallback_aliases_do_not_relabel_the_parent():
    assert _ENGLISH_TO_URDU.get("DHA Defence") == "ڈی ایچ اے"
    assert _ENGLISH_TO_URDU.get("Cantt Malir Cantonment") != "عسکری 5"


@pytest.mark.parametrize("query,alias", [
    ("askari 5 flat", "askari 5"),
    ("عسکری 5 میں فلیٹ", "عسکری 5"),
    ("karsaz flat", "karsaz"),
])
def test_parent_fallback_alias_is_flagged_approximate(query, alias):
    from app.routes import _build_parse_query_response
    f = _build_parse_query_response(query, "karachi", parse_natural_query(query, "karachi"))["filters"]
    assert f["area_approximate"] is True
    assert f["area_query"] == alias


def test_suggestions_never_offer_the_city_or_weak_matches():
    from app.parsing import suggest_areas
    assert suggest_areas("kemari", city="karachi") == []
    assert "Johar Town" in suggest_areas("johr", city="lahore")


def test_full_area_name_containing_a_fallback_alias_is_exact():
    from app.routes import _build_parse_query_response
    q = "2 bed flat in navy housing scheme karsaz"
    f = _build_parse_query_response(q, "karachi", parse_natural_query(q, "karachi"))["filters"]
    assert f["area"] == "Navy Housing Scheme Karsaz"
    assert "area_approximate" not in f
