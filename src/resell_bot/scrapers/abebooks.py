"""Scraper for AbeBooks — international used book marketplace.

Uses the search servlet which returns structured schema.org microdata
(price, condition, availability, ISBN in <meta> tags). No bot protection.

Search sorted by price ascending (sortby=1). Multi-vendor per ISBN.
"""

import logging
from datetime import datetime

from bs4 import BeautifulSoup

from resell_bot.core.models import Listing
from resell_bot.scrapers.base import BaseScraper
from resell_bot.utils.http_client import HttpClient

logger = logging.getLogger(__name__)

BASE_URL = "https://www.abebooks.fr"
SEARCH_URL = f"{BASE_URL}/servlet/SearchResults"

# AbeBooks uses schema.org itemCondition values
CONDITION_MAP = {
    "NewCondition": "neuf",
    "UsedCondition": "occasion",
    "RefurbishedCondition": "reconditionné",
}


class AbebooksScraper(BaseScraper):
    """AbeBooks scraper via HTML search with schema.org microdata."""

    def __init__(self, http_client: HttpClient) -> None:
        self.client = http_client

    @property
    def platform_name(self) -> str:
        return "abebooks"

    async def get_offer(self, isbn: str) -> Listing | None:
        """Search AbeBooks for a book by ISBN.

        Returns the cheapest available Listing, or None.
        Results are sorted by price ascending (sortby=1).
        """
        try:
            resp = await self.client.get(
                SEARCH_URL,
                params={
                    "kn": isbn,
                    "sortby": "1",  # Price ascending
                },
            )

            if resp.status_code != 200:
                logger.debug("AbeBooks %d for %s", resp.status_code, isbn)
                return None

            soup = BeautifulSoup(resp.text, "lxml")
            items = soup.select(".result-item")
            if not items:
                return None

            # Find cheapest matching item (already sorted by price)
            for item in items:
                # Verify ISBN match via schema.org meta
                isbn_meta = item.select_one("meta[itemprop=isbn]")
                if not isbn_meta or isbn_meta.get("content") != isbn:
                    continue

                # Extract offer data from schema.org microdata
                offer = item.select_one("[itemtype*=Offer]")
                if not offer:
                    continue

                price_meta = offer.select_one("meta[itemprop=price]")
                if not price_meta:
                    continue
                try:
                    price = float(price_meta["content"])
                except (ValueError, KeyError):
                    continue

                # Check availability
                avail_meta = offer.select_one("meta[itemprop=availability]")
                if avail_meta and avail_meta.get("content") != "InStock":
                    continue

                # Condition
                cond_meta = offer.select_one("meta[itemprop=itemCondition]")
                condition = CONDITION_MAP.get(
                    cond_meta["content"] if cond_meta else "", None
                )

                # Title
                title_el = item.select_one("[data-test-id=listing-title]")
                title = title_el.get_text(strip=True) if title_el else f"ISBN {isbn}"

                # Author
                author_meta = item.select_one("meta[itemprop=author]")
                author = author_meta["content"] if author_meta else None

                # Seller
                seller_el = item.select_one(".bookseller-info a")
                seller = seller_el.get_text(strip=True) if seller_el else "AbeBooks"

                # Product URL
                link = offer.select_one("a[itemprop=url]")
                product_url = BASE_URL + link["href"] if link else SEARCH_URL

                logger.info(
                    "AbeBooks: %s — %.2f€ (%s) seller=%s",
                    title[:50], price, condition or "?", seller[:20],
                )

                return Listing(
                    title=str(title),
                    price=price,
                    url=product_url,
                    platform=self.platform_name,
                    isbn=isbn,
                    condition=condition,
                    seller=seller,
                    author=author,
                    found_at=datetime.now(),
                )

            return None

        except Exception as e:
            logger.warning("AbeBooks error for %s: %s", isbn, e)
            return None
