"""Declared crawler identity: fixed User-Agent, /bot page, Web Bot Auth, robots.txt."""
import base64
import logging
import re

import pytest
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from fastapi.testclient import TestClient

import app.crawler as crawler_mod
from app import app, botidentity, scraper
from app.crawler_worker import _fetch, crawler_rate_limiter

EXPECTED_UA = "ZameenRentalBot/1.0 (+https://zameenrental.com/bot)"


def _b64url_decode(value):
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


@pytest.fixture
def test_key(monkeypatch):
    key = Ed25519PrivateKey.generate()
    seed = key.private_bytes(
        serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption()
    )
    monkeypatch.setenv(botidentity.KEY_ENV_VAR, base64.b64encode(seed).decode())
    return key


@pytest.fixture
def no_key(monkeypatch):
    monkeypatch.delenv(botidentity.KEY_ENV_VAR, raising=False)
    monkeypatch.setattr(botidentity, "_warned_unsigned", False)


@pytest.fixture
def client():
    return TestClient(app)


class _Resp:
    def __init__(self, status_code=200, text=""):
        self.status_code, self.text = status_code, text


class _RecordingClient:
    """Stands in for httpx.AsyncClient; records the headers of each GET."""

    def __init__(self, resp=None, exc=None):
        self.resp, self.exc, self.calls = resp or _Resp(200, "ok"), exc, []

    async def get(self, url, headers=None, **kwargs):
        self.calls.append((url, dict(headers or {})))
        if self.exc:
            raise self.exc
        return self.resp


def _verify(public_key, signature_header, input_header, base_lines):
    label, params = input_header.split("=", 1)
    sig = re.fullmatch(rf"{label}=:([A-Za-z0-9+/=]+):", signature_header).group(1)
    base = "\n".join(base_lines + [f'"@signature-params": {params}']).encode()
    public_key.verify(base64.b64decode(sig), base)


# ── Fixed User-Agent ──

class TestFixedUserAgent:
    def test_constant(self):
        assert botidentity.BOT_USER_AGENT == EXPECTED_UA

    def test_sign_helper_overrides_any_other_user_agent(self, no_key):
        out = botidentity.sign_request_headers(
            "https://www.zameen.com/", {"User-Agent": "Mozilla/5.0 Chrome/145.0.0.0"}
        )
        assert out["User-Agent"] == EXPECTED_UA

    @pytest.mark.asyncio
    async def test_crawler_fetch_sends_fixed_ua_without_client_hints(self, no_key):
        crawler_rate_limiter.reset(100.0)
        fake = _RecordingClient()
        try:
            html = await _fetch(
                "https://www.zameen.com/Rentals/Karachi-2-1.html", fake,
                {"User-Agent": "Mozilla/5.0 Chrome/145.0.0.0", "sec-ch-ua": "x"},
            )
        finally:
            crawler_rate_limiter.reset(1.0)
        assert html == "ok"
        _, headers = fake.calls[0]
        assert headers["User-Agent"] == EXPECTED_UA

    @pytest.mark.asyncio
    async def test_contact_api_uses_fixed_ua(self, no_key):
        class Limiter:
            async def acquire(self):
                pass

        class Client(_RecordingClient):
            async def get(self, url, headers=None, **kwargs):
                await super().get(url, headers=headers)
                raise RuntimeError("stop")

        fake = Client()
        await scraper.fetch_listing_contact(
            "https://www.zameen.com/Property/x-12345678-1-1.html",
            client=fake, user_agent="Mozilla/5.0 Chrome/145", request_limiter=Limiter(),
        )
        assert fake.calls and all(h["User-Agent"] == EXPECTED_UA for _, h in fake.calls)

    def test_no_browser_user_agent_pool_left(self):
        import app.data as data
        assert not hasattr(data, "USER_AGENTS")


# ── /bot page ──

class TestBotPage:
    def test_page_is_public_and_complete(self, client):
        r = client.get("/bot")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/html")
        text = re.sub(r"<[^>]+>", " ", r.text)
        assert EXPECTED_UA in text
        assert "165.22.91.77" in text
        assert "feedback@zameenrental.com" in text
        assert "1 request per second" in text
        assert "robots.txt" in text
        assert "Zameen.com" in text
        assert "/.well-known/http-message-signatures-directory" in r.text


# ── Web Bot Auth: key directory ──

