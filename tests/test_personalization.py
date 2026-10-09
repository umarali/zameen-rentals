"""Tests for the personalization layer: alerts, matching, favorites, hidden,
recent views, and the supporting API surface."""
from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app import app
from app.database import _get_conn
from app.db_listings import upsert_listing
from app import personalization as pers


CLIENT_ID = "test-client-personalization-001"
OTHER_CLIENT_ID = "test-client-other-002"


@pytest.fixture(autouse=True)
def _ensure_personalization_schema(fresh_db):
    pers.init_personalization_schema()
    yield


@pytest.fixture
def client():
    return TestClient(app)


def _insert_listing(zameen_id: str, **overrides) -> int:
    base = {
        "title": "Test", "price": 60000, "bedrooms": 2, "bathrooms": 1,
        "area_size": "5 Marla", "property_type": "Apartment / Flat",
    }
    base.update(overrides.pop("card_data", {}))
    upsert_listing(
        zameen_id=zameen_id,
        url=f"https://zameen.com/Property/test-{zameen_id}-1-1.html",
        city=overrides.pop("city", "lahore"),
        area_name=overrides.pop("area_name", "Gulberg"),
        area_slug="Lahore_Gulberg",
        card_data=base,
        **overrides,
    )
    conn = _get_conn()
    return conn.execute(
        "SELECT id FROM listings WHERE zameen_id = ?", (zameen_id,)
    ).fetchone()["id"]


# ── normalize_filters / derive_alert_label ───────────────────────────────────


class TestNormalizeFilters:
    def test_rejects_malformed_full_text_query(self):
        with pytest.raises(ValueError, match="full-text"):
            pers.normalize_filters({"q": '"'})

    def test_strips_unknown_and_empty(self):
        out = pers.normalize_filters({
            "city": "lahore", "bedrooms": "2", "price_max": "",
            "garbage": "x", "furnished": "true", "area": "  ",
        })
        assert out == {"city": "lahore", "bedrooms": 2, "furnished": True}

    def test_defaults_city_to_lahore(self):
        assert pers.normalize_filters({"bedrooms": 1})["city"] == "lahore"

    def test_rejects_negative_numbers(self):
        out = pers.normalize_filters({"city": "lahore", "price_min": -10})
        assert "price_min" not in out

    def test_furnished_false_means_unfurnished(self):
        assert pers.normalize_filters({"city": "lahore", "furnished": False})["furnished"] is False
        assert pers.normalize_filters({"city": "lahore", "furnished": "false"})["furnished"] is False
        assert pers.normalize_filters({"city": "lahore", "furnished": "0"})["furnished"] is False

    def test_furnished_absent_or_unrecognised_is_no_preference(self):
        assert "furnished" not in pers.normalize_filters({"city": "lahore"})
        assert "furnished" not in pers.normalize_filters({"city": "lahore", "furnished": None})
        assert "furnished" not in pers.normalize_filters({"city": "lahore", "furnished": "maybe"})

    def test_invalid_dict_raises(self):
        with pytest.raises(ValueError):
            pers.normalize_filters("nope")  # type: ignore[arg-type]


class TestPushTransport:
    @pytest.mark.parametrize("endpoint", [
        "https://fcm.googleapis.com/fcm/send/test",
        "https://updates.push.services.mozilla.com/wpush/v2/test",
        "https://web.push.apple.com/test",
        "https://wns2-db5p.notify.windows.com/test",
    ])
    def test_browser_push_providers_accepted(self, endpoint):
        pers.validate_push_endpoint(endpoint)

    def test_legacy_unsafe_endpoint_never_reaches_transport(self, monkeypatch):
        def unexpected_send(**kwargs):
            pytest.fail("Unsafe endpoint reached the network transport")

        monkeypatch.setattr("pywebpush.webpush", unexpected_send)
        assert pers.send_push({"endpoint": "http://127.0.0.1/private"}, {}) is False

    def test_redirects_disabled_and_timeout_bounded(self, monkeypatch):
        from types import SimpleNamespace
        seen = {}

        def fake_request(self, method, url, **kwargs):
            seen.update(kwargs)
            return SimpleNamespace(status_code=302)

        def fake_webpush(**kwargs):
            assert kwargs["timeout"] == 10
            return kwargs["requests_session"].post(
                kwargs["subscription_info"]["endpoint"], timeout=kwargs["timeout"],
            )

        monkeypatch.setattr("requests.Session.request", fake_request)
        monkeypatch.setattr("pywebpush.webpush", fake_webpush)
        assert pers.send_push({
            "endpoint": "https://fcm.googleapis.com/fcm/send/test",
            "p256dh": "fake", "auth": "fake",
        }, {}) is False
        assert seen["allow_redirects"] is False


