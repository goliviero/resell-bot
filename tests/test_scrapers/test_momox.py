"""Tests for Momox Shop scraper."""

from dataclasses import dataclass
from unittest.mock import AsyncMock

import pytest

from resell_bot.scrapers.momox import MomoxShopScraper, _isbn_to_mpid, _parse_condition
from resell_bot.utils.http_client import HttpClient


SAMPLE_PRODUCT_HTML = """
<html>
<body>
<div data-cnstrc-item-name="Harry Potter à l'école des sorciers"
     data-cnstrc-item-price="12.50"
     data-cnstrc-item-variation-id="M02070584623_UsedVeryGood">
</div>
</body>
</html>
"""

SAMPLE_NO_PRICE_HTML = """
<html><body><div>No product found</div></body></html>
"""


@dataclass
class FakeResponse:
    """Lightweight response mock compatible with curl_cffi."""
    status_code: int
    text: str = ""
    url: str = ""


@pytest.fixture
def http_client():
    return HttpClient(timeout=5.0, max_retries=1, delay_min=0, delay_max=0)


@pytest.fixture
def scraper(http_client):
    return MomoxShopScraper(http_client)


class TestMomoxShopGetOffer:
    @pytest.mark.asyncio
    async def test_valid_offer_returns_listing(self, scraper):
        scraper.client.get = AsyncMock(
            return_value=FakeResponse(200, SAMPLE_PRODUCT_HTML, "https://www.momox-shop.fr/product.html")
        )
        listing = await scraper.get_offer("9782070584628")
        assert listing is not None
        assert listing.price == 12.50
        assert listing.platform == "momox_shop"
        assert listing.condition == "très bon"
        assert "Harry Potter" in listing.title

    @pytest.mark.asyncio
    async def test_not_found_returns_none(self, scraper):
        scraper.client.get = AsyncMock(return_value=FakeResponse(404))
        listing = await scraper.get_offer("9782070584628")
        assert listing is None

    @pytest.mark.asyncio
    async def test_no_price_element_returns_none(self, scraper):
        scraper.client.get = AsyncMock(
            return_value=FakeResponse(200, SAMPLE_NO_PRICE_HTML)
        )
        listing = await scraper.get_offer("9782070584628")
        assert listing is None

    @pytest.mark.asyncio
    async def test_network_error_returns_none(self, scraper):
        scraper.client.get = AsyncMock(side_effect=ConnectionError("Connection refused"))
        listing = await scraper.get_offer("9782070584628")
        assert listing is None

    @pytest.mark.asyncio
    async def test_isbn_preserved_in_listing(self, scraper):
        scraper.client.get = AsyncMock(
            return_value=FakeResponse(200, SAMPLE_PRODUCT_HTML)
        )
        listing = await scraper.get_offer("9782070584628")
        assert listing is not None
        assert listing.isbn == "9782070584628"

    @pytest.mark.asyncio
    async def test_seller_is_momox(self, scraper):
        scraper.client.get = AsyncMock(
            return_value=FakeResponse(200, SAMPLE_PRODUCT_HTML)
        )
        listing = await scraper.get_offer("9782070584628")
        assert listing is not None
        assert listing.seller == "Momox"


class TestIsbnToMpid:
    def test_isbn13_to_mpid(self):
        assert _isbn_to_mpid("9782070584628") == "M02070584623"

    def test_isbn10_to_mpid(self):
        assert _isbn_to_mpid("2070584623") == "M02070584623"

    def test_isbn_with_hyphens(self):
        assert _isbn_to_mpid("978-2-07-058462-8") == "M02070584623"

    def test_invalid_isbn_returns_none(self):
        assert _isbn_to_mpid("invalid") is None


class TestParseCondition:
    def test_used_very_good(self):
        assert _parse_condition("M0xxx_UsedVeryGood") == "très bon"

    def test_used_like_new(self):
        assert _parse_condition("M0xxx_UsedLikeNew") == "comme neuf"

    def test_new(self):
        assert _parse_condition("M0xxx_New") == "neuf"

    def test_unknown(self):
        assert _parse_condition("M0xxx_SomeOther") is None


class TestMomoxPlatformName:
    def test_platform_name(self, scraper):
        assert scraper.platform_name == "momox_shop"
