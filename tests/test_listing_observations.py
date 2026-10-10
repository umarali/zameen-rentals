"""listing_observations: append-only evidence of what Zameen showed, and when."""
import csv
import gzip
import io
import json
import importlib.util
import sys
from pathlib import Path

from app.database import _get_conn
from app.db_listings import get_listing_by_zameen_id, mark_stale_listings, upsert_listing
from app.listing_observations import get_observations, record_observation, utc_iso, version_hash

URL = "https://www.zameen.com/Property/clifton_flat-54783265-5-4.html"
PAGE = "https://www.zameen.com/Rentals/Karachi_Clifton-5-1.html"


def _card(**extra):
    return {"title": "2 Bed Flat", "price": 85000, "bedrooms": 2, "area_size": "5 Marla",
            "image_url": "https://media.zameen.com/thumbnails/1-400x300.jpeg",
            "added": "Added: 3 hours ago", "updated": "Updated: 3 hours ago", **extra}


def _state(**lifecycle):
    base = {"created_epoch": 1791584578.0, "updated_epoch": 1791584578.0,
            "product": "hot", "state": "active", "purpose": "for-rent",
            "agency_external_id": "180373", "agency_tier": 4}
    return {"property_type": None, "latitude": None, "longitude": None, "contact": None,
            "location_path": [], "lifecycle": {**base, **lifecycle}}


def _crawl(card=None, state=None):
    return upsert_listing(zameen_id="54783265", url=URL, city="karachi", area_name="Clifton",
                          card_data=card or _card(), search_state=state or _state(),
                          source_page=PAGE)


class TestLiveObservations:
    def test_first_crawl_records_zameen_fields_and_page(self):
        _crawl()
        [obs] = get_observations("54783265")
        assert obs["source"] == "search_card"
        assert obs["created_epoch"] == 1791584578.0
        assert obs["product"] == "hot"
        assert obs["agency_external_id"] == "180373"
        assert obs["added_text"] == "Added: 3 hours ago"
        assert obs["price"] == 85000
        assert obs["page_url"] == PAGE
        assert obs["observation_count"] == 1
        assert obs["first_observed_at"].endswith("+00:00")

    def test_seeing_the_same_version_extends_it(self):
        _crawl()
        _crawl(card=_card(added="Added: 9 hours ago"))
        [obs] = get_observations("54783265")
        assert obs["observation_count"] == 2
        assert obs["added_text"] == "Added: 3 hours ago"
        assert obs["last_added_text"] == "Added: 9 hours ago"
        assert obs["last_observed_at"] >= obs["first_observed_at"]

    def test_moved_created_date_keeps_the_old_version(self):
        _crawl(card=_card(added="Added: 2 months ago"), state=_state(created_epoch=1786000000.0))
        _crawl(card=_card(added="Added: 17 hours ago"), state=_state(created_epoch=1791584578.0))
        old, new = get_observations("54783265")
        assert (old["created_epoch"], old["added_text"]) == (1786000000.0, "Added: 2 months ago")
        assert (new["created_epoch"], new["added_text"]) == (1791584578.0, "Added: 17 hours ago")

    def test_without_epochs_a_label_change_is_a_new_version(self):
        upsert_listing(zameen_id="54783265", url=URL, city="karachi",
                       card_data=_card(added="Added: 1 month ago"))
        upsert_listing(zameen_id="54783265", url=URL, city="karachi",
                       card_data=_card(added="Added: 2 hours ago"))
        assert [o["added_text"] for o in get_observations("54783265")] == [
            "Added: 1 month ago", "Added: 2 hours ago"]

    def test_price_change_is_recorded_and_history_survives_listing_edits(self):
        _crawl()
        _crawl(card=_card(price=80000, title="2 Bed Flat Reduced"))
        assert [o["price"] for o in get_observations("54783265")] == [85000, 80000]
        assert get_listing_by_zameen_id("54783265")["price"] == 80000

    def test_unchanged_listing_row_still_records(self):
        assert _crawl() == "inserted"
        assert _crawl() == "unchanged"
        assert get_observations("54783265")[0]["observation_count"] == 2

    def test_detail_page_lifecycle_is_stored_but_not_written_to_listing(self):
        _crawl()
        detail = {"description": "Corner flat.",
                  "zameen_lifecycle": {"created_epoch": 1791591051.0, "reactivated_epoch": 1702355471.0,
                                       "approved_epoch": 1702355471.0, "price": 85000}}
        upsert_listing(zameen_id="54783265", url=URL, city="karachi", detail_data=detail)
        assert "zameen_lifecycle" in detail  # caller's dict untouched
        detail_obs = [o for o in get_observations("54783265") if o["source"] == "detail_page"]
        assert detail_obs[0]["reactivated_epoch"] == 1702355471.0
        assert detail_obs[0]["page_url"] == URL
        assert get_listing_by_zameen_id("54783265")["description"] == "Corner flat."

    def test_observation_failure_does_not_fail_the_listing_write(self, monkeypatch):
        def boom(*args, **kwargs):
            raise RuntimeError("observation store broken")
        monkeypatch.setattr("app.db_listings.record_observation", boom)
        assert _crawl() == "inserted"
        assert get_listing_by_zameen_id("54783265") is not None