class TestDeriveAlertLabel:
    def test_simple_label(self):
        label = pers.derive_alert_label({
            "city": "lahore", "bedrooms": 2, "price_max": 80000,
        })
        assert "2 bed" in label
        assert "Lahore" in label
        assert "80K" in label

    def test_furnishing_label(self):
        assert pers.derive_alert_label({"city": "lahore", "furnished": True}).endswith("furnished")
        assert pers.derive_alert_label({"city": "lahore", "furnished": False}).endswith("unfurnished")
        assert "furnished" not in pers.derive_alert_label({"city": "lahore"})

    def test_bedrooms_range(self):
        label = pers.derive_alert_label({
            "city": "lahore", "bedrooms": 2, "bedrooms_max": 4,
        })
        assert "2-4 bed" in label


# ── Alerts CRUD ──────────────────────────────────────────────────────────────


class TestAlertCRUD:
    def test_create_returns_alert(self):
        alert = pers.create_alert(CLIENT_ID, label="My alert",
                                  filters={"city": "lahore", "bedrooms": 2})
        assert alert["id"] > 0
        assert alert["label"] == "My alert"
        assert alert["filters"]["bedrooms"] == 2
        assert alert["client_id"] == CLIENT_ID
        assert alert["paused"] is False
        assert alert["notify_push"] is True

    def test_label_auto_generated_when_blank(self):
        alert = pers.create_alert(CLIENT_ID, label=None,
                                  filters={"city": "lahore", "bedrooms": 3})
        assert alert["label"]
        assert "3 bed" in alert["label"]

    def test_seed_last_seen_id_excludes_existing_listings(self):
        # Existing listing — should NOT match the alert created later.
        _insert_listing("EXISTING-1", card_data={"price": 50000})
        alert = pers.create_alert(CLIENT_ID, label=None,
                                  filters={"city": "lahore", "bedrooms": 2})
        assert alert["last_seen_id"] > 0
        # No matches should exist yet.
        matches = pers.list_matches(CLIENT_ID)
        assert matches == []

    def test_alert_limit_enforced(self):
        for i in range(pers.MAX_ALERTS_PER_CLIENT):
            pers.create_alert(CLIENT_ID, label=f"a{i}",
                              filters={"city": "lahore", "bedrooms": 1})
        with pytest.raises(ValueError):
            pers.create_alert(CLIENT_ID, label="overflow",
                              filters={"city": "lahore"})

    def test_update_alert(self):
        alert = pers.create_alert(CLIENT_ID, label=None,
                                  filters={"city": "lahore", "bedrooms": 1})
        updated = pers.update_alert(CLIENT_ID, alert["id"],
                                    label="Renamed", paused=True,
                                    notify_push=False)
        assert updated["label"] == "Renamed"
        assert updated["paused"] is True
        assert updated["notify_push"] is False

    def test_update_alert_filters(self):
        alert = pers.create_alert(CLIENT_ID, label=None,
                                  filters={"city": "lahore", "bedrooms": 1})
        updated = pers.update_alert(CLIENT_ID, alert["id"],
                                    filters={"city": "karachi", "bedrooms": 2})
        assert updated["filters"]["city"] == "karachi"
        assert updated["filters"]["bedrooms"] == 2

    def test_update_alert_wrong_client_returns_none(self):
        alert = pers.create_alert(CLIENT_ID, label=None,
                                  filters={"city": "lahore"})
        assert pers.update_alert(OTHER_CLIENT_ID, alert["id"], paused=True) is None

    def test_delete_alert(self):
        alert = pers.create_alert(CLIENT_ID, label=None, filters={"city": "lahore"})
        assert pers.delete_alert(CLIENT_ID, alert["id"]) is True
        assert pers.delete_alert(CLIENT_ID, alert["id"]) is False

    def test_delete_alert_removes_unseen_matches(self):
        alert = pers.create_alert(CLIENT_ID, label=None, filters={"city": "lahore"})
        _insert_listing("DELETE-MATCH-1")
        assert pers.unseen_match_count(CLIENT_ID) == 1
        assert pers.delete_alert(CLIENT_ID, alert["id"]) is True
        assert pers.unseen_match_count(CLIENT_ID) == 0

    def test_other_client_cannot_delete(self):
        alert = pers.create_alert(CLIENT_ID, label=None, filters={"city": "lahore"})
        assert pers.delete_alert(OTHER_CLIENT_ID, alert["id"]) is False
        # Still visible to the rightful owner.
        assert pers.get_alert(CLIENT_ID, alert["id"]) is not None


