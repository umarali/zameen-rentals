"""Tests for crawler worker functions — browser profiles, API headers, phone extraction."""
import pytest
from app.crawler_worker import (
    _build_browser_profile, _api_headers, _get_empty_types, _update_type_state,
    refresh_phones_batch,
)
from app.db_listings import upsert_listing, get_listing_by_zameen_id
from app.data import USER_AGENTS, CRAWL_PROPERTY_TYPES


class TestBuildBrowserProfile:
    def test_returns_ua_and_headers(self):
        ua, headers = _build_browser_profile()
        assert isinstance(ua, str)
        assert isinstance(headers, dict)
        assert "User-Agent" in headers
        assert headers["User-Agent"] == ua

    def test_has_required_headers(self):
        ua, headers = _build_browser_profile()
        assert "Accept" in headers
        assert "Accept-Language" in headers
        assert "Accept-Encoding" in headers
        assert "Connection" in headers

    def test_chrome_has_sec_ch_ua(self):
        # Keep generating until we get a Chrome UA
        for _ in range(50):
            ua, headers = _build_browser_profile()
            if "Chrome/" in ua and "Edg/" not in ua:
                assert "sec-ch-ua" in headers
                assert "sec-ch-ua-mobile" in headers
                assert "sec-ch-ua-platform" in headers
                return
        pytest.skip("Didn't get a Chrome UA in 50 tries")

    def test_randomness(self):
        profiles = set()
        for _ in range(20):
            ua, _ = _build_browser_profile()
            profiles.add(ua)
        assert len(profiles) > 1  # Should get at least 2 different UAs


class TestApiHeaders:
    def test_has_required_fields(self):
        headers = _api_headers(
            "Mozilla/5.0 Chrome/145.0.0.0 Safari/537.36",
            "https://www.zameen.com/Property/test-123-1-1.html"
        )
        assert headers["Accept"] == "application/json"
        assert headers["Content-Type"] == "application/json"
        assert headers["X-Requested-With"] == "XMLHttpRequest"
        assert "test-123" in headers["Referer"]

    def test_chrome_sec_headers(self):
        headers = _api_headers(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
            "https://www.zameen.com/"
        )
        assert "sec-ch-ua" in headers
        assert '"145"' in headers["sec-ch-ua"]
        assert headers["sec-fetch-dest"] == "empty"
        assert headers["sec-fetch-mode"] == "cors"


class TestCrawlPropertyTypes:
    def test_types_defined(self):
        assert len(CRAWL_PROPERTY_TYPES) == 5

    def test_each_has_slug_and_label(self):
        for slug, label in CRAWL_PROPERTY_TYPES:
            assert slug.startswith("Rentals_")
            assert len(label) > 0

    def test_slugs_unique(self):
        slugs = [s for s, _ in CRAWL_PROPERTY_TYPES]
        assert len(slugs) == len(set(slugs))


class TestUserAgents:
    def test_minimum_count(self):
        assert len(USER_AGENTS) >= 20

    def test_has_chrome(self):
        assert any("Chrome/" in ua for ua in USER_AGENTS)

    def test_has_firefox(self):
        assert any("Firefox/" in ua for ua in USER_AGENTS)

    def test_has_safari(self):
        assert any("Safari/" in ua and "Chrome/" not in ua for ua in USER_AGENTS)

    def test_has_edge(self):
        assert any("Edg/" in ua for ua in USER_AGENTS)

    def test_has_mobile(self):
        assert any("Mobile" in ua for ua in USER_AGENTS)

    def test_current_versions(self):
        # At least some UAs should have Chrome 143+
        assert any("Chrome/14" in ua for ua in USER_AGENTS)


class TestEmptyTypesTracking:
    def test_empty_initially(self):
        empty = _get_empty_types("karachi", "Karachi_Test")
        assert empty == set()

    def test_tracks_empty_type(self):
        _update_type_state("karachi", "Karachi_Test2", "Rentals_Rooms", 0)
        empty = _get_empty_types("karachi", "Karachi_Test2")
        assert "Rentals_Rooms" in empty

    def test_non_empty_type_not_tracked(self):
        _update_type_state("karachi", "Karachi_Test3", "Rentals_Houses_Property", 25)
        empty = _get_empty_types("karachi", "Karachi_Test3")
        assert "Rentals_Houses_Property" not in empty

    def test_update_from_empty_to_found(self):
        _update_type_state("karachi", "Karachi_Test4", "Rentals_Rooms", 0)
        assert "Rentals_Rooms" in _get_empty_types("karachi", "Karachi_Test4")
        _update_type_state("karachi", "Karachi_Test4", "Rentals_Rooms", 5)
        assert "Rentals_Rooms" not in _get_empty_types("karachi", "Karachi_Test4")


class TestRefreshPhonesBatch:
    @pytest.mark.asyncio
    async def test_uses_contact_fetched_at_and_persists_whatsapp_without_call_phone(self, monkeypatch):
        upsert_listing(
            zameen_id="810001",
            url="https://www.zameen.com/Property/test-810001-1-1.html",
            city="karachi",
            card_data={"title": "Needs contact refresh", "price": 70000, "bedrooms": 2, "bathrooms": 1, "area_size": "5 Marla"},
        )

        async def fake_fetch_phone_via_api(zameen_id, listing_url, client, ua):
            return {
                "call_phone": None,
                "whatsapp_phone": "+923001112233",
                "contact_source": "showNumbers",
                "contact_payload": {"mobile": "+923001112233"},
                "agent_agency": "Refresh Realty",
            }

        async def fake_sleep(*args, **kwargs):
            return None

        monkeypatch.setattr("app.crawler_worker.fetch_phone_via_api", fake_fetch_phone_via_api)
        monkeypatch.setattr("app.crawler_worker.asyncio.sleep", fake_sleep)

        updated = await refresh_phones_batch(limit=5)

        listing = get_listing_by_zameen_id("810001")
        assert updated == 1
        assert listing["call_phone"] is None
        assert listing["whatsapp_phone"] == "+923001112233"
        assert listing["contact_fetched_at"] is not None
