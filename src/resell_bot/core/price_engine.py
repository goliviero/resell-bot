"""Price engine — cross-platform margin calculation."""

import logging
from dataclasses import dataclass

from resell_bot.core.models import Alert, Listing, PriceCheck

logger = logging.getLogger(__name__)

# Estimated shipping cost when buying from a marketplace
DEFAULT_SHIPPING_COST = 3.50


@dataclass
class PriceEngineConfig:
    """Thresholds for deal detection."""

    min_margin: float = 3.0
    max_buy_price: float = 15.0
    shipping_cost: float = DEFAULT_SHIPPING_COST


class PriceEngine:
    """Evaluates listings against buyback prices to find profitable deals."""

    def __init__(self, config: PriceEngineConfig | None = None) -> None:
        self.config = config or PriceEngineConfig()

    def check_price(
        self,
        listing: Listing,
        buyback_prices: dict[str, float],
    ) -> PriceCheck:
        """Build a PriceCheck for a listing against known buyback prices."""
        pc = PriceCheck(isbn=listing.isbn or "")
        pc.market_prices[listing.platform] = listing.price
        pc.buyback_prices = buyback_prices

        if not buyback_prices:
            return pc

        best_platform = max(buyback_prices, key=buyback_prices.get)  # type: ignore[arg-type]
        best_buyback = buyback_prices[best_platform]
        margin = best_buyback - listing.price - self.config.shipping_cost

        pc.best_margin = round(margin, 2)
        pc.best_buy_platform = listing.platform
        pc.best_sell_platform = best_platform
        return pc

    def evaluate(
        self,
        listing: Listing,
        buyback_prices: dict[str, float],
    ) -> Alert | None:
        """Return an Alert if the deal meets thresholds, else None."""
        if listing.price > self.config.max_buy_price:
            return None

        pc = self.check_price(listing, buyback_prices)
        if pc.best_margin < self.config.min_margin:
            return None

        logger.info(
            "Deal found: %s — buy %.2f€ on %s, sell %.2f€ on %s, margin %.2f€",
            listing.title,
            listing.price,
            listing.platform,
            buyback_prices[pc.best_sell_platform],
            pc.best_sell_platform,
            pc.best_margin,
        )

        return Alert(
            listing=listing,
            estimated_margin=pc.best_margin,
            buyback_price=buyback_prices[pc.best_sell_platform],
            buyback_platform=pc.best_sell_platform,
        )
