"""Tests for Ammareal HTML scraper."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from resell_bot.scrapers.ammareal import (
    AmmarealScraper,
    _parse_condition,
    _parse_price,
)


# ── Sample HTML fragments ──────────────────────────────────

SEARCH_HTML_AVAILABLE = """
<html><body>
<div class="product-miniature product-miniature--grid js-product-miniature" data-id-product="1420333">
    <a class="product-miniature__link" href="/livre/1420333-h-428-614-1984-9782070368228.html">
        <img src="/img.jpg">
    </a>
    <div class="product-miniature__info">
        <span class="product-miniature__name">1984</span>
        <span class="product-miniature__origin">George Orwell</span>
        <span class="product-miniature__flag--state">Très bon</span>
        <span class="product-miniature__price">3,19 €</span>
        <span class="product-miniature__category">Livre</span>
    </div>
    <a class="fake-add-to-cart" href="/panier?add=1&id_product=1420333"></a>
</div>
<!-- Unrelated book with different ISBN -->
<div class="product-miniature product-miniature--grid js-product-miniature" data-id-product="9999999">
    <a class="product-miniature__link" href="/livre/9999999-autre-livre-9780000000000.html">
        <img src="/img2.jpg">
    </a>
    <div class="product-miniature__info">
        <span class="product-miniature__name">Autre Livre</span>
        <span class="product-miniature__origin">Autre Auteur</span>
        <span class="product-miniature__flag--state">Bon</span>
        <span class="product-miniature__price">5,00 €</span>
    </div>
    <a class="fake-add-to-cart" href="/panier?add=1&id_product=9999999"></a>
</div>
</body></html>
"""

SEARCH_HTML_MULTIPLE_SAME_ISBN = """
<html><body>
<div class="product-miniature product-miniature--grid js-product-miniature" data-id-product="1420333">
    <a class="product-miniature__link" href="/livre/1420333-1984-9782070368228.html">
        <img src="/img.jpg">
    </a>
    <div class="product-miniature__info">
        <span class="product-miniature__name">1984 (cher)</span>
        <span class="product-miniature__origin">George Orwell</span>
        <span class="product-miniature__flag--state">Comme neuf</span>
        <span class="product-miniature__price">8,50 €</span>
    </div>
</div>
<div class="product-miniature product-miniature--grid js-product-miniature" data-id-product="1420334">
    <a class="product-miniature__link" href="/livre/1420334-1984-poche-9782070368228.html">
        <img src="/img2.jpg">
    </a>
    <div class="product-miniature__info">
        <span class="product-miniature__name">1984 (pas cher)</span>
        <span class="product-miniature__origin">George Orwell</span>
        <span class="product-miniature__flag--state">Bon</span>
        <span class="product-miniature__price">2,99 €</span>
    </div>
</div>
</body></html>
"""

SEARCH_HTML_EMPTY = """
<html><body>
<div class="no-results">Aucun résultat pour votre recherche</div>
</body></html>
"""

SEARCH_HTML_NO_PRICE = """
<html><body>
<div class="product-miniature product-miniature--grid js-product-miniature" data-id-product="1420333">
    <a class="product-miniature__link" href="/livre/1420333-1984-9782070368228.html">
        <img src="/img.jpg">
    </a>
    <div class="product-miniature__info">
        <span class="product-miniature__name">1984</span>
    </div>
