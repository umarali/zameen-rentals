"""tools/eval_listing_tags.py: sampling, weighting, Wilson bounds and the ship verdict."""
import asyncio
import csv
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.db_listings import upsert_listing
from app.decisions import Answer, Decision

_spec = importlib.util.spec_from_file_location(
    "eval_listing_tags", Path(__file__).resolve().parent.parent / "tools" / "eval_listing_tags.py")
ev = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ev)


class TestKeywords:
    def test_negated_bachelor_is_family(self):
        assert ev.keyword_tags("Upper portion, no bachelors")["tenant_fit"] == "family"

    def test_both_is_either(self):
        assert ev.keyword_tags("Only for family or working women")["tenant_fit"] == "either"

    def test_features(self):
        tags = ev.keyword_tags("Brand new house with 10kv solar and separate gate")
        assert tags["backup_power"] and tags["separate_entrance"] and tags["newly_built"]

    def test_separate_stairs_count(self):
        assert ev.keyword_tags("Upper portion with separate stairs")["separate_entrance"]
        assert ev.keyword_tags("Separate meters")["separate_entrance"] is None

    def test_stratum_is_rarest_hit(self):
        assert ev.stratum_of("brand new, solar, students welcome") == "tenant"
        assert ev.stratum_of("brand new with solar") == "backup_power"
        assert ev.stratum_of("lovely flat") == "none"


class TestAmenities:
    def test_absent_values_are_dropped(self):
        raw = json.dumps(["Solar Panels", "Electricity Backup: None", "Parking Spaces: 2"])
        assert ev.amenity_names(raw) == ["Solar Panels", "Parking Spaces: 2"]

    def test_amenity_tags(self):
        assert ev.amenity_tags(json.dumps(["Electricity Backup: Generator"]))["backup_power"]
        assert ev.amenity_tags(json.dumps(["Electricity Backup: None"]))["backup_power"] is None
        assert ev.amenity_tags(json.dumps(["Separate Entrance"]))["separate_entrance"]
        assert ev.amenity_tags("not json") == {"tenant_fit": None, "backup_power": None,
                                               "separate_entrance": None, "newly_built": None}

    def test_stratum_counts_amenities(self):
        assert ev.stratum_of("lovely flat", json.dumps(["Solar Panels"])) == "backup_power"


class TestStats:
    def test_wilson_lower_bound(self):
        assert ev.wilson_lower(0.9, 100) == pytest.approx(0.8256, abs=1e-3)
        assert ev.wilson_lower(1.0, 30) == pytest.approx(0.8865, abs=1e-3)
        assert ev.wilson_lower(0.5, 0) is None

    def test_weighting_changes_precision(self):
        # One false positive from a stratum 10x larger outweighs two true positives.
        items = [(True, True, 1.0), (True, True, 1.0), (True, False, 10.0), (False, True, 1.0)]
        m = ev.weighted_metrics(items)
        assert m["precision"] == pytest.approx(2 / 12)
        assert m["recall"] == pytest.approx(2 / 3)
        assert m["predicted"] == 3 and m["gold"] == 3

    def test_effective_n_shrinks_with_uneven_weights(self):
        even = ev.weighted_metrics([(True, True, 1.0)] * 50)
        uneven = ev.weighted_metrics([(True, True, 1.0)] * 49 + [(True, True, 50.0)])
        assert uneven["precision"] == even["precision"] == 1.0
        assert uneven["precision_lb"] < even["precision_lb"]

    def test_allocate_oversamples_hits(self):
        sizes = ev.allocate({"tenant": 40, "separate_entrance": 300, "backup_power": 500,
                             "newly_built": 4000, "none": 25000}, 350)
        assert sum(sizes.values()) == 350
        assert sizes["tenant"] == 40           # whole stratum when it's small
        assert sizes["none"] >= 117            # about a third stays random


def _metrics(lb, recall):
    return {"precision_lb": lb, "recall": recall}


class TestVerdict:
    def test_keywords_win_ties(self):
        assert ev.verdict({"keywords": _metrics(0.93, 0.60), "jev": _metrics(0.95, 0.65)})[0] == "keywords"

    def test_model_wins_with_clearly_more_recall(self):
        assert ev.verdict({"keywords": _metrics(0.93, 0.50), "jev": _metrics(0.92, 0.75)})[0] == "jev"

    def test_model_wins_when_keywords_fail(self):
        assert ev.verdict({"keywords": _metrics(0.70, 0.9), "jev": _metrics(0.91, 0.4),
                           "haiku": _metrics(0.85, 0.8)})[0] == "jev"

    def test_best_open_source_rule_sets_the_bar(self):
        results = {"keywords": _metrics(0.93, 0.40), "amenities": _metrics(0.95, 0.60),
                   "kw+amenities": _metrics(0.92, 0.70), "jev": _metrics(0.94, 0.75)}
        assert ev.verdict(results) == ("kw+amenities", "open source passes, and no model finds clearly more")
        results["jev"] = _metrics(0.94, 0.85)
        assert ev.verdict(results)[0] == "jev"

    def test_nothing_ships_below_bar(self):
        assert ev.verdict({"keywords": _metrics(0.80, 0.9), "jev": _metrics(None, None)})[0] == "none"


def _label_row(zid, stratum, population, title, description, tenant="", **flags):
    row = {"zameen_id": zid, "stratum": stratum, "stratum_population": str(population),
           "city": "lahore", "area_name": "Johar Town", "property_type": "House", "price": "65000",
           "bedrooms": "3", "area_size": "10 Marla", "amenities_json": "", "title": title,
           "description": description, "tenant_fit": tenant}
    for name in ev.FEATURES:
        row[name] = flags.get(name, "n")
    return row


