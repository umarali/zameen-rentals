"""Integrity of tests/fixtures/nl_eval_queries.jsonl, the hand-labelled NL eval set.

The set is scored by tools/eval_nl_parser.py; this only checks the labels are
well-formed and name real areas, so a typo can't silently make a query unpassable.
"""
import json
from pathlib import Path

import pytest

from app.data import CITIES, PROPERTY_TYPES, get_areas

FIXTURE = Path(__file__).parent / "fixtures" / "nl_eval_queries.jsonl"
ROWS = [json.loads(line) for line in FIXTURE.read_text().splitlines() if line.strip()]
FIELDS = {"area", "areas", "property_type", "bedrooms", "bedrooms_max", "price_min", "price_max",
          "size_marla_min", "size_marla_max", "furnished", "sort"}


def test_set_is_big_and_covers_every_city_and_language():
    assert len(ROWS) >= 150
    assert {r["city"] for r in ROWS} == set(CITIES)
    assert {"en", "roman", "urdu"} <= {r["lang"] for r in ROWS}
    assert len({r["id"] for r in ROWS}) == len(ROWS)


@pytest.mark.parametrize("row", ROWS, ids=[r["id"] for r in ROWS])
def test_row_is_well_formed(row):
    assert row["city"] in CITIES and row["q"].strip()
    assert set(row["expect"]) <= FIELDS
    assert row["expect"] or row.get("area_any"), "nothing to score"
    areas = get_areas(row["city"])
    named = [row["expect"].get("area")] + row["expect"].get("areas", []) + row.get("area_any", [])
    for name in filter(None, named):
        assert name in areas, f"{name!r} is not a {row['city']} area"
    if row["expect"].get("property_type") is not None:
        assert row["expect"]["property_type"] in PROPERTY_TYPES
    assert row["expect"].get("sort") in (None, "price_low", "price_high", "newest")