# ── Matching ─────────────────────────────────────────────────────────────────


class TestMatching:
    def test_bad_legacy_query_does_not_block_other_alerts(self, monkeypatch):
        bad = pers.create_alert(CLIENT_ID, label="Bad", filters={"city": "lahore"})
        pers.create_alert(OTHER_CLIENT_ID, label="Good", filters={"city": "lahore"})
        conn = _get_conn()
        conn.execute("UPDATE alerts SET filters_json = ? WHERE id = ?",
                     (json.dumps({"city": "lahore", "q": '"'}), bad["id"]))
        conn.commit()
        monkeypatch.setattr(pers, "record_match_for_inserted_listing", lambda *a, **k: [])
        _insert_listing("LEGACY-QUERY-1")
        summary = pers.run_match_cycle(dispatch=False)
        assert summary["matches"] == 1
        assert pers.list_matches(OTHER_CLIENT_ID)[0]["zameen_id"] == "LEGACY-QUERY-1"

    def test_insert_hook_does_not_skip_an_earlier_missed_match(self, monkeypatch):
        pers.create_alert(CLIENT_ID, label=None, filters={"city": "lahore"})
        with monkeypatch.context() as patch:
            patch.setattr(pers, "record_match_for_inserted_listing", lambda *a, **k: [])
            _insert_listing("MISSED-1")
        _insert_listing("HOOK-2")
        pers.run_match_cycle(dispatch=False)
        assert {m["zameen_id"] for m in pers.list_matches(CLIENT_ID)} == {"MISSED-1", "HOOK-2"}

    def test_new_listing_matches_alert(self):
        alert = pers.create_alert(CLIENT_ID, label=None,
                                  filters={"city": "lahore", "bedrooms": 2})
        listing_id = _insert_listing("MATCH-1")
        # The upsert hook should have recorded a match in real time.
        matches = pers.list_matches(CLIENT_ID)
        assert len(matches) == 1
        assert matches[0]["zameen_id"] == "MATCH-1"
        # Cycle-based scan should be idempotent (no duplicate match).
        pers.run_match_cycle(dispatch=False)
        assert len(pers.list_matches(CLIENT_ID)) == 1

    def test_furnishing_alerts_need_evidence(self):
        pers.create_alert(CLIENT_ID, label=None, filters={"city": "lahore", "furnished": False})
        pers.create_alert(OTHER_CLIENT_ID, label=None, filters={"city": "lahore", "furnished": True})
        _insert_listing("FURN-1", card_data={"title": "Fully Furnished Flat"})
        _insert_listing("UNFURN-1", card_data={"title": "Unfurnished Flat"})
        _insert_listing("NOT-1", card_data={"title": "Flat, Not Furnished"})
        _insert_listing("PLAIN-1", card_data={"title": "Flat"})
        _insert_listing("BOTH-1", card_data={"title": "Furnished and non furnished flats"})
        pers.run_match_cycle(dispatch=False)
        assert {m["zameen_id"] for m in pers.list_matches(CLIENT_ID)} == {"UNFURN-1", "NOT-1"}
        assert {m["zameen_id"] for m in pers.list_matches(OTHER_CLIENT_ID)} == {"FURN-1"}

    def test_sql_and_python_alert_matchers_agree(self):
        filters_by_value = {v: {"city": "lahore", "furnished": v} for v in (True, False)}
        titles = ["Fully Furnished Flat", "Unfurnished Flat", "Flat, Not Furnished", "Flat",
                  "Furnished and non furnished flats", "Semi furnished flat"]
        for i, title in enumerate(titles):
            _insert_listing(f"AGREE-{i}", card_data={"title": title})
        rows = [dict(r) for r in _get_conn().execute(
            "SELECT * FROM listings WHERE zameen_id LIKE 'AGREE-%'").fetchall()]
        for filters in filters_by_value.values():
            conds, params = pers._build_match_clauses(filters, listings_alias="l")
            sql_ids = {r["zameen_id"] for r in _get_conn().execute(
                f"SELECT l.zameen_id FROM listings l WHERE {' AND '.join(conds)}", params)}
            py_ids = {r["zameen_id"] for r in rows if pers.listing_matches_alert(r, filters)}
            assert sql_ids == py_ids

    def test_non_matching_listing_ignored(self):
        pers.create_alert(CLIENT_ID, label=None,
                          filters={"city": "lahore", "bedrooms": 3, "price_max": 50000})
        _insert_listing("NOMATCH-1", card_data={"price": 60000, "bedrooms": 2})
        assert pers.list_matches(CLIENT_ID) == []

    def test_late_discovery_of_old_source_listing_does_not_trigger_alert(self):
        pers.create_alert(CLIENT_ID, label=None, filters={"city": "lahore"})

        _insert_listing("OLD-SOURCE-1", card_data={"added": "Added: 1 week ago"})

        assert pers.list_matches(CLIENT_ID) == []

    def test_match_cycle_prunes_old_discoveries_recorded_before_source_time_filter(self):
        alert = pers.create_alert(CLIENT_ID, label=None, filters={"city": "lahore"})
        listing_id = _insert_listing("OLD-PENDING-1", card_data={"added": "Added: 1 week ago"})
        conn = _get_conn()
        conn.execute(
            """
            INSERT INTO alert_matches (alert_id, client_id, listing_id, zameen_id)
            VALUES (?, ?, ?, ?)
            """,
            (alert["id"], CLIENT_ID, listing_id, "OLD-PENDING-1"),
        )
        conn.commit()

        summary = pers.run_match_cycle(dispatch=False)

        assert summary["stale_pruned"] == 1
        assert pers.list_matches(CLIENT_ID) == []

    def test_paused_alert_does_not_match(self):
        alert = pers.create_alert(CLIENT_ID, label=None,
                                  filters={"city": "lahore", "bedrooms": 2})
        pers.update_alert(CLIENT_ID, alert["id"], paused=True)
        _insert_listing("PAUSED-1")
        assert pers.list_matches(CLIENT_ID) == []

    def test_city_filter_isolates_alerts(self):
        pers.create_alert(CLIENT_ID, label=None,
                          filters={"city": "karachi", "bedrooms": 2})
        _insert_listing("LAHORE-ONLY", city="lahore")
        assert pers.list_matches(CLIENT_ID) == []

    def test_unseen_count_drops_after_mark_seen(self):
        pers.create_alert(CLIENT_ID, label=None, filters={"city": "lahore", "bedrooms": 2})
        _insert_listing("UNSEEN-1")
        assert pers.unseen_match_count(CLIENT_ID) == 1
        updated = pers.mark_matches_seen(CLIENT_ID)
        assert updated == 1
        assert pers.unseen_match_count(CLIENT_ID) == 0

    def test_run_match_cycle_picks_up_listings_inserted_before_alert_extension(self):
        # Insert listing, then create an alert whose filters match it.
        # Because alert seeds last_seen_id to current MAX(id), this listing
        # should NOT match — that's the intended "no backlog spam" behavior.
        _insert_listing("BACKLOG-1")
        pers.create_alert(CLIENT_ID, label=None,
                          filters={"city": "lahore", "bedrooms": 2})
        summary = pers.run_match_cycle(dispatch=False)
        assert summary["matches"] == 0

    def test_size_filter_insert_hook_accepts_matching_listing(self):
        pers.create_alert(CLIENT_ID, label=None, filters={
            "city": "lahore", "bedrooms": 2, "size_marla_min": 3,
        })
        _insert_listing("SIZE-1", card_data={"area_size": "5 Marla"})
        assert len(pers.list_matches(CLIENT_ID)) == 1

    def test_size_filter_insert_hook_rejects_undersized_listing(self):
        pers.create_alert(CLIENT_ID, label=None, filters={
            "city": "lahore", "size_marla_min": 10,
        })
        _insert_listing("SIZE-SMALL-1", card_data={"area_size": "5 Marla"})
        assert pers.list_matches(CLIENT_ID) == []

    def test_text_filter_insert_hook_rejects_non_matching_listing(self):
        pers.create_alert(CLIENT_ID, label=None, filters={
            "city": "lahore", "q": "garden",
        })
        _insert_listing("TEXT-NOMATCH-1", card_data={"title": "Apartment in Gulberg"})
        assert pers.list_matches(CLIENT_ID) == []

    def test_find_new_matches_does_not_skip_rows_after_limit(self):
        alert = pers.create_alert(CLIENT_ID, label=None, filters={"city": "lahore"})
        pers.update_alert(CLIENT_ID, alert["id"], paused=True)
        for i in range(51):
            _insert_listing(f"BATCH-{i:02d}")
        pers.update_alert(CLIENT_ID, alert["id"], paused=False)
        assert len(pers.find_new_matches(limit_per_alert=50)) == 50
        assert len(pers.find_new_matches(limit_per_alert=50)) == 1
        assert len(pers.list_matches(CLIENT_ID, limit=100)) == 51

    def test_insert_hook_match_is_dispatched_on_cycle(self, monkeypatch):
        alert = pers.create_alert(CLIENT_ID, label=None, filters={"city": "lahore"})
        pers.save_push_subscription(
            CLIENT_ID,
            endpoint="https://fcm.googleapis.com/fcm/send/dispatch",
            p256dh="fake-p256dh",
            auth="fake-auth",
        )
        monkeypatch.setattr(pers, "send_push", lambda subscription, payload: True)
        _insert_listing("PUSH-DISPATCH-1")
        summary = pers.run_match_cycle(dispatch=True)
        assert summary["matches"] == 0
        assert summary["sent"] == 1
        match = _get_conn().execute(
            "SELECT notified_push FROM alert_matches WHERE alert_id = ?",
            (alert["id"],),
        ).fetchone()
        assert match["notified_push"] == 1

    def test_failed_push_remains_pending_for_retry(self, monkeypatch):
        alert = pers.create_alert(CLIENT_ID, label=None, filters={"city": "lahore"})
        pers.save_push_subscription(
            CLIENT_ID,
            endpoint="https://fcm.googleapis.com/fcm/send/retry",
            p256dh="fake-p256dh",
            auth="fake-auth",
        )
        monkeypatch.setattr(pers, "send_push", lambda subscription, payload: False)
        _insert_listing("PUSH-RETRY-1")
        assert pers.run_match_cycle(dispatch=True)["failed"] == 1
        match = _get_conn().execute(
            "SELECT notified_push FROM alert_matches WHERE alert_id = ?",
            (alert["id"],),
        ).fetchone()
        assert match["notified_push"] == 0
        monkeypatch.setattr(pers, "send_push", lambda subscription, payload: True)
        assert pers.run_match_cycle(dispatch=True)["sent"] == 1

    def test_notify_inapp_false_excludes_badge_and_match_list(self):
        pers.create_alert(
            CLIENT_ID, label=None, filters={"city": "lahore"}, notify_inapp=False
        )
        _insert_listing("NO-INAPP-1")
        assert pers.unseen_match_count(CLIENT_ID) == 0
        assert pers.list_matches(CLIENT_ID) == []

    def test_listing_matches_alert_pure_function(self):
        listing = {
            "is_active": 1, "city": "lahore", "area_name": "DHA Phase 5",
            "property_type": "Apartment / Flat", "bedrooms": 2,
            "price": 75000, "title": "Furnished flat", "amenities_json": None,
            "details_json": None,
        }
        assert pers.listing_matches_alert(listing, {"city": "lahore"})
        assert not pers.listing_matches_alert(listing, {"city": "karachi"})
        assert pers.listing_matches_alert(listing, {"city": "lahore", "bedrooms": 2})
        assert not pers.listing_matches_alert(listing, {"city": "lahore", "bedrooms": 3})
        assert pers.listing_matches_alert(listing, {"city": "lahore", "price_max": 80000})
        assert not pers.listing_matches_alert(listing, {"city": "lahore", "price_max": 60000})
        assert pers.listing_matches_alert(listing, {"city": "lahore", "furnished": True})
        assert not pers.listing_matches_alert(listing, {"city": "lahore", "furnished": False})
        for title in ("Non furnished flat", "Flat, not furnished"):
            negative = {**listing, "title": title}
            assert pers.listing_matches_alert(negative, {"city": "lahore", "furnished": False})
            assert not pers.listing_matches_alert(negative, {"city": "lahore", "furnished": True})
        # Saying nothing about furniture is unknown, not unfurnished.
        unknown = {**listing, "title": "Flat"}
        assert pers.listing_matches_alert(unknown, {"city": "lahore"})
        assert not pers.listing_matches_alert(unknown, {"city": "lahore", "furnished": False})
        assert not pers.listing_matches_alert(unknown, {"city": "lahore", "furnished": True})
        # Inactive listing never matches.
        assert not pers.listing_matches_alert({**listing, "is_active": 0},
                                              {"city": "lahore"})


