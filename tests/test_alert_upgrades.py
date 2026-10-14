"""Paid alert upgrades: daily charging, shortlist, priority check, and the
guarantee that free alerts behave exactly as before."""
from __future__ import annotations

import json
import sys
import types
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app import alert_upgrades as up
from app import credits
from app import personalization as pers
from app.database import _get_conn
from app.db_listings import upsert_listing

CLIENT = "paid-alerts-client-001"
OTHER = "free-alerts-client-002"


def utc(y, m, d, hh=0, mm=0):
    return datetime(y, m, d, hh, mm, tzinfo=timezone.utc)


# 2026-10-12 04:00 UTC is 09:00 in Karachi (UTC+5): the shortlist hour.
DAY1_MORNING = utc(2026, 10, 12, 4, 0)


@pytest.fixture(autouse=True)
def _schema(fresh_db, monkeypatch):
    # The historical priority experiment remains tested, but is not publicly offered.
    monkeypatch.setattr(up, "PRIORITY_AVAILABLE", True)
    pers.init_personalization_schema()
    credits.register_starter_request(CLIENT, "192.0.2.1")
    credits.register_starter_request(OTHER, "192.0.2.1")
    yield


@pytest.fixture
def no_ranking(monkeypatch):
    """Simulate the ai track's app.ranking not being installed."""
    monkeypatch.setitem(sys.modules, "app.ranking", None)


def _alert(client=CLIENT, **filters) -> int:
    filters = {"city": "lahore", "area": "Gulberg", **filters}
    return pers.create_alert(client, label=None, filters=filters)["id"]


_zid = [700000]


def _listing(price=60000, bedrooms=2, area="Gulberg", **card) -> dict:
    _zid[0] += 1
    zid = str(_zid[0])
    upsert_listing(
        zameen_id=zid, url=f"https://www.zameen.com/Property/t-{zid}-1-1.html",
        city="lahore", area_name=area, area_slug="Lahore_Gulberg",
        card_data={"title": f"Flat {zid}", "price": price, "bedrooms": bedrooms,
                   "bathrooms": 1, "area_size": "5 Marla",
                   "property_type": "Apartment / Flat", **card},
    )
    return dict(_get_conn().execute("SELECT * FROM listings WHERE zameen_id = ?", (zid,)).fetchone())


def _set_matched_at(alert_id: int, when: datetime):
    conn = _get_conn()
    conn.execute("UPDATE alert_matches SET matched_at = ? WHERE alert_id = ?",
                 (up._sqlite_utc(when), alert_id))
    conn.commit()


def _spends(client=CLIENT):
    return _get_conn().execute(
        "SELECT ref, delta, kind FROM credit_ledger WHERE client_id = ? AND kind IN ('spend', 'refund') ORDER BY id",
        (client,),
    ).fetchall()


def _drain(client, leave):
    while credits.balance(client) > leave:
        credits.spend(client, "instant_alerts_day", ref=credits.new_spend_ref("instant_alerts_day"))


# ── Karachi calendar day ─────────────────────────────────────────────────────


class TestKarachiDay:
    def test_day_turns_at_karachi_midnight_not_utc(self):
        assert up.karachi_day(utc(2026, 10, 11, 18, 59)) == "2026-10-11"
        assert up.karachi_day(utc(2026, 10, 11, 19, 0)) == "2026-10-12"

    def test_ref_format(self):
        assert up.day_ref(7, up.INSTANT, "2026-10-11") == "alertday:7:instant_alerts_day:2026-10-11"


# ── Switching on and off ─────────────────────────────────────────────────────


