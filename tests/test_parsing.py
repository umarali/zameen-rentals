"""Parser-level regressions for Roman Urdu rental queries."""
from app.parsing import parse_natural_query


class TestRomanUrduParsing:
    def test_upper_portion_query_with_block_and_price_cap(self):
        result = parse_natural_query(
            "gulshan e iqbal block 13 main ooper ka portion 150k tak ka portion",
            city="karachi",
        )

        assert result["area"] == "Gulshan-e-Iqbal"
        assert result["property_type"] == "upper_portion"
        assert result["price_max"] == 150000

    def test_lower_portion_query_with_price_range(self):
        result = parse_natural_query(
            "dha phase 8 main 250 se 300k tak ka neechay ka portion",
            city="karachi",
        )

        assert result["area"] == "DHA Phase 8"
        assert result["property_type"] == "lower_portion"
        assert result["price_min"] == 250000
        assert result["price_max"] == 300000

    def test_existing_flat_query_still_parses_the_same(self):
        result = parse_natural_query(
            "2 bed flat DHA under 50k",
            city="karachi",
        )

        assert result["bedrooms"] == 2
        assert result["property_type"] == "apartment"
        assert result["price_max"] == 50000
        assert result["area"] == "DHA Defence"