class TestKeyDirectory:
    def test_directory_shape_with_key(self, client, test_key):
        r = client.get(botidentity.DIRECTORY_PATH)
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/http-message-signatures-directory+json"
        keys = r.json()["keys"]
        assert len(keys) == 1
        jwk = keys[0]
        assert jwk["kty"] == "OKP" and jwk["crv"] == "Ed25519"
        assert set(jwk) == {"kty", "crv", "x"}  # never leaks "d"
        raw_pub = test_key.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
        assert _b64url_decode(jwk["x"]) == raw_pub
        assert "=" not in jwk["x"]

    def test_directory_response_is_signed(self, client, test_key):
        r = client.get(botidentity.DIRECTORY_PATH)
        inp = r.headers["signature-input"]
        assert 'tag="http-message-signatures-directory"' in inp
        assert 'alg="ed25519"' in inp
        assert f'keyid="{botidentity.jwk_thumbprint(test_key)}"' in inp
        assert re.search(r"created=\d+", inp) and re.search(r"expires=\d+", inp)
        assert inp.startswith('sig1=("@authority";req)')
        _verify(test_key.public_key(), r.headers["signature"], inp,
                ['"@authority";req: testserver'])

    def test_thumbprint_is_rfc7638(self, test_key):
        import hashlib
        x = botidentity.public_jwk(test_key)["x"]
        canonical = f'{{"crv":"Ed25519","kty":"OKP","x":"{x}"}}'.encode()
        expected = base64.urlsafe_b64encode(hashlib.sha256(canonical).digest()).rstrip(b"=").decode()
        assert botidentity.jwk_thumbprint(test_key) == expected

    def test_directory_404_without_key(self, client, no_key):
        assert client.get(botidentity.DIRECTORY_PATH).status_code == 404


# ── Web Bot Auth: request signing ──

class TestRequestSigning:
    def test_signed_request_verifies(self, test_key):
        url = "https://www.zameen.com/Rentals/Karachi-2-1.html?sort=date_desc"
        out = botidentity.sign_request_headers(url, {"Accept": "text/html"}, now=1_800_000_000)
        assert out["User-Agent"] == EXPECTED_UA
        assert out["Accept"] == "text/html"
        assert out["Signature-Agent"] == '"https://zameenrental.com"'
        inp = out["Signature-Input"]
        assert inp.startswith('sig1=("@authority" "signature-agent")')
        assert 'tag="web-bot-auth"' in inp and 'alg="ed25519"' in inp
        assert "created=1800000000" in inp and "expires=1800000060" in inp
        assert f'keyid="{botidentity.jwk_thumbprint(test_key)}"' in inp
        _verify(test_key.public_key(), out["Signature"], inp, [
            '"@authority": www.zameen.com',
            '"signature-agent": "https://zameenrental.com"',
        ])

    def test_signature_fails_for_other_authority(self, test_key):
        out = botidentity.sign_request_headers("https://www.zameen.com/x", now=1_800_000_000)
        with pytest.raises(InvalidSignature):
            _verify(test_key.public_key(), out["Signature"], out["Signature-Input"], [
                '"@authority": evil.example',
                '"signature-agent": "https://zameenrental.com"',
            ])

    @pytest.mark.asyncio
    async def test_crawler_fetch_is_signed_when_keyed(self, test_key):
        crawler_rate_limiter.reset(100.0)
        fake = _RecordingClient()
        try:
            await _fetch("https://www.zameen.com/Rentals/Karachi-2-1.html", fake, {})
        finally:
            crawler_rate_limiter.reset(1.0)
        headers = fake.calls[0][1]
        assert {"Signature", "Signature-Input", "Signature-Agent"} <= set(headers)

    def test_unsigned_without_key_does_not_crash(self, no_key, caplog):
        with caplog.at_level(logging.WARNING, logger="zameenrentals"):
            out = botidentity.sign_request_headers("https://www.zameen.com/", {"Accept": "x"})
        assert out["User-Agent"] == EXPECTED_UA
        assert out["Accept"] == "x"
        assert not {"Signature", "Signature-Input", "Signature-Agent"} & set(out)
        assert any("UNSIGNED" in rec.message for rec in caplog.records)

    @pytest.mark.asyncio
    async def test_crawler_fetch_unsigned_without_key(self, no_key):
        crawler_rate_limiter.reset(100.0)
        fake = _RecordingClient()
        try:
            html = await _fetch("https://www.zameen.com/Rentals/Karachi-2-1.html", fake, {})
        finally:
            crawler_rate_limiter.reset(1.0)
        assert html == "ok"
        headers = fake.calls[0][1]
        assert headers["User-Agent"] == EXPECTED_UA
        assert "Signature" not in headers

    def test_invalid_key_is_unsigned_not_fatal(self, monkeypatch):
        monkeypatch.setenv(botidentity.KEY_ENV_VAR, "not-a-key")
        out = botidentity.sign_request_headers("https://www.zameen.com/")
        assert out["User-Agent"] == EXPECTED_UA and "Signature" not in out


# ── robots.txt ──

ALLOWING = "User-agent: *\nDisallow: /api/userEvents\nDisallow: /Karachi*\n"