class TestSwitching:
    def test_switching_on_charges_today_immediately(self):
        aid = _alert()
        state = up.set_upgrade(CLIENT, aid, up.INSTANT, True, now=DAY1_MORNING)
        assert state["upgrades"][up.INSTANT]["enabled"] is True
        assert state["upgrades"][up.INSTANT]["paid_today"] is True
        assert credits.balance(CLIENT) == credits.STARTER_CREDITS - credits.COSTS[up.INSTANT]
        assert [r["ref"] for r in _spends()] == [f"alertday:{aid}:instant_alerts_day:2026-10-12"]

    def test_shortlist_off_and_on_before_delivery_charges_nothing(self):
        aid = _alert()
        up.set_upgrade(CLIENT, aid, up.SHORTLIST, True, now=DAY1_MORNING)
        up.set_upgrade(CLIENT, aid, up.SHORTLIST, False, now=DAY1_MORNING)
        up.set_upgrade(CLIENT, aid, up.SHORTLIST, True, now=DAY1_MORNING + timedelta(hours=1))
        assert len(_spends()) == 0
        assert credits.balance(CLIENT) == credits.STARTER_CREDITS

    def test_switching_off_stops_future_charges(self):
        aid = _alert()
        up.set_upgrade(CLIENT, aid, up.INSTANT, True, now=DAY1_MORNING)
        up.set_upgrade(CLIENT, aid, up.INSTANT, False, now=DAY1_MORNING)
        for d in range(1, 4):
            up.run_daily_jobs(now=DAY1_MORNING + timedelta(days=d), dispatch=False)
        assert len(_spends()) == 1

    def test_insufficient_credits_raises_and_leaves_it_off(self):
        aid = _alert()
        _drain(CLIENT, 0)
        with pytest.raises(credits.InsufficientCredits):
            up.set_upgrade(CLIENT, aid, up.SHORTLIST, True, now=DAY1_MORNING)
        assert up.upgrade_state(CLIENT, aid)["upgrades"][up.SHORTLIST]["enabled"] is False
        assert credits.balance(CLIENT) == 0

    def test_paused_alert_cannot_be_upgraded(self):
        aid = _alert()
        pers.update_alert(CLIENT, aid, paused=True)
        with pytest.raises(ValueError):
            up.set_upgrade(CLIENT, aid, up.INSTANT, True, now=DAY1_MORNING)

    def test_other_clients_alert_is_not_found(self):
        aid = _alert(client=OTHER)
        with pytest.raises(LookupError):
            up.set_upgrade(CLIENT, aid, up.INSTANT, True)

    def test_deleting_alert_removes_upgrade_state(self):
        aid = _alert()
        up.set_upgrade(CLIENT, aid, up.INSTANT, True, now=DAY1_MORNING)
        assert pers.delete_alert(CLIENT, aid)
        assert _get_conn().execute("SELECT COUNT(*) FROM alert_upgrades").fetchone()[0] == 0


# ── Daily charging ───────────────────────────────────────────────────────────


class TestDailyCharging:
    def test_repeated_cycles_charge_once_per_day(self):
        aid = _alert()
        up.set_upgrade(CLIENT, aid, up.INSTANT, True, now=DAY1_MORNING)
        for minutes in range(0, 600, 7):  # a busy crawler flushes often
            up.run_daily_jobs(now=DAY1_MORNING + timedelta(minutes=minutes), dispatch=False)
        assert len(_spends()) == 1
        day2 = DAY1_MORNING + timedelta(days=1)
        for minutes in range(0, 120, 5):
            up.run_daily_jobs(now=day2 + timedelta(minutes=minutes), dispatch=False)
        refs = [r["ref"] for r in _spends()]
        assert refs == [
            f"alertday:{aid}:instant_alerts_day:2026-10-12",
            f"alertday:{aid}:instant_alerts_day:2026-10-13",
        ]

    def test_day_boundary_follows_karachi_time(self):
        aid = _alert()
        # Switched on at 23:30 Karachi on the 11th (18:30 UTC).
        up.set_upgrade(CLIENT, aid, up.INSTANT, True, now=utc(2026, 10, 11, 18, 30))
        # 23:59 Karachi: still the 11th, nothing new to charge.
        up.run_daily_jobs(now=utc(2026, 10, 11, 18, 59), dispatch=False)
        assert len(_spends()) == 1
        # 00:01 Karachi on the 12th, while UTC is still the 11th: a new day.
        up.run_daily_jobs(now=utc(2026, 10, 11, 19, 1), dispatch=False)
        refs = [r["ref"] for r in _spends()]
        assert refs[-1] == f"alertday:{aid}:instant_alerts_day:2026-10-12"
        assert len(refs) == 2

    def test_auto_off_when_balance_runs_out_and_never_negative(self):
        aid = _alert()
        up.set_upgrade(CLIENT, aid, up.INSTANT, True, now=DAY1_MORNING)
        _drain(CLIENT, 0)
        summary = up.run_daily_jobs(now=DAY1_MORNING + timedelta(days=1), dispatch=False)
        assert summary["switched_off"] == 1
        assert credits.balance(CLIENT) == 0
        state = up.get_state(CLIENT, now=DAY1_MORNING + timedelta(days=1))
        assert state["alerts"][str(aid)][up.INSTANT]["enabled"] is False
        assert state["alerts"][str(aid)][up.INSTANT]["disabled_reason"] == "balance"
        notices = state["notices"]
        assert len(notices) == 1 and notices[0]["kind"] == "balance_off"
        assert notices[0]["upgrade"] == up.INSTANT
        # Later cycles neither charge nor duplicate the notice.
        for d in range(2, 5):
            up.run_daily_jobs(now=DAY1_MORNING + timedelta(days=d), dispatch=False)
        assert len(up.list_notices(CLIENT)) == 1
        assert credits.balance(CLIENT) == 0
        assert up.dismiss_notices(CLIENT) == 1
        assert up.list_notices(CLIENT) == []

    def test_paused_alert_is_not_charged(self):
        aid = _alert()
        up.set_upgrade(CLIENT, aid, up.INSTANT, True, now=DAY1_MORNING)
        pers.update_alert(CLIENT, aid, paused=True)
        up.run_daily_jobs(now=DAY1_MORNING + timedelta(days=1), dispatch=False)
        assert len(_spends()) == 1

    def test_days_covered(self):
        a1, a2 = _alert(), _alert(bedrooms=3)
        up.set_upgrade(CLIENT, a1, up.INSTANT, True, now=DAY1_MORNING)
        up.set_upgrade(CLIENT, a2, up.SHORTLIST, True, now=DAY1_MORNING)
        state = up.get_state(CLIENT, now=DAY1_MORNING)
        assert state["daily_cost"] == 2
        assert state["balance"] == 9
        assert state["days_covered"] == 4


