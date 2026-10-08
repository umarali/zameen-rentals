"""Scoring rules in tools/eval_nl_parser.py."""
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "eval_nl_parser", Path(__file__).resolve().parent.parent / "tools" / "eval_nl_parser.py")
ev = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ev)


def _case(expect, **extra):
    return {"id": "t", "city": "karachi", "q": "x", "expect": expect, **extra}


def test_right_area_is_correct():
    fields, verdict = ev.score_case(_case({"area": "Clifton"}), {"area": "Clifton"})
    assert verdict == "correct" and fields["area"]


def test_wrong_unflagged_area_is_silent_wrong():
    fields, verdict = ev.score_case(_case({"area": "Clifton"}), {"area": "Saddar"})
    assert verdict == "silent_wrong" and not fields["area"]


def test_wrong_flagged_area_counts_only_when_approx_ok():
    _, verdict = ev.score_case(_case({"area": "Clifton"}), {"area": "Saddar", "area_approximate": True})
    assert verdict == "flagged"
    fields, _ = ev.score_case(_case({"area": "Clifton"}, approx_ok=True),
                              {"area": "Saddar", "area_approximate": True})
    assert fields["area"]


def test_missing_block_must_be_flagged():
    fields, verdict = ev.score_case(_case({"area": "Gulshan-e-Iqbal"}, approx_ok=True), {"area": "Gulshan-e-Iqbal"})
    assert verdict == "unflagged_approx" and not fields["area"]


def test_needless_flag_on_right_area_is_a_false_flag_but_still_right():
    fields, verdict = ev.score_case(_case({"area": "Clifton"}), {"area": "Clifton", "area_approximate": True})
    assert verdict == "false_flag" and fields["area"]


def test_area_any_and_no_area_expectations():
    _, verdict = ev.score_case(_case({}, area_any=["Saddar", "Clifton"]), {"area": "Clifton"})
    assert verdict == "correct"
    _, verdict = ev.score_case(_case({"area": None}), {"area": "Clifton"})
    assert verdict == "silent_wrong"
    _, verdict = ev.score_case(_case({"area": None}), {})
    assert verdict == "correct"


def test_null_means_absent_and_sizes_compare_numerically():
    fields, _ = ev.score_case(_case({"bedrooms": None, "size_marla_min": 10}),
                              {"bedrooms": 2, "size_marla_min": 10.0})
    assert fields == {"bedrooms": False, "size_marla_min": True}


def test_same_location_id_counts_as_same_area():
    from app.data import get_areas
    areas = get_areas("lahore")
    by_id = {}
    for name, info in areas.items():
        by_id.setdefault(info[1], []).append(name)
    twins = next((names for names in by_id.values() if len(names) > 1), None)
    if twins:
        assert ev._same_area(twins[0], twins[1], "lahore")
    assert not ev._same_area("Johar Town", "Model Town", "lahore")
