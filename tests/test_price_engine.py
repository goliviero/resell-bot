"""Tests for the price engine."""

from datetime import datetime

from resell_bot.core.models import Listing
from resell_bot.core.price_engine import PriceEngine, PriceEngineConfig


def _make_listing(price: float = 5.0, isbn: str = "9782070360550") -> Listing:
    return Listing(
        title="Fondation",
        price=price,
        url="https://example.com/book/1",
        platform="chasseauxlivres",
        isbn=isbn,
        condition="bon",
        seller=None,
        found_at=datetime.now(),
    )


class TestPriceEngine:
    def setup_method(self):
        self.engine = PriceEngine(
            PriceEngineConfig(min_margin=3.0, max_buy_price=15.0, shipping_cost=3.50)
        )

    def test_good_deal_generates_alert(self):
        listing = _make_listing(price=5.0)
        buyback = {"momox": 12.0, "recyclivre": 9.0}
        alert = self.engine.evaluate(listing, buyback)

        assert alert is not None
        assert alert.estimated_margin == 3.5  # 12.0 - 5.0 - 3.50
        assert alert.buyback_platform == "momox"
        assert alert.buyback_price == 12.0

    def test_bad_deal_returns_none(self):
        listing = _make_listing(price=10.0)
        buyback = {"momox": 12.0}  # margin = 12 - 10 - 3.5 = -1.5
        alert = self.engine.evaluate(listing, buyback)
        assert alert is None

    def test_price_above_max_returns_none(self):
        listing = _make_listing(price=20.0)
        buyback = {"momox": 50.0}  # huge margin but price too high
        alert = self.engine.evaluate(listing, buyback)
        assert alert is None

    def test_no_buyback_prices_returns_none(self):
        listing = _make_listing(price=5.0)
        alert = self.engine.evaluate(listing, {})
        assert alert is None

    def test_best_platform_selected(self):
        listing = _make_listing(price=3.0)
        buyback = {"momox": 8.0, "recyclivre": 10.0}
        alert = self.engine.evaluate(listing, buyback)

        assert alert is not None
        assert alert.buyback_platform == "recyclivre"
        assert alert.buyback_price == 10.0
        assert alert.estimated_margin == 3.5  # 10 - 3 - 3.5

    def test_exact_threshold_margin(self):
        # margin = buyback - price - shipping = X - price - 3.5
        # min_margin = 3.0, so need X - price - 3.5 >= 3.0 → X >= price + 6.5
        listing = _make_listing(price=5.0)
        buyback = {"momox": 11.5}  # 11.5 - 5 - 3.5 = 3.0 → exactly at threshold
        alert = self.engine.evaluate(listing, buyback)
        assert alert is not None
        assert alert.estimated_margin == 3.0

    def test_just_below_threshold(self):
        listing = _make_listing(price=5.0)
        buyback = {"momox": 11.49}  # 11.49 - 5 - 3.5 = 2.99
        alert = self.engine.evaluate(listing, buyback)
        assert alert is None

    def test_check_price_builds_price_check(self):
        listing = _make_listing(price=7.0)
        buyback = {"momox": 15.0}
        pc = self.engine.check_price(listing, buyback)

        assert pc.isbn == "9782070360550"
        assert pc.market_prices == {"chasseauxlivres": 7.0}
        assert pc.buyback_prices == {"momox": 15.0}
        assert pc.best_margin == 4.5  # 15 - 7 - 3.5
        assert pc.best_sell_platform == "momox"