# ── Daily shortlist ──────────────────────────────────────────────────────────


class TestShortlist:
    def test_not_built_before_shortlist_hour(self, no_ranking):
        aid = _alert()
        _listing()
        _set_matched_at(aid, DAY1_MORNING - timedelta(hours=2))
        up.set_upgrade(CLIENT, aid, up.SHORTLIST, True, now=DAY1_MORNING - timedelta(hours=3))
        summary = up.run_daily_jobs(now=DAY1_MORNING - timedelta(minutes=1), dispatch=False)
        assert summary["shortlists"] == 0
        summary = up.run_daily_jobs(now=DAY1_MORNING, dispatch=False)
        assert summary["shortlists"] == 1

    def test_no_charge_on_days_without_matches(self, no_ranking):
        aid = _alert()
        # Day 1: enabling an empty search never reserves or consumes credits.
        up.set_upgrade(CLIENT, aid, up.SHORTLIST, True, now=DAY1_MORNING - timedelta(hours=1))
        assert credits.balance(CLIENT) == 10
        s = up.run_daily_jobs(now=DAY1_MORNING, dispatch=False)
        assert s["empty"] == 1
        assert credits.balance(CLIENT) == credits.STARTER_CREDITS
        # Day 2: still nothing new -> not charged.
        up.run_daily_jobs(now=DAY1_MORNING + timedelta(days=1), dispatch=False)
        assert credits.balance(CLIENT) == credits.STARTER_CREDITS
        # Day 3: matches arrive -> charged once, however many cycles run.
        _listing()
        day3 = DAY1_MORNING + timedelta(days=2)
        _set_matched_at(aid, day3 - timedelta(hours=3))
        for minutes in range(0, 60, 5):
            up.run_daily_jobs(now=day3 + timedelta(minutes=minutes), dispatch=False)
        assert credits.balance(CLIENT) == credits.STARTER_CREDITS - credits.COSTS[up.SHORTLIST]
        shortlists = up.list_shortlists(CLIENT, aid)
        assert [s["day"] for s in shortlists] == ["2026-10-14"]
        assert len(shortlists[0]["items"]) == 1
        # Re-enabling on a day settled as empty costs nothing that day.
        up.set_upgrade(CLIENT, aid, up.SHORTLIST, False, now=day3)
        up.set_upgrade(CLIENT, aid, up.SHORTLIST, True, now=day3)
        assert credits.balance(CLIENT) == credits.STARTER_CREDITS - credits.COSTS[up.SHORTLIST]

    def test_only_last_24_hours_and_not_hidden(self, no_ranking):
        aid = _alert()
        old, fresh, hidden = _listing(), _listing(), _listing()
        conn = _get_conn()
        conn.execute("UPDATE alert_matches SET matched_at = ? WHERE listing_id = ?",
                     (up._sqlite_utc(DAY1_MORNING - timedelta(hours=30)), old["id"]))
        for lst in (fresh, hidden):
            conn.execute("UPDATE alert_matches SET matched_at = ? WHERE listing_id = ?",
                         (up._sqlite_utc(DAY1_MORNING - timedelta(hours=2)), lst["id"]))
        conn.commit()
        pers.add_hidden(CLIENT, hidden["zameen_id"])
        up.set_upgrade(CLIENT, aid, up.SHORTLIST, True, now=DAY1_MORNING)
        up.run_daily_jobs(now=DAY1_MORNING, dispatch=False)
        items = up.list_shortlists(CLIENT, aid)[0]["items"]
        assert [i["zameen_id"] for i in items] == [fresh["zameen_id"]]

    def test_unpaid_day_switches_off_then_reenable_delivers(self, no_ranking):
        aid = _alert()
        up.set_upgrade(CLIENT, aid, up.SHORTLIST, True, now=DAY1_MORNING - timedelta(days=1))
        _listing()
        day2 = DAY1_MORNING
        _set_matched_at(aid, day2 - timedelta(hours=1))
        _drain(CLIENT, 0)
        s = up.run_daily_jobs(now=day2, dispatch=False)
        assert s["switched_off"] == 1
        assert credits.balance(CLIENT) == 0
        assert up.list_shortlists(CLIENT, aid) == []
        credits.grant(CLIENT, 20, kind="purchase", ref="payment:test-1")
        up.set_upgrade(CLIENT, aid, up.SHORTLIST, True, now=day2)
        up.run_daily_jobs(now=day2 + timedelta(minutes=5), dispatch=False)
        assert len(up.list_shortlists(CLIENT, aid)) == 1
        assert credits.balance(CLIENT) == 20 - credits.COSTS[up.SHORTLIST]

    def test_push_sent_when_subscribed(self, no_ranking, monkeypatch):
        aid = _alert()
        pers.save_push_subscription(CLIENT, endpoint="https://fcm.googleapis.com/fcm/send/abc",
                                    p256dh="k", auth="a")
        sent = []
        monkeypatch.setattr(pers, "send_push", lambda sub, payload, **kw: sent.append(payload) or True)
        _listing()
        _set_matched_at(aid, DAY1_MORNING - timedelta(hours=1))
        up.set_upgrade(CLIENT, aid, up.SHORTLIST, True, now=DAY1_MORNING)
        summary = up.run_daily_jobs(now=DAY1_MORNING)
        assert summary["pushed"] == 1
        assert sent[0]["type"] == "alert_shortlist"
        assert sent[0]["url"] == f"/?alerts=open&alert_id={aid}&shortlist=1"
        up.run_daily_jobs(now=DAY1_MORNING + timedelta(minutes=10))
        assert len(sent) == 1


