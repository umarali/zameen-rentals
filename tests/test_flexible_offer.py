"""Observable pricing and delivery behavior for the public credit offer."""
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from app import app, credits, alert_upgrades as upgrades, personalization as pers
from app.database import _get_conn

CLIENT = "flexible-offer-client"
HEADERS = {"X-Client-Id": CLIENT}
NOW = datetime(2026, 10, 14, 5, tzinfo=timezone.utc)


def test_one_pack_and_equal_costs_share_one_balance(fresh_db):
    with TestClient(app) as client:
        response = client.get("/api/credits", headers=HEADERS).json()
        assert response["packs"] == [{"id": "standard", "credits": 50, "price_pkr": 500}]
        assert response["balance"] == 10
        for action in ("tailored_list", "search_report", "daily_shortlist_day"):
            assert response["costs"][action] == 1
            credits.spend(CLIENT, action, ref=f"offer:{action}")
        assert client.get("/api/credits", headers=HEADERS).json()["balance"] == 7


def test_priority_is_not_offered_and_legacy_enabled_rows_cannot_charge(fresh_db):
    with TestClient(app) as client:
        aid = pers.create_alert(CLIENT, label="Home", filters={"city": "lahore"})["id"]
        before = client.get("/api/credits", headers=HEADERS).json()["balance"]
        response = client.post(f"/api/alerts/{aid}/upgrades/{upgrades.INSTANT}",
                               headers=HEADERS, json={"enabled": True})
        assert response.status_code == 404
        conn = _get_conn()
        with conn:
            conn.execute("INSERT INTO alert_upgrades (alert_id,upgrade,client_id,enabled) VALUES (?,?,?,1)",
                         (aid, upgrades.INSTANT, CLIENT))
        assert upgrades.run_daily_jobs(now=NOW, dispatch=False)["charged"] == 0
        assert upgrades.priority_searches(now=NOW) == []
        state = client.get("/api/alerts/upgrades", headers=HEADERS).json()
        assert upgrades.INSTANT not in state["costs"]
        assert upgrades.INSTANT not in state["alerts"][str(aid)]
        assert state["daily_cost"] == 0
        assert credits.balance(CLIENT) == before


def test_turning_empty_shortlist_on_then_off_never_charges(fresh_db):
    with TestClient(app) as client:
        aid = pers.create_alert(CLIENT, label="Home", filters={"city": "lahore"})["id"]
        before = client.get("/api/credits", headers=HEADERS).json()["balance"]
        path = f"/api/alerts/{aid}/upgrades/{upgrades.SHORTLIST}"
        for enabled in (True, False):
            assert client.post(path, headers=HEADERS, json={"enabled": enabled}).status_code == 200
        upgrades.run_daily_jobs(now=NOW, dispatch=False)
        assert upgrades.list_shortlists(CLIENT, aid) == []
        assert credits.balance(CLIENT) == before
        assert not any(row["kind"] == "spend" for row in credits.history(CLIENT))
