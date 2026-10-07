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

    def test_marla_size_parses_to_marla(self):
        result = parse_natural_query("5 marla house in DHA Lahore", city="lahore")
        assert result["size_marla_min"] == 5.0
        result_k = parse_natural_query("1 kanal house DHA", city="lahore")
        assert result_k["size_marla_min"] == 20.0

    def test_square_yard_and_gaz_convert_to_marla(self):
        # Karachi quotes square yards / gaz; 1 Marla = 25 Sq Yd.
        assert parse_natural_query("240 sq yd house in Clifton", city="karachi")["size_marla_min"] == 9.6
        assert parse_natural_query("120 gaz portion in Gulshan", city="karachi")["size_marla_min"] == 4.8
        assert parse_natural_query("500 gaz bungalow DHA", city="karachi")["size_marla_min"] == 20.0

    def test_bare_yards_is_not_a_size_filter(self):
        # "100 yards from beach" is distance, not plot size — must not set size.
        assert "size_marla_min" not in parse_natural_query("house 100 yards from beach in Clifton", city="karachi")

    def test_size_plus_area_query_not_flagged_approximate(self):
        # Regression for the sq-yd token leak (sq/yd must not look like an area).
        from app.routes import _build_parse_query_response
        r = parse_natural_query("240 sq yd house in Clifton", city="karachi")
        resp = _build_parse_query_response("240 sq yd house in Clifton", "karachi", r)
        assert resp["filters"].get("area") == "Clifton"
        assert resp["filters"].get("area_approximate") is not True


class TestRegexBattery:
    """Wrong results from the 2026-10-07 regex battery. A wrong area is worse than none."""

    def test_johr_town_spelling_is_johar_town(self):
        result = parse_natural_query("johr town mein 2 kamray ka flat", city="lahore")
        assert result["area"] == "Johar Town"
        assert result["bedrooms"] == 2
        assert result["property_type"] == "apartment"

    def test_jauhar_town_spelling_is_johar_town(self):
        assert parse_natural_query("jauhar town ghar", city="lahore")["area"] == "Johar Town"

    def test_price_words_do_not_become_an_area(self):
        result = parse_natural_query("3 bed house 50 to 80 thousand", city="karachi")
        assert "area" not in result
        assert (result["price_min"], result["price_max"]) == (50000, 80000)

    def test_bare_amount_after_for_is_max_price(self):
        result = parse_natural_query("house for 45000", city="karachi")
        assert result["price_max"] == 45000
        assert result["property_type"] == "house"

    def test_two_areas_joined_by_or(self):
        result = parse_natural_query("DHA or Clifton flat under 80k", city="karachi")
        assert result["areas"] == ["DHA Defence", "Clifton"]
        assert result["area"] == "DHA Defence"
        assert result["price_max"] == 80000

    def test_single_area_has_no_areas_list(self):
        assert "areas" not in parse_natural_query("flat in clifton", city="karachi")

    def test_nipa_landmark_is_gulshan(self):
        result = parse_natural_query("sasta kamra near nipa", city="karachi")
        assert result["area"] == "Gulshan-e-Iqbal"

    def test_islamabad_sub_sector(self):
        result = parse_natural_query("G 11/3 lower portion", city="islamabad")
        assert result["area"] == "G 11 G 11 3"
        assert result["property_type"] == "lower_portion"

    def test_islamabad_sub_sector_hyphenated(self):
        assert parse_natural_query("g-11/3 flat", city="islamabad")["area"] == "G 11 G 11 3"


class TestMatchArea:
    def test_generic_word_alone_does_not_match(self):
        from app.parsing import match_area
        assert match_area("xyzzy town", city="lahore") is None

    def test_unrelated_text_does_not_match(self):
        from app.parsing import match_area
        assert match_area("to thousand", city="karachi") is None

    def test_misspelling_still_matches(self):
        from app.parsing import match_area
        assert match_area("gulbrg", city="lahore") == "Gulberg"

    def test_double_spaced_names_match_single_spaced_query(self):
        from app.parsing import match_area
        assert match_area("defence dha phase 6", city="lahore") in {
            "Defence  DHA  Phase 6", "Defence (DHA) Phase 6"}

    def test_suggestions_for_unmatched_query(self):
        from app.parsing import suggest_areas
        suggestions = suggest_areas("johr", city="lahore")
        assert "Johar Town" in suggestions
        assert len(suggestions) <= 3