# ── Favorites / hidden / recent ──────────────────────────────────────────────


class TestFavorites:
    def test_add_and_list(self):
        _insert_listing("FAV-1")
        pers.add_favorite(CLIENT_ID, "FAV-1", note="must visit")
        favs = pers.list_favorites(CLIENT_ID)
        assert len(favs) == 1
        assert favs[0]["zameen_id"] == "FAV-1"
        assert favs[0]["note"] == "must visit"

    def test_remove_favorite(self):
        _insert_listing("FAV-2")
        pers.add_favorite(CLIENT_ID, "FAV-2")
        assert pers.remove_favorite(CLIENT_ID, "FAV-2") is True
        assert pers.list_favorites(CLIENT_ID) == []

    def test_dupe_favorite_is_idempotent(self):
        pers.add_favorite(CLIENT_ID, "FAV-3")
        pers.add_favorite(CLIENT_ID, "FAV-3")
        favs_ids = pers.get_favorite_zameen_ids(CLIENT_ID)
        assert favs_ids == {"FAV-3"}


class TestHidden:
    def test_add_and_get_set(self):
        pers.add_hidden(CLIENT_ID, "HIDE-1")
        pers.add_hidden(CLIENT_ID, "HIDE-2")
        assert pers.get_hidden_zameen_ids(CLIENT_ID) == {"HIDE-1", "HIDE-2"}

    def test_remove_hidden(self):
        pers.add_hidden(CLIENT_ID, "HIDE-3")
        assert pers.remove_hidden(CLIENT_ID, "HIDE-3") is True
        assert "HIDE-3" not in pers.get_hidden_zameen_ids(CLIENT_ID)


