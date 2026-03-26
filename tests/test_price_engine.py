"""Tests for the price engine."""

from datetime import datetime

from resell_bot.core.models import Listing
from resell_bot.core import price_engine


def _make_listing(price: float = 5.0, isbn: str = "9782070360550") -> Listing:
    return Listing(
        title="Fondation",
        price=price,
        url="https://example.com/book/1",
        platform="momox_shop",
        isbn=isbn,
        condition="bon",
        seller=None,
        found_at=datetime.now(),
    )


class TestPriceEngine:
    def test_deal_below_max_price(self):
        listing = _make_listing(price=5.0)
        alert = price_engine.evaluate(listing, max_buy_price=15.0)
        assert alert is not None
        assert alert.savings == 10.0
        assert alert.max_buy_price == 15.0

    def test_price_above_max_returns_none(self):
        listing = _make_listing(price=20.0)
        alert = price_engine.evaluate(listing, max_buy_price=15.0)
        assert alert is None

    def test_price_equals_max_is_deal(self):
        listing = _make_listing(price=15.0)
        alert = price_engine.evaluate(listing, max_buy_price=15.0)
        assert alert is not None
        assert alert.savings == 0.0

    def test_savings_calculated_correctly(self):
        listing = _make_listing(price=7.50)
        alert = price_engine.evaluate(listing, max_buy_price=25.0)
        assert alert is not None
        assert alert.savings == 17.5

    def test_listing_preserved_in_alert(self):
        listing = _make_listing(price=3.0)
        alert = price_engine.evaluate(listing, max_buy_price=10.0)
        assert alert is not None
        assert alert.listing.title == "Fondation"
        assert alert.listing.platform == "momox_shop"
        assert alert.listing.price == 3.0