# ── Ranking ──────────────────────────────────────────────────────────────────


def _cand(zid, price, day, lid):
    return {"zameen_id": zid, "price": price, "first_seen_at": f"{day} 10:00:00",
            "listing_id": lid, "title": zid}


class TestRanking:
    def test_fallback_when_ranking_module_missing(self, no_ranking):
        filters = {"price_max": 100000}
        listings = [
            _cand("old-cheap", 40000, "2026-10-10", 1),
            _cand("new-pricey", 95000, "2026-10-11", 2),
            _cand("new-cheap", 50000, "2026-10-11", 3),
            _cand("new-noprice", None, "2026-10-11", 4),
        ]
        items, ranked_by = up.rank_matches(filters, listings, limit=5)
        assert ranked_by == "fallback"
        assert [i["zameen_id"] for i in items] == ["new-cheap", "new-pricey", "new-noprice", "old-cheap"]
        assert items[0]["reason"] == "PKR 50,000 a month, PKR 50,000 under your budget."
        assert all(i["trade_off"] is None for i in items)

    def test_fallback_is_deterministic_and_limited(self, no_ranking):
        listings = [_cand(f"z{i}", 30000 + i * 1000, "2026-10-11", i) for i in range(10)]
        first, _ = up.rank_matches({}, listings, limit=5)
        second, _ = up.rank_matches({}, list(reversed(listings)), limit=5)
        assert first == second and len(first) == 5

    def test_fallback_price_fit_with_range(self, no_ranking):
        filters = {"price_min": 40000, "price_max": 60000}
        listings = [_cand("edge", 59000, "2026-10-11", 1), _cand("mid", 51000, "2026-10-11", 2)]
        items, _ = up.rank_matches(filters, listings)
        assert [i["zameen_id"] for i in items] == ["mid", "edge"]

    def test_uses_ranking_module_when_present(self, monkeypatch):
        calls = {}

        def rank_listings(criteria, listings, brief=None, limit=10):
            calls.update(criteria=criteria, n=len(listings), brief=brief, limit=limit)
            return [
                {"zameen_id": "b", "reason": "Closest to the park", "trade_off": "Older building"},
                {"zameen_id": "unknown", "reason": "x", "trade_off": None},
                {"zameen_id": "a", "reason": "Cheapest", "trade_off": ""},
            ]

        monkeypatch.setitem(sys.modules, "app.ranking", types.SimpleNamespace(rank_listings=rank_listings))
        listings = [_cand("a", 40000, "2026-10-11", 1), _cand("b", 50000, "2026-10-11", 2)]
        items, ranked_by = up.rank_matches({"city": "lahore"}, listings, limit=5)
        assert ranked_by == "ranking"
        assert calls == {"criteria": {"city": "lahore"}, "n": 2, "brief": None, "limit": 5}
        assert [(i["zameen_id"], i["reason"], i["trade_off"]) for i in items] == [
            ("b", "Closest to the park", "Older building"), ("a", "Cheapest", None),
        ]

    def test_falls_back_when_ranking_raises(self, monkeypatch):
        def boom(*a, **k):
            raise RuntimeError("model down")

        monkeypatch.setitem(sys.modules, "app.ranking", types.SimpleNamespace(rank_listings=boom))
        items, ranked_by = up.rank_matches({}, [_cand("a", 1, "2026-10-11", 1)])
        assert ranked_by == "fallback" and items[0]["zameen_id"] == "a"

    def test_slow_ranking_times_out_to_fallback(self, monkeypatch):
        import threading
        release = threading.Event()

        def slow(*a, **k):
            release.wait(5)
            return [{"zameen_id": "a", "reason": "late", "trade_off": ""}]

        monkeypatch.setitem(sys.modules, "app.ranking", types.SimpleNamespace(rank_listings=slow))
        monkeypatch.setattr(up, "RANK_CALL_TIMEOUT_SECONDS", 0.05)
        try:
            items, ranked_by = up.rank_matches({}, [_cand("a", 1, "2026-10-11", 1)])
        finally:
            release.set()
        assert ranked_by == "fallback" and items[0]["reason"] != "late"

    def test_spent_run_budget_skips_ranking(self, monkeypatch):
        import time
        called = []
        monkeypatch.setitem(sys.modules, "app.ranking",
                            types.SimpleNamespace(rank_listings=lambda *a, **k: called.append(1) or []))
        monkeypatch.setattr(up, "_rank_deadline", time.monotonic() - 1)
        _, ranked_by = up.rank_matches({}, [_cand("a", 1, "2026-10-11", 1)])
        assert ranked_by == "fallback" and called == []


