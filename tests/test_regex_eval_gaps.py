"""Regex-parser gaps found by the 150-query eval set (tests/fixtures/nl_eval_queries.jsonl)."""
import pytest

from app.parsing import parse_natural_query
from app.routes import _build_parse_query_response


def _filters(q, city):
    return _build_parse_query_response(q, city, parse_natural_query(q, city))["filters"]


@pytest.mark.parametrize("q,ptype", [
    ("500 gaz bungalow dha phase 8", "house"),
    ("newest flats in north nazimabad", "apartment"),
    ("bangla chahiye dha mein", "house"),
])
def test_plural_and_synonym_property_types(q, ptype):
    assert parse_natural_query(q, "karachi")["property_type"] == ptype


@pytest.mark.parametrize("q,city,area", [
    ("جوہر ٹاؤن میں دو کمرے کا فلیٹ", "lahore", "Johar Town"),
    ("گلبرگ میں فلیٹ", "lahore", "Gulberg"),
    ("ڈی ایچ اے میں ایک کنال گھر", "lahore", "DHA Defence"),
    ("ایف ایٹ میں فلیٹ", "islamabad", "F 8"),
    ("ایف 8 میں فلیٹ", "islamabad", "F 8"),
    ("بحریہ ٹاؤن میں گھر", "islamabad", "Bahria Town"),
])
def test_urdu_area_names_for_every_city(q, city, area):
    f = _filters(q, city)
    assert f["area"] == area
    assert "area_approximate" not in f


def test_urdu_unicode_variants_match():
    # "ؤ" typed as one code point vs Zameen's "و" + combining hamza.
    assert parse_natural_query("بحریہ ٹاؤن میں گھر", "lahore")["area"] == "Bahria Town"
    assert parse_natural_query("بحریہ ٹاؤن میں گھر", "lahore")["area"] == "Bahria Town"


@pytest.mark.parametrize("q,marla", [
    ("بحریہ ٹاؤن میں پانچ مرلہ گھر", 5.0),
    ("ڈی ایچ اے میں ایک کنال گھر", 20.0),
    ("دس مرلے کا گھر", 10.0),
])
def test_urdu_size_units(q, marla):
    assert parse_natural_query(q, "lahore")["size_marla_min"] == marla


def test_more_specific_of_parent_and_child_wins():
    f = _filters("flat in north karachi buffer zone", "karachi")
    assert f["area"] == "North Buffer Zone"
    assert "area_approximate" not in f


@pytest.mark.parametrize("q,city,area", [
    ("sasta kamra near nipa", "karachi", "Gulshan-e-Iqbal"),
    ("house near emporium mall", "lahore", "Johar Town"),
    ("flat near liberty market", "lahore", "Gulberg"),
    ("room near ucp", "lahore", "Johar Town"),
])
def test_landmark_resolution_is_not_a_false_flag(q, city, area):
    f = _filters(q, city)
    assert f["area"] == area
    assert "area_approximate" not in f


def test_area_query_keeps_word_order_and_drops_filler():
    f = _filters("flat in clifftn blok 7 under 50k", "karachi")
    assert f["area_approximate"] is True
    assert f["area_query"] == "clifftn blok"