class TestRecentViews:
    def test_record_and_list(self):
        _insert_listing("VIEW-1")
        pers.record_view(CLIENT_ID, "VIEW-1")
        items = pers.list_recent_views(CLIENT_ID)
        assert len(items) == 1
        assert items[0]["zameen_id"] == "VIEW-1"

    def test_record_refreshes_timestamp(self):
        _insert_listing("VIEW-2")
        pers.record_view(CLIENT_ID, "VIEW-2")
        first = pers.list_recent_views(CLIENT_ID)[0]["viewed_at"]
        import time; time.sleep(0.01)
        pers.record_view(CLIENT_ID, "VIEW-2")
        second = pers.list_recent_views(CLIENT_ID)[0]["viewed_at"]
        assert second >= first


# ── VAPID ────────────────────────────────────────────────────────────────────


class TestVAPID:
    def test_key_is_persistent(self, tmp_path, monkeypatch):
        # Use a sandboxed VAPID dir so we don't trash the dev keypair.
        from app import personalization
        monkeypatch.setattr(personalization, "_VAPID_DIR", tmp_path)
        monkeypatch.setattr(personalization, "_VAPID_PRIVATE_PATH", tmp_path / "vapid_private.pem")
        monkeypatch.setattr(personalization, "_VAPID_PUBLIC_PATH", tmp_path / "vapid_public.txt")
        personalization._VAPID_CACHE.clear()
        first = personalization.vapid_public_key()
        personalization._VAPID_CACHE.clear()
        second = personalization.vapid_public_key()
        assert first == second
        assert len(first) > 40  # base64url'd uncompressed P-256 public key