class TestScoreRows:
    def test_scores_only_rows_every_system_predicted(self):
        labels = [
            _label_row("1", "tenant", 10, "Room", "Bachelors welcome", "bachelor"),
            _label_row("2", "none", 100, "Flat", "Nice flat", "unclear", backup_power="y"),
            _label_row("3", "none", 100, "Flat", "Nice flat"),  # not predicted by jev
        ]
        jev = {
            "1": {"tenant_fit": "bachelor", "tenant_fit_confidence": 0.9, "backup_power": 0.1,
                  "separate_entrance": 0.1, "newly_built": 0.1},
            "2": {"tenant_fit": "unclear", "tenant_fit_confidence": 0.9, "backup_power": 0.95,
                  "separate_entrance": 0.1, "newly_built": 0.1},
        }
        table, n_labelled, n_common = ev.score_rows(labels, {"jev": jev})
        assert (n_labelled, n_common) == (3, 2)
        assert table["bachelor_ok"]["jev"]["precision"] == 1.0
        assert table["backup_power"]["jev"]["recall"] == 1.0
        assert table["backup_power"]["keywords"]["recall"] == 0.0

    def test_unlabelled_rows_are_ignored(self):
        labels = [_label_row("1", "none", 5, "Flat", "x")]
        for c in ev.LABEL_COLUMNS:
            labels[0][c] = ""
        _, n_labelled, _ = ev.score_rows(labels, {})
        assert n_labelled == 0


class FakeJev:
    async def decide(self, state, questions):
        assert "Title: Room" in state and "Rent: PKR 65,000/month" in state
        return Decision(model="jev-1.13.0", input_tokens=300, answers={
            "tenant_fit": Answer("choice", "bachelor", 0.8),
            **{n: Answer("noul", 0.2, 0.6) for n in ev.FEATURES},
        })


class TestPredict:
    def test_jev_records(self):
        rows = [_label_row("1", "tenant", 10, "Room", "Bachelors welcome")]
        (rec,) = asyncio.run(ev.predict_jev(rows, FakeJev()))
        assert rec["tenant_fit"] == "bachelor" and rec["tenant_fit_confidence"] == 0.8
        assert rec["input_tokens"] == 300 and rec["backup_power"] == 0.2

    def test_haiku_record_scores_as_confident(self):
        parsed = SimpleNamespace(tenant_fit="family", backup_power=True,
                                 separate_entrance=False, newly_built=False)
        usage = SimpleNamespace(input_tokens=400, output_tokens=30)
        rec = ev.haiku_record("9", parsed, usage, 500.0)
        tags = ev.public_tags(rec)
        assert tags["tenant_fit"] == "family" and tags["backup_power"] is True
        assert tags["separate_entrance"] is None

    def test_haiku_prompt_carries_the_same_questions(self):
        system = ev._haiku_system()
        for name in ev.FEATURES:
            assert ev.QUESTIONS[name]["instructions"] in system
        assert "no bachelors" in system


class TestSample:
    def test_writes_stratified_csv_with_populations(self, tmp_path):
        for i in range(6):
            desc = "Students welcome" if i < 2 else "Solar installed" if i < 3 else "Plain"
            url = f"https://www.zameen.com/Property/t-80000{i}-1-1.html"
            upsert_listing(zameen_id=f"80000{i}", url=url, city="lahore",
                           card_data={"title": f"House {i}", "price": 50000})
            upsert_listing(zameen_id=f"80000{i}", url=url, city="lahore",
                           detail_data={"description": desc})
        out = tmp_path / "labels.csv"
        ev.sample(SimpleNamespace(n=4, out=str(out), seed=1, include_title_only=False, from_csv=None))
        with open(out, newline="") as f:
            rows = list(csv.DictReader(f))
        strata = {r["stratum"]: r["stratum_population"] for r in rows}
        assert strata["tenant"] == "2" and strata["none"] == "3"
        assert len(rows) == 4
        assert all(r["description"] for r in rows)


def test_read_preds_skips_blank_lines(tmp_path):
    path = tmp_path / "p.jsonl"
    path.write_text(json.dumps({"zameen_id": "1"}) + "\n\n")
    assert list(ev._read_preds(path)) == ["1"]


def test_sample_from_csv_export(tmp_path):
    export = tmp_path / "export.csv"
    with open(export, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["zameen_id", *ev.CONTEXT_COLUMNS])
        w.writerow(["1", "lahore", "DHA", "House", "90000", "4", "1 Kanal",
                    json.dumps(["Solar Panels"]), "Kanal house", "Lovely home"])
        w.writerow(["2", "lahore", "DHA", "House", "90000", "4", "1 Kanal", "", "Kanal house", ""])
        w.writerow(["3", "lahore", "DHA", "House", "90000", "4", "1 Kanal", "", "", "No title"])
    out = tmp_path / "labels.csv"
    ev.sample(SimpleNamespace(n=10, out=str(out), seed=1, include_title_only=False,
                              from_csv=str(export)))
    with open(out, newline="") as f:
        rows = list(csv.DictReader(f))
    assert [(r["zameen_id"], r["stratum"]) for r in rows] == [("1", "backup_power")]
    assert "Electricity Backup" in (tmp_path / "labels.guide.txt").read_text()
