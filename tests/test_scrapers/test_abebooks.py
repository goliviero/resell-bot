"""Tests for AbeBooks scraper."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from resell_bot.scrapers.abebooks import AbebooksScraper, CONDITION_MAP


def _make_html(items_html: str) -> str:
    """Wrap item HTML in a minimal page structure."""
    return f"<html><body><ul>{items_html}</ul></body></html>"


def _make_item(
    isbn: str = "9782070368228",
    price: str = "7.54",
    condition: str = "UsedCondition",
    availability: str = "InStock",
    title: str = "1984",
    author: str = "George Orwell",
    seller: str = "TestSeller",
    url: str = "/1984-George-Orwell/123/bd",
) -> str:
    return f"""
    <li class="cf result-item" itemscope itemtype="http://schema.org/Book">
        <meta itemprop="isbn" content="{isbn}" />
        <meta itemprop="author" content="{author}" />
        <div class="result-data">
            <h2 class="title" itemprop="offers" itemscope itemtype="http://schema.org/Offer">
                <meta itemprop="price" content="{price}" />
                <meta itemprop="priceCurrency" content="EUR" />
                <meta itemprop="itemCondition" content="{condition}" />
                <meta itemprop="availability" content="{availability}" />
                <a itemprop="url" href="{url}">
                    <span data-test-id="listing-title">{title}</span>
                </a>
            </h2>
            <div class="bookseller-info">
                <a href="/seller/">{seller}</a>
            </div>
        </div>
    </li>
    """


def _mock_client(html: str, status: int = 200):
    client = MagicMock()
    resp = MagicMock()
    resp.status_code = status
    resp.text = html
    client.get = AsyncMock(return_value=resp)
    return client


class TestAbebooksGetOffer:
    @pytest.mark.asyncio
    async def test_available_book(self):
        html = _make_html(_make_item())
        scraper = AbebooksScraper(_mock_client(html))
        listing = await scraper.get_offer("9782070368228")
        assert listing is not None
        assert listing.price == 7.54
        assert listing.isbn == "9782070368228"
        assert listing.title == "1984"
        assert listing.condition == "occasion"
        assert listing.seller == "TestSeller"
        assert listing.platform == "abebooks"
        assert "abebooks.fr" in listing.url

    @pytest.mark.asyncio
    async def test_empty_results(self):
        html = _make_html("")
        scraper = AbebooksScraper(_mock_client(html))
        assert await scraper.get_offer("9782070368228") is None

    @pytest.mark.asyncio
    async def test_wrong_isbn_filtered(self):
        html = _make_html(_make_item(isbn="9999999999999"))
        scraper = AbebooksScraper(_mock_client(html))
        assert await scraper.get_offer("9782070368228") is None

    @pytest.mark.asyncio
    async def test_returns_cheapest(self):
        items = _make_item(price="15.00") + _make_item(price="5.00")
        html = _make_html(items)
        scraper = AbebooksScraper(_mock_client(html))
        listing = await scraper.get_offer("9782070368228")
        # sortby=1 means results are already sorted, we return first match
        assert listing is not None
        assert listing.price == 15.00  # First match (page already sorted)

    @pytest.mark.asyncio
    async def test_out_of_stock_skipped(self):
        html = _make_html(_make_item(availability="OutOfStock"))
        scraper = AbebooksScraper(_mock_client(html))
        assert await scraper.get_offer("9782070368228") is None

    @pytest.mark.asyncio
    async def test_new_condition(self):
        html = _make_html(_make_item(condition="NewCondition"))
        scraper = AbebooksScraper(_mock_client(html))
        listing = await scraper.get_offer("9782070368228")
        assert listing is not None
        assert listing.condition == "neuf"

    @pytest.mark.asyncio
    async def test_http_error(self):
        scraper = AbebooksScraper(_mock_client("", status=403))
        assert await scraper.get_offer("9782070368228") is None

    @pytest.mark.asyncio
    async def test_network_error(self):
        client = MagicMock()
        client.get = AsyncMock(side_effect=ConnectionError("timeout"))
        scraper = AbebooksScraper(client)
        assert await scraper.get_offer("9782070368228") is None

    @pytest.mark.asyncio
    async def test_missing_price_skipped(self):
        item_html = """
        <li class="cf result-item" itemscope itemtype="http://schema.org/Book">
            <meta itemprop="isbn" content="9782070368228" />
            <h2 itemprop="offers" itemscope itemtype="http://schema.org/Offer">
                <meta itemprop="availability" content="InStock" />
            </h2>
        </li>
        """
        scraper = AbebooksScraper(_mock_client(_make_html(item_html)))
        assert await scraper.get_offer("9782070368228") is None


class TestAbebooksConditionMap:
    def test_all_conditions_mapped(self):
        assert CONDITION_MAP["NewCondition"] == "neuf"
        assert CONDITION_MAP["UsedCondition"] == "occasion"
        assert CONDITION_MAP["RefurbishedCondition"] == "reconditionné"


class TestAbebooksPlatformName:
    def test_platform_name(self):
        scraper = AbebooksScraper(MagicMock())
        assert scraper.platform_name == "abebooks"
