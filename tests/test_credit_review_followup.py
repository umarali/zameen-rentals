import json
import sqlite3
from datetime import datetime, timezone
from types import SimpleNamespace as NS

import anthropic
import httpx
import pytest
from fastapi.testclient import TestClient
from app import app, credits, ranking, personalization as pers, payments
from app.database import _get_conn
from app.cache import limiter


@pytest.fixture(autouse=True)
def schema(fresh_db):
    pers.init_personalization_schema()
    payments.init_payments_schema()
    limiter.reset()
    yield
    limiter.reset()


def test_free_route_works_when_starter_grant_storage_fails():
    conn = _get_conn()
    with conn:
        conn.execute("CREATE TRIGGER fail_starter BEFORE INSERT ON credit_ledger WHEN NEW.kind='starter' BEGIN SELECT RAISE(ABORT, 'storage unavailable'); END")
    with TestClient(app, raise_server_exceptions=False) as client:
        assert client.post('/api/personalization/touch', headers={'X-Client-Id':'free-with-credit-storage-failure'}).status_code == 200


def test_unregistered_wallet_cannot_mint_starter_credits():
    assert credits.balance('unregistered-wallet') == 0
    with pytest.raises(credits.InsufficientCredits):
        credits.spend('unregistered-wallet', 'tailored_list', ref='cold-spend')
    credits.grant('unregistered-wallet', 50, kind='purchase', ref='payment:cold')
    assert credits.balance('unregistered-wallet') == 50


def test_ipv6_addresses_in_one_prefix_share_starter_limit(monkeypatch):
    monkeypatch.setattr(credits, 'STARTER_WALLETS_PER_NETWORK_DAY', 1)
    credits.register_starter_request('ipv6-wallet-first', '2001:db8:1234:5678::1')
    credits.register_starter_request('ipv6-wallet-second', '2001:db8:1234:5678::2')
    credits.register_starter_request('ipv6-wallet-other', '2001:db8:1234:5679::1')
    assert credits.balance('ipv6-wallet-first') == 10
    assert credits.balance('ipv6-wallet-second') == 0
    assert credits.balance('ipv6-wallet-other') == 10


def test_denied_claim_retries_next_day_and_paid_grant_stays_separate(monkeypatch):
    class Clock:
        day=14
        @classmethod
        def now(cls, tz):return datetime(2026,10,cls.day,12,tzinfo=timezone.utc)
    monkeypatch.setattr(credits, 'datetime', Clock)
    monkeypatch.setattr(credits, 'STARTER_WALLETS_PER_NETWORK_DAY', 1)
    credits.register_starter_request('day-wallet-first', '203.0.113.8')
    credits.register_starter_request('day-wallet-denied', '203.0.113.8')
    credits.grant('day-wallet-denied', 50, kind='purchase', ref='payment:denied')
    assert credits.balance('day-wallet-denied') == 50
    Clock.day=15
    credits.register_starter_request('day-wallet-denied', '203.0.113.8')
    assert credits.balance('day-wallet-denied') == 60


@pytest.mark.parametrize('status',[400,401,403,404,429,529,None])
def test_rejected_provider_call_releases_budget(monkeypatch,status):
    calls=[]
    def create(**kwargs):
        calls.append(1)
        if status is None:
            raise TypeError("unexpected keyword argument 'output_config'")
        raise anthropic.APIStatusError('Rejected',response=httpx.Response(status,request=httpx.Request('POST','https://api.anthropic.com/v1/messages')),body={})
    monkeypatch.setattr(ranking,'_get_client',lambda:NS(messages=NS(create=create)))
    monkeypatch.setattr(ranking,'AI_DAILY_BUDGET_USD',.03)
    for _ in range(2):
        with pytest.raises(ranking.RankingError):
            ranking.call_claude_json(feature='test',model='claude-sonnet-5-5',system='s',user='u',schema={},max_tokens=1000)
    assert len(calls)==2


