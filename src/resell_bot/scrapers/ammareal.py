"""Scraper for Ammareal — secondhand book marketplace (PrestaShop).

Uses the search page at ammareal.fr/recherche?controller=search&s={ISBN}
which returns product cards in HTML. Search is fuzzy so results MUST be
filtered by exact ISBN match (ISBN appears in product URLs).

No bot protection (PrestaShop vanilla), lightweight pages.
"""

import logging
import re
from datetime import datetime

from bs4 import BeautifulSoup

from resell_bot.core.models import Listing
from resell_bot.scrapers.base import BaseScraper
from resell_bot.utils.http_client import HttpClient

logger = logging.getLogger(__name__)

BASE_URL = "https://www.ammareal.fr"
SEARCH_URL = f"{BASE_URL}/recherche"

CONDITION_MAP = {
    "bon": "bon",
    "très bon": "très bon",
    "comme neuf": "comme neuf",
    "acceptable": "acceptable",
}

# ISBN-13 pattern to extract from product URLs
ISBN13_RE = re.compile(r"(\d{13})")


def _parse_price(price_text: str) -> float | None:
    """Parse price from French format like '3,19 €' to float 3.19."""
    if not price_text:
        return None
    # Strip whitespace, euro sign, and convert comma to dot
    cleaned = price_text.strip().replace("€", "").replace("\xa0", "").strip()
    cleaned = cleaned.replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def _parse_condition(raw: str) -> str | None:
    """Normalize condition text from product card."""
    if not raw:
        return None
    return CONDITION_MAP.get(raw.strip().lower())


class AmmarealScraper(BaseScraper):
    """Ammareal scraper via HTML search page."""

    def __init__(self, http_client: HttpClient) -> None:
        self.client = http_client

    @property
    def platform_name(self) -> str:
        return "ammareal"

    async def get_offer(self, isbn: str) -> Listing | None:
        """Search Ammareal for a book by ISBN-13.

        Returns the cheapest matching Listing, or None.
        """
        try:
            resp = await self.client.get(
                SEARCH_URL,
                params={
                    "controller": "search",
                    "s": isbn,
                    "limit": "5",
                },
            )

            if resp.status_code != 200:
                logger.debug("Ammareal %d for %s", resp.status_code, isbn)
                return None

            soup = BeautifulSoup(resp.text, "lxml")

            # Find all product cards
            cards = soup.select(
                "div.product-miniature.js-product-miniature"
            )
            if not cards:
                return None

            # Collect matching listings, pick cheapest
            best: Listing | None = None

            for card in cards:
                # Check ISBN match via product URL
                link_tag = card.select_one("a.product-miniature__link[href]")
                product_url = link_tag["href"] if link_tag else ""

                # Also check fake-add-to-cart link which may contain ISBN
                fake_link = card.select_one("a.fake-add-to-cart[href]")
                fake_url = fake_link["href"] if fake_link else ""

                # Extract ISBN from URLs
                combined_urls = f"{product_url} {fake_url}"
                isbn_match = ISBN13_RE.search(combined_urls)
                if not isbn_match or isbn_match.group(1) != isbn:
                    continue

                # Parse price
                price_el = card.select_one(".product-miniature__price")
                if not price_el:
                    continue
                price = _parse_price(price_el.get_text())
                if price is None:
                    continue

                # Parse title
                title_el = card.select_one(".product-miniature__name")
                title = title_el.get_text(strip=True) if title_el else f"ISBN {isbn}"

                # Parse author
                author_el = card.select_one(".product-miniature__origin")
                author = author_el.get_text(strip=True) if author_el else None

                # Parse condition
                condition_el = card.select_one(".product-miniature__flag--state")
                condition = _parse_condition(
                    condition_el.get_text(strip=True) if condition_el else ""
                )

                # Build full product URL
                if product_url and not product_url.startswith("http"):
                    product_url = BASE_URL + product_url

                listing = Listing(
                    title=title,
                    price=price,
                    url=product_url,
                    platform=self.platform_name,
                    isbn=isbn,
                    condition=condition,
                    seller="Ammareal",
                    author=author,
                    found_at=datetime.now(),
                )

                if best is None or price < best.price:
                    best = listing

            if best:
                logger.info(
                    "Ammareal: %s — %.2f€ (%s)",
                    best.title, best.price, best.condition or "?",
                )

            return best

        except Exception as e:
            logger.warning("Ammareal error for %s: %s", isbn, e)
            return None
