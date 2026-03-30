"""Unit tests for scraper and parsing functions."""
import pytest
from app.scraper import (
    extract_zameen_id, parse_listings, _is_property_photo_url,
    _extract_property_type, _extract_images,
)
from app.parsing import parse_price, build_url, match_area
from app.cache import RateLimiter
from bs4 import BeautifulSoup


class TestExtractZameenId:
    def test_standard_url(self):
        url = "https://www.zameen.com/Property/dha_defence_apartment-53921288-1482-4.html"
        assert extract_zameen_id(url) == "53921288"

    def test_long_slug(self):
        url = "https://www.zameen.com/Property/bath_island_royal_elite_brand_new_artistic_interior_design_apartment_for_rent-18859662-9738-4.html"
        assert extract_zameen_id(url) == "18859662"

    def test_no_match(self):
        assert extract_zameen_id("https://www.zameen.com/Rentals/Karachi-2-1.html") is None

    def test_empty_string(self):
        assert extract_zameen_id("") is None

    def test_none(self):
        assert extract_zameen_id(None) is None

    def test_short_id(self):
        url = "https://www.zameen.com/Property/some_slug-12345-100-1.html"
        assert extract_zameen_id(url) == "12345"


class TestParsePrice:
    def test_crore(self):
        assert parse_price("PKR 1.5 Crore") == 15000000

    def test_lakh(self):
        assert parse_price("PKR 50 Lakh") == 5000000

    def test_lac(self):
        assert parse_price("PKR 2.5 Lac") == 250000

    def test_thousand(self):
        assert parse_price("PKR 75 Thousand") == 75000

    def test_raw_number(self):
        assert parse_price("150000") == 150000

    def test_with_commas(self):
        assert parse_price("PKR 1,50,000") == 150000

    def test_empty(self):
        assert parse_price("") is None

    def test_none(self):
        assert parse_price(None) is None

    def test_zero(self):
        assert parse_price("0") == 0


class TestIsPropertyPhotoUrl:
    def test_valid_photo(self):
        assert _is_property_photo_url("https://media.zameen.com/thumbnails/295194207-800x600.jpeg")

    def test_agent_photo(self):
        assert not _is_property_photo_url("https://media.zameen.com/agent/photo.jpeg")

    def test_avatar(self):
        assert not _is_property_photo_url("https://media.zameen.com/user/avatar/123.jpeg")

    def test_logo(self):
        assert not _is_property_photo_url("https://media.zameen.com/logo/agency.png")

    def test_small_image(self):
        # The regex checks /WxH/ pattern — small images like agent avatars use this
        assert not _is_property_photo_url("https://media.zameen.com/thumbnails/100x75/photo.jpeg")


class TestExtractPropertyType:
    def _card(self, text):
        return BeautifulSoup(f"<div>{text}</div>", "html.parser").div

    def test_apartment(self):
        assert _extract_property_type(self._card("2 bed apartment for rent")) == "Apartment"

    def test_flat(self):
        assert _extract_property_type(self._card("3 bed flat available")) == "Apartment"

    def test_house(self):
        assert _extract_property_type(self._card("5 Marla house for rent")) == "House"

    def test_upper_portion(self):
        assert _extract_property_type(self._card("Upper Portion for rent")) == "Upper Portion"

    def test_lower_portion(self):
        assert _extract_property_type(self._card("Lower Portion available")) == "Lower Portion"

    def test_penthouse(self):
        assert _extract_property_type(self._card("Penthouse with sea view")) == "Penthouse"

    def test_room_not_bedroom(self):
        # "room" should match but "bedroom" should not trigger "Room"
        assert _extract_property_type(self._card("2 bedroom apartment")) == "Apartment"

    def test_room_standalone(self):
        assert _extract_property_type(self._card("room available for rent")) == "Room"


class TestMatchArea:
    def test_exact_english(self):
        assert match_area("Clifton", "karachi") == "Clifton"

    def test_roman_urdu(self):
        assert match_area("gulshan", "karachi") == "Gulshan-e-Iqbal"

    def test_dha_alias(self):
        assert match_area("dha", "karachi") == "DHA Defence"

    def test_partial_match(self):
        result = match_area("DHA Phase", "karachi")
        assert result is not None
        assert "DHA Phase" in result

    def test_no_match(self):
        assert match_area("xyznonexistent", "karachi") is None


class TestBuildUrl:
    def test_basic_url(self):
        url = build_url(area="DHA Phase 5", city="karachi")
        assert "zameen.com" in url
        assert "D.H.A_Phase_5" in url or "DHA" in url

    def test_with_bedrooms(self):
        url = build_url(area="Clifton", bedrooms=3, city="karachi")
        assert "beds_in=3" in url

    def test_with_price_range(self):
        url = build_url(price_min=50000, price_max=100000, city="karachi")
        assert "price_min=50000" in url
        assert "price_max=100000" in url

    def test_with_sort(self):
        url = build_url(sort="price_low", city="karachi")
        assert "sort=price_asc" in url

    def test_with_property_type(self):
        url = build_url(property_type="house", city="karachi")
        assert "Houses" in url


class TestParseListings:
    def test_empty_html(self):
        assert parse_listings("<html><body></body></html>") == []

    def test_returns_list(self):
        result = parse_listings("<html><body></body></html>")
        assert isinstance(result, list)


class TestRateLimiter:
    @pytest.mark.asyncio
    async def test_acquire_basic(self):
        rl = RateLimiter(rate=100.0, burst=10)  # Fast for testing
        await rl.acquire()  # Should not raise

    @pytest.mark.asyncio
    async def test_rate_attribute(self):
        rl = RateLimiter(rate=2.0, burst=3)
        assert rl.rate == 2.0
        assert rl.burst == 3