# ── Priority check ───────────────────────────────────────────────────────────

CARD_HTML = """
<li role="article">
  <h2><a href="/Property/lahore-gulberg-flat-{zid}-1-1.html">Flat in Gulberg</a></h2>
  <span aria-label="Price">PKR 55 Thousand</span>
  <span aria-label="Beds">2</span>
  <div aria-label="Location">Gulberg, Lahore</div>
</li>
"""


class TestPriorityCheck:
    def test_only_charged_unpaused_instant_alerts_are_checked(self):
        paid = _alert(bedrooms=2, price_max=60000)
        _alert(bedrooms=3)  # free alert
        paused = _alert(bedrooms=1)
        up.set_upgrade(CLIENT, paid, up.INSTANT, True, now=DAY1_MORNING)
        up.set_upgrade(CLIENT, paused, up.INSTANT, True, now=DAY1_MORNING)
        pers.update_alert(CLIENT, paused, paused=True)
        searches = up.priority_searches(now=DAY1_MORNING)
        assert [s["alert_ids"] for s in searches] == [[paid]]
        url = searches[0]["url"]
        assert url.startswith("https://www.zameen.com/Rentals/")
        assert "sort=date_desc" in url and "beds_in=2" in url and "price_max=60000" in url
        # Not yet charged for the next Karachi day -> not checked then.
        assert up.priority_searches(now=DAY1_MORNING + timedelta(days=1)) == []

    def test_identical_searches_are_fetched_once(self):
        a1, a2 = _alert(bedrooms=2), _alert(client=OTHER, bedrooms=2)
        up.set_upgrade(CLIENT, a1, up.INSTANT, True, now=DAY1_MORNING)
        up.set_upgrade(OTHER, a2, up.INSTANT, True, now=DAY1_MORNING)
        searches = up.priority_searches(now=DAY1_MORNING)
        assert len(searches) == 1 and sorted(searches[0]["alert_ids"]) == sorted([a1, a2])

    @pytest.mark.asyncio
    async def test_stores_cards_and_records_matches(self, monkeypatch):
        paid = _alert(bedrooms=2)
        free = _alert(client=OTHER, bedrooms=2)
        up.set_upgrade(CLIENT, paid, up.INSTANT, True)
        fetched = []

        async def fake_fetch(url, client, headers):
            fetched.append(url)
            return CARD_HTML.format(zid=880001)

        monkeypatch.setattr("app.crawler_worker._fetch", fake_fetch)
        summary = await up.check_priority_searches(None, {}, sleep=_no_sleep)
        assert summary == {"searches": 1, "pages": 1, "new": 1, "updated": 0}
        assert len(fetched) == 1
        row = _get_conn().execute("SELECT area_name FROM listings WHERE zameen_id = '880001'").fetchone()
        assert row["area_name"] == "Gulberg"
        # The insert hook matched both the paid alert and the free one.
        matched = {r["alert_id"] for r in _get_conn().execute("SELECT alert_id FROM alert_matches")}
        assert matched == {paid, free}
        # A second tick finds nothing new.
        summary = await up.check_priority_searches(None, {}, sleep=_no_sleep)
        assert summary["new"] == 0


async def _no_sleep(_):
    return None


# ── Free alerts are unchanged ────────────────────────────────────────────────