@pytest.fixture
def fresh_robots(monkeypatch):
    monkeypatch.setattr(crawler_mod, "_robots_cache", {})
    monkeypatch.setattr(crawler_mod, "_robots_rate_cap", None)
    crawler_rate_limiter.reset(1.0)
    yield
    crawler_rate_limiter.reset(1.0)


class TestRobotsTxt:
    @pytest.mark.asyncio
    async def test_fetch_exception_means_do_not_crawl(self, fresh_robots, no_key):
        fake = _RecordingClient(exc=RuntimeError("network down"))
        assert await crawler_mod.check_robots_txt(fake, "ua") is None

    @pytest.mark.asyncio
    @pytest.mark.parametrize("status", [403, 404, 429, 500, 503])
    async def test_non_200_means_do_not_crawl(self, fresh_robots, no_key, status):
        fake = _RecordingClient(resp=_Resp(status, "User-agent: *\nAllow: /"))
        assert await crawler_mod.check_robots_txt(fake, "ua") is None

    @pytest.mark.asyncio
    async def test_failure_is_not_cached_as_allow(self, fresh_robots, no_key):
        bad = _RecordingClient(resp=_Resp(500))
        assert await crawler_mod.check_robots_txt(bad, "ua") is None
        assert await crawler_mod.check_robots_txt(bad, "ua") is None
        assert len(bad.calls) == 2

    @pytest.mark.asyncio
    async def test_200_with_allowed_paths(self, fresh_robots, no_key):
        fake = _RecordingClient(resp=_Resp(200, ALLOWING))
        assert await crawler_mod.check_robots_txt(fake, "ua") == ALLOWING
        assert fake.calls[0][1]["User-Agent"] == EXPECTED_UA

    @pytest.mark.asyncio
    async def test_disallowed_rentals_path(self, fresh_robots, no_key):
        fake = _RecordingClient(resp=_Resp(200, "User-agent: *\nDisallow: /Rentals/\n"))
        assert await crawler_mod.check_robots_txt(fake, "ua") is None

    @pytest.mark.asyncio
    async def test_our_own_group_overrides_wildcard(self, fresh_robots, no_key):
        text = "User-agent: ZameenRentalBot\nDisallow: /\n\nUser-agent: *\nAllow: /\n"
        assert await crawler_mod.check_robots_txt(_RecordingClient(resp=_Resp(200, text)), "ua") is None

    @pytest.mark.asyncio
    async def test_long_crawl_delay_is_honoured_not_capped(self, fresh_robots, no_key):
        text = "User-agent: *\nCrawl-delay: 10\n"
        assert await crawler_mod.check_robots_txt(_RecordingClient(resp=_Resp(200, text)), "ua")
        assert crawler_mod._robots_rate_cap == pytest.approx(0.1)
        assert crawler_rate_limiter.target_rate == pytest.approx(0.1)

    @pytest.mark.asyncio
    async def test_short_crawl_delay_never_raises_rate_above_one_per_second(self, fresh_robots, no_key):
        text = "User-agent: *\nCrawl-delay: 0.1\n"
        assert await crawler_mod.check_robots_txt(_RecordingClient(resp=_Resp(200, text)), "ua")
        assert crawler_mod._robots_rate_cap == 1.0
        assert crawler_rate_limiter.target_rate <= 1.0

    def test_published_rate_cap(self):
        assert crawler_mod.DEFAULT_MAX_RATE == 1.0
        assert crawler_rate_limiter.burst == 1

    @pytest.mark.asyncio
    async def test_cycle_does_not_crawl_when_robots_unavailable(self, fresh_robots, no_key, monkeypatch):
        """run_crawler's caller path: None from robots means sleep, never crawl."""
        calls = []

        class FakeClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

        async def fake_robots(client, ua):
            return None

        async def fake_detail_batch(**kw):
            calls.append("detail")
            return 0

        async def fake_sleep(seconds):
            crawler_mod._shutdown = True

        monkeypatch.setattr(crawler_mod, "_shutdown", False)
        monkeypatch.setattr(crawler_mod, "init_db", lambda: None)
        monkeypatch.setattr(crawler_mod, "init_personalization_schema", lambda: None)
        monkeypatch.setattr(crawler_mod, "init_crawl_state", lambda: None)
        monkeypatch.setattr(crawler_mod, "get_crawl_stats", lambda: {
            "total_listings": 0, "areas_crawled": 0, "areas_total": 0, "detail_coverage": 0.0})
        monkeypatch.setattr(crawler_mod, "check_robots_txt", fake_robots)
        monkeypatch.setattr(crawler_mod, "crawl_detail_batch", fake_detail_batch)
        monkeypatch.setattr(crawler_mod.httpx, "AsyncClient", lambda: FakeClient())
        monkeypatch.setattr(crawler_mod.asyncio, "sleep", fake_sleep)
        await crawler_mod.run_backfill_worker(detail_batch=1, phone_batch=1, concurrency=1)
        assert calls == []
