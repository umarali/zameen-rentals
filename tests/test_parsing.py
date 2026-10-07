"""Parser-level regressions for Roman Urdu rental queries."""
import pytest

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


class TestMultiAreaOffsets:
    """Codex review 2026-10-07, finding 3: every area span and joiner check must
    index the same string, even after bed/size/furnished text is consumed."""

    def test_urdu_alternatives_after_bed_prefix(self):
        result = parse_natural_query("2 bed کلفٹن or گلشن اقبال", city="karachi")
        assert result["bedrooms"] == 2
        assert result["areas"] == ["Clifton", "Gulshan-e-Iqbal"]
        assert result["area"] == "Clifton"

    def test_mixed_script_after_bed_prefix(self):
        result = parse_natural_query("2 bed کلفٹن or DHA", city="karachi")
        assert result["areas"] == ["Clifton", "DHA Defence"]

    def test_mixed_script_after_furnished_and_size_prefix(self):
        result = parse_natural_query("furnished 5 marla کلفٹن or DHA", city="karachi")
        assert result["furnished"] is True
        assert result["size_marla_min"] == 5.0
        assert result["areas"] == ["Clifton", "DHA Defence"]

    def test_english_only_control(self):
        result = parse_natural_query("2 bed DHA or Clifton", city="karachi")
        assert result["areas"] == ["DHA Defence", "Clifton"]

    def test_unjoined_mentions_stay_single(self):
        assert "areas" not in parse_natural_query("2 bed کلفٹن near DHA", city="karachi")


class TestBlockNumbers:
    """A block number the user typed must not be dropped or swapped (fe report 2026-10-07)."""

    def test_exact_block_name_beats_shorter_alias(self):
        assert parse_natural_query("flat in clifton block 5", city="karachi")["area"] == "Clifton Block 5"

    def test_misspelled_block_keeps_its_number(self):
        assert parse_natural_query("flat in clifftn blok 5", city="karachi")["area"] == "Clifton Block 5"

    def test_price_digits_do_not_block_a_misspelled_area(self):
        assert parse_natural_query("flat in clifftn under 50000", city="karachi")["area"] == "Clifton"

    def test_unknown_block_number_does_not_pick_another_block(self):
        from app.parsing import match_area
        assert match_area("clifton blok 99", city="karachi") in (None, "Clifton")

    def test_trailing_number_of_a_size_is_not_part_of_the_area(self):
        result = parse_natural_query("furnished house askari 5 marla", city="lahore")
        assert result["area"] == "Askari"
        assert result["size_marla_min"] == 5.0

    def test_numbered_area_followed_by_other_words_still_matches(self):
        assert parse_natural_query("askari 5 house", city="lahore")["area"] == "Askari 5"


class TestAreaReviewRegressions:
    @pytest.mark.parametrize("budget", ["under 50000", "under 80k", "50k to 80k", "for 45000"])
    def test_budget_does_not_override_fuzzy_block(self, budget):
        result = parse_natural_query(f"flat in clifftn blok 5 {budget}", city="karachi")
        assert result["area"] == "Clifton Block 5"
        assert result["price_max"] is not None

    @pytest.mark.parametrize("joiner", ["یا", "اور"])
    def test_urdu_area_alternatives(self, joiner):
        result = parse_natural_query(f"2 بیڈ کلفٹن {joiner} گلشن اقبال", city="karachi")
        assert result["areas"] == ["Clifton", "Gulshan-e-Iqbal"]
        assert result["bedrooms"] == 2

    def test_all_known_urdu_aliases_survive_filter_prefixes(self):
        from app.data import URDU_AREAS, get_areas
        for alias, name in URDU_AREAS.items():
            if name not in get_areas("karachi"):
                continue  # The known dangling aliases are outside this branch's scope.
            for query in (alias, f"2 بیڈ فلیٹ {alias} میں 50000 تک", f"furnished 5 marla {alias}"):
                assert parse_natural_query(query, "karachi")["area"] == name, query