def _free_alert_scenario(monkeypatch, *, with_paid: bool):
    """Same listings and alerts; optionally a paid client alongside. Returns
    what the free client sees: matches, push payloads, match-cycle summary."""
    credits.register_starter_request(CLIENT, "192.0.2.1")
    credits.register_starter_request(OTHER, "192.0.2.1")
    pushes = []
    monkeypatch.setattr(pers, "send_push",
                        lambda sub, payload, **kw: pushes.append(payload) or True)
    monkeypatch.setitem(sys.modules, "app.ranking", None)
    free = _alert(client=OTHER, bedrooms=2)
    pers.save_push_subscription(OTHER, endpoint="https://fcm.googleapis.com/fcm/send/free",
                                p256dh="k", auth="a")
    if with_paid:
        paid = _alert(bedrooms=2)
        pers.save_push_subscription(CLIENT, endpoint="https://fcm.googleapis.com/fcm/send/paid",
                                    p256dh="k", auth="a")
        up.set_upgrade(CLIENT, paid, up.INSTANT, True)
        up.set_upgrade(CLIENT, paid, up.SHORTLIST, True)
    for price in (50000, 55000, 70000):
        _listing(price=price)
    summary = pers.run_match_cycle(dispatch=True)
    # Noon in Karachi today: past the shortlist hour, so the paid shortlist runs too.
    up.run_daily_jobs(now=up.karachi_now().replace(hour=12, minute=0))
    free_pushes = [p for p in pushes if p["alert_id"] == free]
    matches = [
        (m["zameen_id"], m["title"], m["price"])
        for m in pers.list_matches(OTHER)
    ]
    paid_ran = None
    if with_paid:
        paid_ran = {
            "shortlists": len(up.list_shortlists(CLIENT, paid, mark_seen=False)),
            "spent": credits.STARTER_CREDITS - credits.balance(CLIENT),
            "paid_pushes": sum(1 for p in pushes if p["alert_id"] == paid),
        }
    return paid_ran, {
        "alerts": [{k: v for k, v in a.items() if k not in ("id", "created_at", "last_matched_at",
                                                            "last_seen_id", "last_match_at")}
                   for a in pers.list_alerts(OTHER)],
        "matches": sorted(matches),
        "pushes": [{k: v for k, v in p.items() if k not in ("alert_id", "tag", "url")} for p in free_pushes],
        "summary_keys": sorted(summary),
        "unseen": pers.unseen_match_count(OTHER),
        "balance": credits.balance(OTHER),
    }


class TestFreeAlertsUnchanged:
    def test_free_client_sees_the_same_with_and_without_paid_alerts(self, monkeypatch):
        _zid[0] = 750000
        _, before = _free_alert_scenario(monkeypatch, with_paid=False)
        # Fresh database, same scenario, now with a paying client alongside.
        import app.database as db_mod
        db_mod.close_db()
        for suffix in ("", "-wal", "-shm"):
            type(db_mod._DB_PATH)(str(db_mod._DB_PATH) + suffix).unlink(missing_ok=True)
        db_mod.init_db()
        pers.init_personalization_schema()
        _zid[0] = 750000
        paid_ran, after = _free_alert_scenario(monkeypatch, with_paid=True)
        assert before == after
        # The paid side really ran next to it: charged, shortlist built, pushed.
        assert paid_ran["shortlists"] == 1
        assert paid_ran["spent"] >= credits.COSTS[up.INSTANT] + credits.COSTS[up.SHORTLIST]
        assert paid_ran["paid_pushes"] >= 2  # its own match push + the shortlist push
        assert len(before["matches"]) == 3
        assert before["balance"] == credits.STARTER_CREDITS  # free alerts never spend

    def test_match_cycle_summary_shape_is_unchanged(self):
        assert sorted(pers.run_match_cycle(dispatch=True)) == [
            "failed", "matches", "no_subscription", "pruned", "sent", "skipped", "stale_pruned",
        ]

    def test_free_alerts_flush_before_paid_jobs(self, monkeypatch):
        from app import crawler

        order = []
        monkeypatch.setattr(crawler, "run_match_cycle", lambda dispatch: order.append("free") or {})
        monkeypatch.setattr(crawler.alert_upgrades, "run_daily_jobs", lambda: order.append("paid") or {})
        crawler.flush_alert_notifications("test")
        assert order == ["free", "paid"]

    def test_paid_job_failure_does_not_break_free_flush(self, monkeypatch):
        from app import crawler

        monkeypatch.setattr(crawler, "run_match_cycle", lambda dispatch: {"matches": 2})

        def boom():
            raise RuntimeError("paid broke")

        monkeypatch.setattr(crawler.alert_upgrades, "run_daily_jobs", boom)
        assert crawler.flush_alert_notifications("test") == {"matches": 2}

    @pytest.mark.asyncio
    async def test_priority_check_runs_after_city_feeds_and_free_flush(self, monkeypatch):
        from app import crawler

        order = []

        async def fake_city(city, client, headers, pages):
            order.append(f"city:{city}")
            return 0, 0, 0, 1

        async def fake_priority(client, headers):
            order.append("priority")
            return {"searches": 0, "pages": 0, "new": 0, "updated": 0}

        monkeypatch.setattr(crawler, "crawl_city_latest_cards", fake_city)
        monkeypatch.setattr(crawler, "flush_alert_notifications", lambda ctx: order.append(f"flush:{ctx}"))
        monkeypatch.setattr(crawler.alert_upgrades, "check_priority_searches", fake_priority)
        await crawler.refresh_latest_city_feeds(None, {})
        assert order[-2:] == ["flush:latest", "priority"]
        assert all(o.startswith("city:") for o in order[:-2])


# ── API ──────────────────────────────────────────────────────────────────────


@pytest.fixture
def api():
    from app import app
    return TestClient(app)


H = {"X-Client-Id": CLIENT}


