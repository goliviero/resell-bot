"""Scraper for momox-shop.fr — Momox's used book shop.

Momox sells used books at fixed prices on momox-shop.fr.
Product pages are accessed via MPID: M0{isbn10}.

Price is extracted from the HTML data-cnstrc-item-price attribute.
Uses curl_cffi to bypass Cloudflare TLS fingerprinting.
"""

import logging
from datetime import datetime

from bs4 import BeautifulSoup

from resell_bot.core.models import Listing
from resell_bot.scrapers.base import BaseScraper
from resell_bot.utils.http_client import HttpClient
from resell_bot.utils.isbn import isbn13_to_isbn10

logger = logging.getLogger(__name__)

SHOP_URL = "https://www.momox-shop.fr"


def _isbn_to_mpid(isbn: str) -> str | None:
    """Convert ISBN-13 to Momox Product ID (M0 + ISBN-10)."""
    clean = isbn.replace("-", "").strip()
    if len(clean) == 10:
        return f"M0{clean}"
    if len(clean) == 13:
        isbn10 = isbn13_to_isbn10(clean)
        if isbn10:
            return f"M0{isbn10}"
    return None


class MomoxShopScraper(BaseScraper):
    """Scraper for momox-shop.fr sale prices."""

    def __init__(self, http_client: HttpClient) -> None:
        self.client = http_client

    @property
    def platform_name(self) -> str:
        return "momox_shop"

    async def get_offer(self, isbn: str) -> Listing | None:
        """Check if Momox Shop sells this book and at what price.

        Returns a Listing with the best available price, or None.
        """
        mpid = _isbn_to_mpid(isbn)
        if not mpid:
            logger.debug("Cannot convert ISBN %s to MPID", isbn)
            return None

        product_url = f"{SHOP_URL}/{mpid}.html"

        try:
            resp = await self.client.get(product_url)

            # 404 or redirect to search = not available
            if resp.status_code != 200:
                logger.debug("Momox Shop %d for %s", resp.status_code, isbn)
                return None

            soup = BeautifulSoup(resp.text, "lxml")

            # Extract price from data-cnstrc-item-price attribute
            price_el = soup.find(attrs={"data-cnstrc-item-price": True})
            if not price_el:
                logger.debug("No price element found for %s", isbn)
                return None

            price = float(price_el["data-cnstrc-item-price"])
            if price <= 0:
                return None

            # Extract title
            title_el = soup.find(attrs={"data-cnstrc-item-name": True})
            title = title_el["data-cnstrc-item-name"] if title_el else f"ISBN {isbn}"

            # Extract condition from variant ID (e.g. M0xxx_UsedVeryGood)
            condition = None
            variant_el = soup.find(attrs={"data-cnstrc-item-variation-id": True})
            if variant_el:
                variant_id = variant_el["data-cnstrc-item-variation-id"]
                condition = _parse_condition(variant_id)

            # Get actual product URL (may have been redirected with SEO slug)
            final_url = str(resp.url) if hasattr(resp, 'url') and resp.url else product_url

            logger.info("Momox Shop: %s — %.2f€ (%s)", title, price, condition or "?")

            return Listing(
                title=str(title),
                price=price,
                url=final_url,
                platform=self.platform_name,
                isbn=isbn,
                condition=condition,
                seller="Momox",
                found_at=datetime.now(),
            )

        except Exception as e:
            logger.warning("Momox Shop error for %s: %s", isbn, e)
            return None


def _parse_condition(variant_id: str) -> str | None:
    """Extract human-readable condition from Momox variant ID."""
    conditions = {
        "UsedLikeNew": "comme neuf",
        "UsedVeryGood": "très bon",
        "UsedGood": "bon",
        "UsedAcceptable": "acceptable",
        "New": "neuf",
        "LibriNew": "neuf",
    }
    for key, label in conditions.items():
        if key in variant_id:
            return label
    return None