class TestRecordObservation:
    def test_version_ignores_labels_when_epochs_exist(self):
        a = {"created_epoch": 1.0, "added_text": "Added: 3 hours ago"}
        b = {"created_epoch": 1.0, "added_text": "Added: 4 hours ago"}
        assert version_hash(a) == version_hash(b)
        assert version_hash({"added_text": "x"}) != version_hash({"added_text": "y"})

    def test_unmerged_import_is_idempotent(self):
        conn = _get_conn()
        args = dict(observed_at="2026-10-07T17:43:41+00:00", provenance="{}", merge=False)
        fields = {"added_text": "Added: 2 months ago"}
        assert record_observation(conn, "1", "snapshot_import", fields, **args) == "inserted"
        assert record_observation(conn, "1", "snapshot_import", fields, **args) == "duplicate"

    def test_utc_iso_marks_naive_times_as_utc(self):
        assert utc_iso("2026-10-07T17:43:41.107842") == "2026-10-07T17:43:41+00:00"
        assert utc_iso("2026-10-07 05:56:17") == "2026-10-07T05:56:17+00:00"
        assert utc_iso(None) is None


class TestSnapshotImportTool:
    def _write(self, tmp_path, rows):
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
        path = tmp_path / "snap.csv.gz"
        path.write_bytes(gzip.compress(buf.getvalue().encode()))
        return path

    def test_imports_both_observations_with_provenance_once(self, tmp_path, monkeypatch):
        row = {"zameen_id": "54162140", "city": "lahore", "is_active": "1",
               "oct7_card_scraped_at": "2026-10-07T17:43:41.111016",
               "oct7_added_text": "Added: 2 months ago", "oct7_updated_text": "",
               "cur_card_scraped_at": "2026-10-10T02:34:10.242201",
               "cur_added_text": "Added: 17 hours ago", "cur_updated_text": "Updated: 17 hours ago",
               "cur_first_seen_at": "2026-10-07 06:00:00", "cur_last_seen_at": "2026-10-10T02:34:10"}
        path = self._write(tmp_path, [row])
        spec = importlib.util.spec_from_file_location(
            "import_observation_snapshot",
            Path(__file__).resolve().parent.parent / "tools" / "import_observation_snapshot.py")
        tool = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(tool)
        monkeypatch.setattr(sys, "argv", ["import_observation_snapshot.py", str(path)])
        tool.main()
        tool.main()
        rows = get_observations("54162140")
        assert [(r["first_observed_at"], r["added_text"]) for r in rows] == [
            ("2026-10-07T17:43:41+00:00", "Added: 2 months ago"),
            ("2026-10-10T02:34:10+00:00", "Added: 17 hours ago"),
        ]
        provenance = json.loads(rows[0]["provenance"])
        assert provenance["file"] == "snap.csv" and provenance["columns"] == "oct7"
        assert len(provenance["sha256"]) == 64


class TestTimestampComparisons:
    def test_stale_marking_compares_times_not_text(self):
        upsert_listing(zameen_id="1001", url="https://www.zameen.com/Property/a-1001-1-1.html",
                       city="karachi", card_data={"title": "Old", "price": 1})
        conn = _get_conn()
        # Same calendar day as the cut-off, one minute past it, written with a 'T' like the crawler.
        conn.execute("UPDATE listings SET last_seen_at = strftime('%Y-%m-%dT%H:%M:%f', 'now', '-7 days', '-1 minutes')")
        conn.commit()
        assert mark_stale_listings(days=7) == 1


class TestRecentlyFoundSort:
    def _seed(self, zid, added, first_seen):
        upsert_listing(zameen_id=zid, url=f"https://www.zameen.com/Property/x-{zid}-1-1.html",
                       city="karachi", area_name="Clifton",
                       card_data={"title": f"Flat {zid}", "price": 50000, "added": added})
        conn = _get_conn()
        conn.execute("UPDATE listings SET first_seen_at = ? WHERE zameen_id = ?", (first_seen, zid))
        conn.commit()

    def test_newest_orders_by_when_we_first_saw_it_not_zameens_date(self):
        from app.db_listings import search_listings
        # Seen long ago, but Zameen now says "added 1 hour ago" (a moved date).
        self._seed("2001", "Added: 1 hour ago", "2026-09-01 00:00:00")
        # Genuinely new to us, though Zameen says 2 months.
        self._seed("2002", "Added: 2 months ago", "2026-10-09 00:00:00")
        ids = [r["zameen_id"] for r in search_listings(city="karachi", sort="newest")["results"]]
        assert ids == ["2002", "2001"]

    def test_nearby_newest_uses_first_seen_too(self):
        from app.db_listings import search_nearby_listings
        self._seed("2001", "Added: 1 hour ago", "2026-09-01 00:00:00")
        self._seed("2002", "Added: 2 months ago", "2026-10-09 00:00:00")
        conn = _get_conn()
        conn.execute("UPDATE listings SET latitude = 24.82, longitude = 67.03, location_source = 'listing_exact'")
        conn.commit()
        result = search_nearby_listings(city="karachi", lat=24.82, lng=67.03, radius_km=5, sort="newest")
        assert [r["zameen_id"] for r in result["results"]] == ["2002", "2001"]