class TestApi:
    def test_state_and_toggle(self, api):
        aid = _alert()
        state = api.get("/api/alerts/upgrades", headers=H).json()
        assert state["balance"] == credits.STARTER_CREDITS
        assert state["costs"] == {up.INSTANT: 1, up.SHORTLIST: 1}
        assert state["days_covered"] is None
        assert state["alerts"][str(aid)][up.INSTANT]["enabled"] is False

        r = api.post(f"/api/alerts/{aid}/upgrades/{up.SHORTLIST}", headers=H, json={"enabled": True})
        assert r.status_code == 200
        body = r.json()
        assert body["upgrades"][up.SHORTLIST]["enabled"] is True
        assert body["balance"] == 10 and body["daily_cost"] == 1 and body["days_covered"] == 10

        r = api.post(f"/api/alerts/{aid}/upgrades/{up.SHORTLIST}", headers=H, json={"enabled": False})
        assert r.json()["upgrades"][up.SHORTLIST]["enabled"] is False
        assert r.json()["balance"] == 10

    def test_402_with_contract_detail(self, api):
        aid = _alert()
        _drain(CLIENT, 0)
        r = api.post(f"/api/alerts/{aid}/upgrades/{up.SHORTLIST}", headers=H, json={"enabled": True})
        assert r.status_code == 402
        assert r.json()["detail"] == {
            "code": "insufficient_credits", "action": up.SHORTLIST, "balance": 0, "cost": 1,
        }

    def test_errors(self, api):
        aid = _alert()
        assert api.post(f"/api/alerts/{aid}/upgrades/nope", headers=H, json={"enabled": True}).status_code == 404
        assert api.post(f"/api/alerts/999/upgrades/{up.INSTANT}", headers=H, json={"enabled": True}).status_code == 404
        assert api.post(f"/api/alerts/{aid}/upgrades/{up.INSTANT}", headers=H, json={"enabled": "yes"}).status_code == 400
        assert api.post(f"/api/alerts/{aid}/upgrades/{up.INSTANT}", json={"enabled": True}).status_code == 400
        other = _alert(client=OTHER)
        assert api.get(f"/api/alerts/{other}/shortlists", headers=H).status_code == 404

    def test_shortlists_and_notices(self, api, no_ranking):
        aid = _alert()
        _listing()
        up.set_upgrade(CLIENT, aid, up.SHORTLIST, True, now=DAY1_MORNING)
        _set_matched_at(aid, DAY1_MORNING - timedelta(hours=1))
        up.run_daily_jobs(now=DAY1_MORNING, dispatch=False)
        state = api.get("/api/alerts/upgrades", headers=H).json()
        assert state["alerts"][str(aid)]["latest_shortlist"]["seen"] is False
        data = api.get(f"/api/alerts/{aid}/shortlists", headers=H).json()
        assert len(data["shortlists"]) == 1 and data["shortlists"][0]["items"][0]["reason"]
        state = api.get("/api/alerts/upgrades", headers=H).json()
        assert state["alerts"][str(aid)]["latest_shortlist"]["seen"] is True
        assert api.post("/api/alerts/upgrades/notices/seen", headers=H, json={}).json() == {"updated": 0}


def test_shortlist_does_not_rebill_matches_in_overlapping_daily_windows(no_ranking):
    aid = _alert()
    first = DAY1_MORNING + timedelta(hours=2)
    _listing()
    _set_matched_at(aid, first - timedelta(minutes=30))
    up.set_upgrade(CLIENT, aid, up.SHORTLIST, True, now=first)
    assert up.run_daily_jobs(now=first, dispatch=False)['shortlists'] == 1
    before = credits.balance(CLIENT)
    next_run = DAY1_MORNING + timedelta(days=1, minutes=5)
    assert up.run_daily_jobs(now=next_run, dispatch=False)['empty'] == 1
    assert credits.balance(CLIENT) == before
    assert len(up.list_shortlists(CLIENT, aid)) == 1


def test_shortlist_defers_future_matches_until_the_next_window(no_ranking):
    aid = _alert()
    first = DAY1_MORNING + timedelta(hours=2)
    _listing()
    _set_matched_at(aid, first + timedelta(minutes=1))
    up.set_upgrade(CLIENT, aid, up.SHORTLIST, True, now=first)
    assert up.run_daily_jobs(now=first, dispatch=False)['empty'] == 1
    assert credits.balance(CLIENT) == 10
    assert up.run_daily_jobs(now=DAY1_MORNING + timedelta(days=1), dispatch=False)['shortlists'] == 1
    assert credits.balance(CLIENT) == 9


def test_shortlist_keeps_new_arrivals_in_the_same_second(no_ranking):
    aid = _alert()
    first = DAY1_MORNING + timedelta(hours=2)
    old = _listing()
    _set_matched_at(aid, first)
    up.set_upgrade(CLIENT, aid, up.SHORTLIST, True, now=first)
    up.run_daily_jobs(now=first, dispatch=False)
    new = _listing()
    conn = _get_conn()
    with conn:
        conn.execute('UPDATE alert_matches SET matched_at=? WHERE listing_id=?',
                     (up._sqlite_utc(first), new['id']))
    assert up.run_daily_jobs(now=DAY1_MORNING + timedelta(days=1), dispatch=False)['shortlists'] == 1
    rows = up.list_shortlists(CLIENT, aid)
    assert rows[0]['items'][0]['zameen_id'] == new['zameen_id']
    assert rows[1]['items'][0]['zameen_id'] == old['zameen_id']
    assert credits.balance(CLIENT) == 8


