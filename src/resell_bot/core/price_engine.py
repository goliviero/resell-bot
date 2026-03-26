"""Price engine — compares platform sale prices against watchlist max buy prices."""

import logging

from resell_bot.core.models import Alert, Listing

logger = logging.getLogger(__name__)


def evaluate(listing: Listing, max_buy_price: float) -> Alert | None:
    """Check if a listing is a deal worth alerting on.

    Returns an Alert if listing.price <= max_buy_price, else None.
    """
    if listing.price > max_buy_price:
        return None

    savings = round(max_buy_price - listing.price, 2)

    logger.info(
        "Deal found: %s — %s sells at %.2f€, max budget %.2f€, savings %.2f€",
        listing.title,
        listing.platform,
        listing.price,
        max_buy_price,
        savings,
    )

    return Alert(
        listing=listing,
        max_buy_price=max_buy_price,
        savings=savings,
    )
