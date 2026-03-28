"""Scraper for RecycLivre — secondhand book marketplace.

Uses the search page at recyclivre.com/search?q={ISBN-13} which returns
full product data in HTML data attributes (no JS rendering needed).
Search is fuzzy so results MUST be filtered by exact ISBN match.

No Cloudflare blocking observed, ~400KB per request, ~300ms response.
"""

import logging
from datetime import datetime

from bs4 import BeautifulSoup

from resell_bot.core.models import Listing
from resell_bot.scrapers.base import BaseScraper
from resell_bot.utils.http_client import HttpClient

logger = logging.getLogger(__name__)

SEARCH_URL = "https://www.recyclivre.com/search"
BASE_URL = "https://www.recyclivre.com"

CONDITION_MAP = {
    "like_new": "comme neuf",
    "very_good": "très bon",
    "good": "bon",
    "acceptable": "acceptable",
}


def _parse_condition(variant_value: str) -> str | None:
    """Extract condition from variant input value like '88467-very_good'."""
    if not variant_value:
        return None
    parts = variant_value.rsplit("-", 1)
    if len(parts) == 2:
        return CONDITION_MAP.get(parts[1])
    return None


class RecyclivreScraper(BaseScraper):
    """RecycLivre scraper via HTML search page."""

    def __init__(self, http_client: HttpClient) -> None:
        self.client = http_client

    @property
    def platform_name(self) -> str:
        return "recyclivre"

    async def get_offer(self, isbn: str) -> Listing | None:
        """Search RecycLivre for a book by ISBN-13.

        Returns the cheapest in-stock Listing, or None.
        """
        try:
            resp = await self.client.get(
                SEARCH_URL,
                params={
                    "q": isbn,
                    "filter[in_stock]": "in_stock",
                    "sorting[price]": "asc",
                    "limit": "5",  # Reduce page size ~60% (162KB vs 384KB)
                },
            )

            if resp.status_code != 200:
                logger.debug("RecycLivre %d for %s", resp.status_code, isbn)
                return None

            soup = BeautifulSoup(resp.text, "lxml")

            # Find all product forms with data attributes
            forms = soup.select("form[data-js-add-to-cart='form']")
            if not forms:
                return None

            # Filter for exact ISBN match (search is fuzzy)
            for form in forms:
                product_isbn = form.get("data-product-id", "")
                if product_isbn != isbn:
                    continue

                price_str = form.get("data-product-price", "")
                if not price_str:
                    continue

                price = float(price_str)
                title = form.get("data-product-name", f"ISBN {isbn}")
                author = form.get("data-product-author") or None
                quantity = int(form.get("data-product-quantity", "0"))

                if quantity <= 0:
                    continue

                # Get condition from variant input
                variant_input = form.select_one(
                    "input[name='sylius_add_to_cart[cartItem][variant]']"
                )
                condition = None
                if variant_input:
                    condition = _parse_condition(variant_input.get("value", ""))

                # Get product URL from parent card
                card = form.find_parent("div", class_="book")
                product_url = ""
                if card:
                    link = card.select_one("a[href^='/products/']")
                    if link:
                        product_url = BASE_URL + link["href"]

                if not product_url:
                    product_url = f"{SEARCH_URL}?q={isbn}"

                logger.info(
                    "RecycLivre: %s — %.2f€ (%s) stock=%d",
                    title, price, condition or "?", quantity,
                )

                return Listing(
                    title=str(title),
                    price=price,
                    url=product_url,
                    platform=self.platform_name,
                    isbn=isbn,
                    condition=condition,
                    seller="RecycLivre",
                    author=author,
                    found_at=datetime.now(),
                )

            return None

        except Exception as e:
            logger.warning("RecycLivre error for %s: %s", isbn, e)
            return None
