"""Tests for RecycLivre HTML scraper."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from resell_bot.scrapers.recyclivre import RecyclivreScraper, _parse_condition


# ── Sample HTML fragments ──────────────────────────────────

SEARCH_HTML_AVAILABLE = """
<html><body>
<div class="book" data-product-code="88467">
    <a href="/products/88467-germinal">
        <img src="/img.jpg">
    </a>
    <div class="flex-grow-1 p-3">
        <form data-js-add-to-cart="form"
              data-product-name="Germinal"
              data-product-id="9782253004226"
              data-product-author="Emile Zola"
              data-product-price="1.99"
              data-product-brand="Le Livre de poche"
              data-product-quantity="2"
              data-product-discount="0"
              data-product-category="ROMANS">
            <input type="hidden" name="sylius_add_to_cart[cartItem][variant]" value="88467-very_good">
        </form>
    </div>
</div>
<!-- Unrelated book with different ISBN -->
<div class="book" data-product-code="99999">
    <a href="/products/99999-other-book">
        <img src="/img2.jpg">
    </a>
    <div class="flex-grow-1 p-3">
        <form data-js-add-to-cart="form"
              data-product-name="Other Book"
              data-product-id="9780000000000"
              data-product-author="Other Author"
              data-product-price="5.00"
              data-product-quantity="1">
            <input type="hidden" name="sylius_add_to_cart[cartItem][variant]" value="99999-good">
        </form>
    </div>
</div>
</body></html>
"""

SEARCH_HTML_EMPTY = """
<html><body>
<div class="no-results">Aucun resultat</div>
</body></html>
"""

SEARCH_HTML_OUT_OF_STOCK = """
<html><body>
<div class="book" data-product-code="88467">
    <a href="/products/88467-germinal"><img></a>
    <div class="flex-grow-1 p-3">
        <form data-js-add-to-cart="form"
              data-product-name="Germinal"
              data-product-id="9782253004226"
              data-product-price="1.99"
              data-product-quantity="0">
            <input type="hidden" name="sylius_add_to_cart[cartItem][variant]" value="88467-good">
        </form>
    </div>
</div>
</body></html>
"""


def _mock_response(text: str, status: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status
    resp.text = text
    return resp


class TestParseCondition:
    def test_very_good(self):
        assert _parse_condition("88467-very_good") == "très bon"

    def test_good(self):
        assert _parse_condition("12345-good") == "bon"

    def test_like_new(self):
        assert _parse_condition("12345-like_new") == "comme neuf"

    def test_acceptable(self):
        assert _parse_condition("12345-acceptable") == "acceptable"

    def test_empty(self):
        assert _parse_condition("") is None

    def test_no_dash(self):
        assert _parse_condition("nodash") is None


class TestRecyclivreGetOffer:
    @pytest.fixture
    def scraper(self):
        client = MagicMock()
        client.get = AsyncMock()
        return RecyclivreScraper(client)

    def test_available_book_returns_listing(self, scraper):
        scraper.client.get.return_value = _mock_response(SEARCH_HTML_AVAILABLE)
        result = asyncio.run(
            scraper.get_offer("9782253004226")
        )
        assert result is not None
        assert result.title == "Germinal"
        assert result.price == 1.99
        assert result.author == "Emile Zola"
        assert result.condition == "très bon"
        assert result.platform == "recyclivre"
        assert result.isbn == "9782253004226"
        assert "/products/88467-germinal" in result.url

    def test_empty_results_returns_none(self, scraper):
        scraper.client.get.return_value = _mock_response(SEARCH_HTML_EMPTY)
        result = asyncio.run(
            scraper.get_offer("9782253004226")
        )
        assert result is None

    def test_out_of_stock_returns_none(self, scraper):
        scraper.client.get.return_value = _mock_response(SEARCH_HTML_OUT_OF_STOCK)
        result = asyncio.run(
            scraper.get_offer("9782253004226")
        )
        assert result is None

    def test_wrong_isbn_not_matched(self, scraper):
        scraper.client.get.return_value = _mock_response(SEARCH_HTML_AVAILABLE)
        result = asyncio.run(
            scraper.get_offer("9999999999999")
        )
        assert result is None

    def test_http_error_returns_none(self, scraper):
        scraper.client.get.return_value = _mock_response("", status=500)
        result = asyncio.run(
            scraper.get_offer("9782253004226")
        )
        assert result is None

    def test_network_error_returns_none(self, scraper):
        scraper.client.get = AsyncMock(side_effect=Exception("Connection failed"))
        result = asyncio.run(
            scraper.get_offer("9782253004226")
        )
        assert result is None


class TestRecyclivrePlatformName:
    def test_platform_name(self):
        client = MagicMock()
        scraper = RecyclivreScraper(client)
        assert scraper.platform_name == "recyclivre"