# ── API surface ──────────────────────────────────────────────────────────────


class TestPersonalizationAPI:
    @pytest.mark.parametrize("endpoint", [
        "http://127.0.0.1/push", "https://127.0.0.1/push",
        "http://169.254.169.254/latest/meta-data/", "https://example.com/push",
        "https://fcm.googleapis.com.evil.test/push",
        "https://fcm.googleapis.com@evil.test/push",
        "https://evilpush.apple.com/push", "https://fcm.googleapis.com:8443/push",
        "https://evil.test\\x.push.apple.com/push",
        "https://fcm.googleapis.com/push#fragment",
    ])
    def test_push_rejects_untrusted_destinations(self, client, endpoint):
        res = client.post("/api/push/subscribe", headers={"X-Client-Id": CLIENT_ID}, json={
            "endpoint": endpoint, "keys": {"p256dh": "fake", "auth": "fake"},
        })
        assert res.status_code == 400
        assert pers.list_push_subscriptions(CLIENT_ID) == []

    @pytest.mark.parametrize("keys", [[], "invalid", 42])
    def test_push_rejects_invalid_key_container(self, client, keys):
        res = client.post("/api/push/subscribe", headers={"X-Client-Id": CLIENT_ID}, json={
            "endpoint": "https://fcm.googleapis.com/fcm/send/test", "keys": keys,
        })
        assert res.status_code == 400

    def test_touch_requires_client_id(self, client):
        res = client.post("/api/personalization/touch")
        assert res.status_code == 400

    def test_touch_returns_state(self, client):
        res = client.post("/api/personalization/touch",
                          headers={"X-Client-Id": CLIENT_ID})
        assert res.status_code == 200
        body = res.json()
        assert body["client_id"] == CLIENT_ID
        assert "vapid_public_key" in body

    def test_create_and_list_alert(self, client):
        headers = {"X-Client-Id": CLIENT_ID}
        client.post("/api/personalization/touch", headers=headers)
        res = client.post("/api/alerts", headers=headers, json={
            "label": "API alert",
            "filters": {"city": "lahore", "bedrooms": 2},
        })
        assert res.status_code == 200
        alert = res.json()
        assert alert["label"] == "API alert"

        res = client.get("/api/alerts", headers=headers)
        assert res.status_code == 200
        assert len(res.json()["alerts"]) == 1

    def test_alert_match_via_api(self, client):
        headers = {"X-Client-Id": CLIENT_ID}
        client.post("/api/alerts", headers=headers, json={
            "filters": {"city": "lahore", "bedrooms": 2},
        })
        _insert_listing("API-MATCH-1")
        res = client.get("/api/alerts/matches", headers=headers)
        assert res.status_code == 200
        body = res.json()
        assert len(body["matches"]) == 1
        assert body["matches"][0]["zameen_id"] == "API-MATCH-1"

    def test_favorite_lifecycle(self, client):
        headers = {"X-Client-Id": CLIENT_ID}
        _insert_listing("FAV-API-1")
        res = client.post("/api/favorites", headers=headers, json={"zameen_id": "FAV-API-1"})
        assert res.status_code == 200
        res = client.get("/api/favorites", headers=headers)
        assert res.status_code == 200
        assert res.json()["favorites"][0]["zameen_id"] == "FAV-API-1"
        res = client.delete("/api/favorites/FAV-API-1", headers=headers)
        assert res.status_code == 200
        assert client.get("/api/favorites", headers=headers).json()["favorites"] == []

    def test_hidden_lifecycle(self, client):
        headers = {"X-Client-Id": CLIENT_ID}
        client.post("/api/hidden", headers=headers, json={"zameen_id": "HIDDEN-API-1"})
        res = client.get("/api/hidden", headers=headers)
        assert res.json()["hidden"][0]["zameen_id"] == "HIDDEN-API-1"
        client.delete("/api/hidden/HIDDEN-API-1", headers=headers)
        assert client.get("/api/hidden", headers=headers).json()["hidden"] == []

    def test_recent_views_lifecycle(self, client):
        headers = {"X-Client-Id": CLIENT_ID}
        _insert_listing("RECENT-API-1")
        client.post("/api/recent-views", headers=headers, json={"zameen_id": "RECENT-API-1"})
        res = client.get("/api/recent-views", headers=headers)
        assert res.json()["recent_views"][0]["zameen_id"] == "RECENT-API-1"

    def test_vapid_key_endpoint(self, client):
        res = client.get("/api/push/vapid-key")
        assert res.status_code == 200
        assert res.json()["vapid_public_key"]

    def test_push_subscribe_requires_keys(self, client):
        headers = {"X-Client-Id": CLIENT_ID}
        res = client.post("/api/push/subscribe", headers=headers, json={"endpoint": "x"})
        assert res.status_code == 400

    def test_push_subscribe_then_unsubscribe(self, client):
        headers = {"X-Client-Id": CLIENT_ID}
        res = client.post("/api/push/subscribe", headers=headers, json={
            "endpoint": "https://fcm.googleapis.com/fcm/send/abc",
            "keys": {"p256dh": "fake-p256dh", "auth": "fake-auth"},
        })
        assert res.status_code == 200
        subs = pers.list_push_subscriptions(CLIENT_ID)
        assert len(subs) == 1
        res = client.post("/api/push/unsubscribe", headers=headers, json={
            "endpoint": "https://fcm.googleapis.com/fcm/send/abc",
        })
        assert res.status_code == 200
        assert pers.list_push_subscriptions(CLIENT_ID) == []

    def test_push_unsubscribe_cannot_remove_other_clients_endpoint(self, client):
        pers.save_push_subscription(
            CLIENT_ID,
            endpoint="https://fcm.googleapis.com/fcm/send/private",
            p256dh="fake-p256dh",
            auth="fake-auth",
        )
        res = client.post(
            "/api/push/unsubscribe",
            headers={"X-Client-Id": OTHER_CLIENT_ID},
            json={"endpoint": "https://fcm.googleapis.com/fcm/send/private"},
        )
        assert res.status_code == 200
        assert len(pers.list_push_subscriptions(CLIENT_ID)) == 1

    def test_alerts_run_cycle_endpoint_requires_admin_token(self, client, monkeypatch):
        headers = {"X-Client-Id": CLIENT_ID}
        client.post("/api/alerts", headers=headers, json={
            "filters": {"city": "lahore", "bedrooms": 2},
        })
        _insert_listing("CYCLE-1")
        res = client.post("/api/alerts/run-match-cycle")
        assert res.status_code == 503
        monkeypatch.setenv("ZAMEENRENTALS_ADMIN_TOKEN", "test-admin-token")
        assert client.post("/api/alerts/run-match-cycle").status_code == 401
        res = client.post(
            "/api/alerts/run-match-cycle",
            headers={"X-Admin-Token": "test-admin-token"},
        )
        assert res.status_code == 200
        # The real-time hook already recorded the match, so the cycle finds 0
        # *new* matches. That's correct behavior.
        body = res.json()
        assert "matches" in body
        assert "pruned" in body

    def test_invalid_client_id_rejected(self, client):
        res = client.post("/api/personalization/touch",
                          headers={"X-Client-Id": "no"})  # too short
        assert res.status_code == 400