</div>
</body></html>
"""


def _mock_response(text: str, status: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status
    resp.text = text
    return resp


class TestParsePrice:
    def test_french_format(self):
        assert _parse_price("3,19 €") == 3.19

    def test_integer_price(self):
        assert _parse_price("5,00 €") == 5.0

    def test_high_price(self):
        assert _parse_price("12,50 €") == 12.5

    def test_no_space_before_euro(self):
        assert _parse_price("3,19€") == 3.19

    def test_empty_string(self):
        assert _parse_price("") is None

    def test_invalid(self):
        assert _parse_price("abc") is None

    def test_whitespace(self):
        assert _parse_price("  3,19 €  ") == 3.19


class TestParseCondition:
    def test_bon(self):
        assert _parse_condition("Bon") == "bon"

    def test_tres_bon(self):
        assert _parse_condition("Très bon") == "très bon"

    def test_comme_neuf(self):
        assert _parse_condition("Comme neuf") == "comme neuf"

    def test_acceptable(self):
        assert _parse_condition("Acceptable") == "acceptable"

    def test_empty(self):
        assert _parse_condition("") is None

    def test_unknown(self):
        assert _parse_condition("Neuf") is None

    def test_whitespace(self):
        assert _parse_condition("  Bon  ") == "bon"


class TestAmmarealGetOffer:
    @pytest.fixture
    def scraper(self):
        client = MagicMock()
        client.get = AsyncMock()
        return AmmarealScraper(client)

    def test_available_book_returns_listing(self, scraper):
        scraper.client.get.return_value = _mock_response(SEARCH_HTML_AVAILABLE)
        result = asyncio.run(scraper.get_offer("9782070368228"))
        assert result is not None
        assert result.title == "1984"
        assert result.price == 3.19
        assert result.author == "George Orwell"
        assert result.condition == "très bon"
        assert result.platform == "ammareal"
        assert result.isbn == "9782070368228"
        assert result.seller == "Ammareal"
        assert "1420333" in result.url
        assert result.url.startswith("https://www.ammareal.fr")

    def test_empty_results_returns_none(self, scraper):
        scraper.client.get.return_value = _mock_response(SEARCH_HTML_EMPTY)
        result = asyncio.run(scraper.get_offer("9782070368228"))
        assert result is None

    def test_wrong_isbn_not_matched(self, scraper):
        scraper.client.get.return_value = _mock_response(SEARCH_HTML_AVAILABLE)
        result = asyncio.run(scraper.get_offer("9999999999999"))
        assert result is None

    def test_returns_cheapest_listing(self, scraper):
        scraper.client.get.return_value = _mock_response(
            SEARCH_HTML_MULTIPLE_SAME_ISBN
        )
        result = asyncio.run(scraper.get_offer("9782070368228"))
        assert result is not None
        assert result.price == 2.99
        assert result.title == "1984 (pas cher)"

    def test_http_error_returns_none(self, scraper):
        scraper.client.get.return_value = _mock_response("", status=500)
        result = asyncio.run(scraper.get_offer("9782070368228"))
        assert result is None

    def test_network_error_returns_none(self, scraper):
        scraper.client.get = AsyncMock(side_effect=Exception("Connection failed"))
        result = asyncio.run(scraper.get_offer("9782070368228"))
        assert result is None

    def test_no_price_skipped(self, scraper):
        scraper.client.get.return_value = _mock_response(SEARCH_HTML_NO_PRICE)
        result = asyncio.run(scraper.get_offer("9782070368228"))
        assert result is None

    def test_isbn_in_fake_link(self, scraper):
        """ISBN can appear in the fake-add-to-cart href instead of product link."""
        html = """
        <html><body>
        <div class="product-miniature product-miniature--grid js-product-miniature" data-id-product="123">
            <a class="product-miniature__link" href="/livre/123-some-book.html"></a>
            <div class="product-miniature__info">
                <span class="product-miniature__name">Test Book</span>
                <span class="product-miniature__price">1,50 €</span>
            </div>
            <a class="fake-add-to-cart" href="/panier?isbn=9782070368228&add=1"></a>
        </div>
        </body></html>
        """
        scraper.client.get.return_value = _mock_response(html)
        result = asyncio.run(scraper.get_offer("9782070368228"))
        assert result is not None
        assert result.price == 1.50


class TestAmmarealPlatformName:
    def test_platform_name(self):
        client = MagicMock()
        scraper = AmmarealScraper(client)
        assert scraper.platform_name == "ammareal"