def test_client_cannot_bypass_claim_limit_with_forwarded_header(monkeypatch):
    monkeypatch.setattr(credits, 'STARTER_WALLETS_PER_NETWORK_DAY', 1)
    with TestClient(app, client=('203.0.113.4', 50000)) as c:
        a=c.get('/api/credits',headers={'X-Client-Id':'forwarded-first-wallet'})
        b=c.get('/api/credits',headers={'X-Client-Id':'forwarded-second-wallet','X-Forwarded-For':'198.51.100.9'})
        assert a.json()['balance']==10
        assert b.json()['balance']==0


def test_starter_cleanup_skips_cleared_rows_and_runs_once_a_day():
    conn = _get_conn()
    with conn:
        conn.execute('CREATE TABLE cleanup_updates (client_id TEXT)')
        conn.execute('CREATE TRIGGER count_cleanup AFTER UPDATE OF network_hash ON credit_starter_claims BEGIN INSERT INTO cleanup_updates VALUES (NEW.client_id); END')
        conn.executemany('INSERT INTO credit_starter_claims VALUES (?, ?, ?, 0)',
                         [(f'old-{i}', '2000-01-01', None) for i in range(100)])
        conn.execute("INSERT INTO credit_starter_claims VALUES ('old-hash', '2000-01-01', 'old-fingerprint', 0)")
    credits.register_starter_request('cleanup-first-wallet', '192.0.2.1')
    assert conn.execute('SELECT COUNT(*) FROM cleanup_updates').fetchone()[0] == 1
    with conn:
        conn.execute('DELETE FROM cleanup_updates')
    credits.register_starter_request('cleanup-second-wallet', '192.0.2.1')
    assert conn.execute('SELECT COUNT(*) FROM cleanup_updates').fetchone()[0] == 0


def test_credit_failure_is_controlled_and_free_touch_still_works(monkeypatch):
    def fail(*args):raise sqlite3.OperationalError('database unavailable')
    monkeypatch.setattr(credits, 'register_starter_request', fail)
    headers={'X-Client-Id':'credit-service-failure-client'}
    with TestClient(app, raise_server_exceptions=False) as client:
        assert client.post('/api/personalization/touch', headers=headers).status_code == 200
        response=client.get('/api/credits',headers=headers)
        assert response.status_code==503
        assert response.json()['detail']=='Credits are temporarily unavailable. Search still works.'


def test_response_value_error_keeps_ambiguous_budget_reservation(monkeypatch):
    def create(**kwargs):raise UnicodeDecodeError('utf-8', b'\xff', 0, 1, 'invalid response')
    monkeypatch.setattr(ranking,'_get_client',lambda:NS(messages=NS(create=create)))
    with pytest.raises(ranking.RankingError):
        ranking.call_claude_json(feature='test',model='claude-sonnet-5-5',system='s',user='u',schema={},max_tokens=1000)
    assert _get_conn().execute('SELECT COUNT(*) FROM ai_budget_reservations').fetchone()[0]==1


def test_starter_claim_does_not_commit_shared_transaction():
    conn=_get_conn()
    conn.execute('BEGIN')
    conn.execute('SELECT COUNT(*) FROM credit_ledger').fetchone()
    try:
        credits.register_starter_request('isolated-starter-connection', '192.0.2.6')
        assert conn.in_transaction
    finally:
        conn.rollback()
    assert credits.balance('isolated-starter-connection')==10


def test_ai_work_claim_and_release_do_not_commit_shared_transaction():
    from app import routes_ai
    first=routes_ai._claim_work(['setup-key'])
    routes_ai._release_work(first)
    conn=_get_conn()
    conn.execute('BEGIN')
    conn.execute('SELECT COUNT(*) FROM ai_work_claims').fetchone()
    try:
        owner=routes_ai._claim_work(['isolated-claim'])
        assert conn.in_transaction
        routes_ai._release_work(owner)
        assert conn.in_transaction
    finally:
        conn.rollback()
    assert conn.execute('SELECT COUNT(*) FROM ai_work_claims').fetchone()[0]==0