def test_failed_shortlist_storage_returns_credit_and_retry_charges_once(no_ranking):
    aid = _alert()
    _listing()
    _set_matched_at(aid, DAY1_MORNING - timedelta(hours=1))
    up.set_upgrade(CLIENT, aid, up.SHORTLIST, True, now=DAY1_MORNING)
    conn = _get_conn()
    with conn:
        conn.execute("CREATE TRIGGER fail_shortlist BEFORE INSERT ON alert_shortlists WHEN NEW.status='delivered' BEGIN SELECT RAISE(ABORT, 'storage failed'); END")
    assert up.run_daily_jobs(now=DAY1_MORNING, dispatch=False)['shortlists'] == 0
    assert credits.balance(CLIENT) == 10
    with conn:
        conn.execute('DROP TRIGGER fail_shortlist')
    assert up.run_daily_jobs(now=DAY1_MORNING, dispatch=False)['shortlists'] == 1
    assert credits.balance(CLIENT) == 9
    assert up.upgrade_state(CLIENT, aid, now=DAY1_MORNING)['upgrades'][up.SHORTLIST]['paid_today'] is True
    up.run_daily_jobs(now=DAY1_MORNING, dispatch=False)
    assert credits.balance(CLIENT) == 9


def test_shortlist_resumes_an_interrupted_retry_without_another_charge(no_ranking):
    aid = _alert()
    _listing()
    _set_matched_at(aid, DAY1_MORNING - timedelta(hours=1))
    up.set_upgrade(CLIENT, aid, up.SHORTLIST, True, now=DAY1_MORNING)
    ref = up.day_ref(aid, up.SHORTLIST, up.karachi_day(DAY1_MORNING))
    credits.spend(CLIENT, up.SHORTLIST, ref=ref)
    credits.refund(ref)
    credits.spend(CLIENT, up.SHORTLIST, ref=ref+':retry1')
    assert up.run_daily_jobs(now=DAY1_MORNING, dispatch=False)['shortlists'] == 1
    assert credits.balance(CLIENT) == 9


def test_empty_shortlist_returns_interrupted_retry_charge(no_ranking):
    aid=_alert()
    up.set_upgrade(CLIENT, aid, up.SHORTLIST, True, now=DAY1_MORNING)
    ref=up.day_ref(aid,up.SHORTLIST,up.karachi_day(DAY1_MORNING))
    credits.spend(CLIENT,up.SHORTLIST,ref=ref)
    credits.refund(ref)
    credits.spend(CLIENT,up.SHORTLIST,ref=ref+':retry1')
    assert up.run_daily_jobs(now=DAY1_MORNING,dispatch=False)['empty']==1
    assert credits.balance(CLIENT)==10


def test_shortlist_keeps_late_committed_earlier_timestamp(no_ranking):
    aid=_alert()
    first=DAY1_MORNING+timedelta(hours=2)
    _listing()
    _set_matched_at(aid,first-timedelta(minutes=2))
    up.set_upgrade(CLIENT,aid,up.SHORTLIST,True,now=first)
    up.run_daily_jobs(now=first,dispatch=False)
    new=_listing()
    conn=_get_conn()
    with conn:
        conn.execute('UPDATE alert_matches SET matched_at=? WHERE listing_id=?',
                     (up._sqlite_utc(first-timedelta(minutes=1)),new['id']))
    assert up.run_daily_jobs(now=DAY1_MORNING+timedelta(days=1),dispatch=False)['shortlists']==1
    assert up.list_shortlists(CLIENT,aid)[0]['items'][0]['zameen_id']==new['zameen_id']


def test_credit_registration_failure_does_not_block_stopping_or_viewing(api,no_ranking,monkeypatch):
    aid=_alert()
    _listing()
    _set_matched_at(aid,DAY1_MORNING-timedelta(hours=1))
    up.set_upgrade(CLIENT,aid,up.SHORTLIST,True,now=DAY1_MORNING)
    up.run_daily_jobs(now=DAY1_MORNING,dispatch=False)
    def fail(*args):raise RuntimeError('starter registration unavailable')
    monkeypatch.setattr(credits,'register_starter_request',fail)
    h={'X-Client-Id':CLIENT}
    response=api.post(f'/api/alerts/{aid}/upgrades/{up.SHORTLIST}',headers=h,json={'enabled':False})
    assert response.status_code==200
    assert response.json()['upgrades'][up.SHORTLIST]['enabled'] is False
    response=api.get(f'/api/alerts/{aid}/shortlists',headers=h)
    assert response.status_code==200 and len(response.json()['shortlists'])==1
    assert api.post('/api/alerts/upgrades/notices/seen',headers=h,json={}).status_code==200
