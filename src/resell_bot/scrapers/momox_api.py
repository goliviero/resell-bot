"""Scraper for Momox Shop via the Medimops backend API.

Uses the internal JSON API at api.medimops.de/v1/search to fetch
shop sale prices and stock availability — much faster than HTML scraping
(~80ms vs ~2s per request) and no Cloudflare challenge.

The API returns marketplace-specific data including:
- bestPrice: cheapest available price on momox-shop.fr
- stock: total units available
- variants: per-condition pricing (UsedVeryGood, UsedGood, etc.)
"""

import logging
from datetime import datetime

from resell_bot.core.models import Listing
from resell_bot.scrapers.base import BaseScraper
from resell_bot.utils.http_client import HttpClient

logger = logging.getLogger(__name__)

MEDIMOPS_API = "https://api.medimops.de/v1"
MARKETPLACE_ID = "fra"
SHOP_BASE_URL = "https://www.momox-shop.fr"

CONDITION_MAP = {
    "UsedLikeNew": "comme neuf",
    "UsedVeryGood": "très bon",
    "UsedGood": "bon",
    "UsedAcceptable": "acceptable",
    "New": "neuf",
    "LibriNew": "neuf",
}


class MomoxApiScraper(BaseScraper):
    """Fast Momox Shop scraper via Medimops JSON API."""

    def __init__(self, http_client: HttpClient) -> None:
        self.client = http_client

    @property
    def platform_name(self) -> str:
        return "momox_shop"

    async def get_offer(self, isbn: str) -> Listing | None:
        """Check Momox Shop availability and price via API.

        Returns a Listing with the cheapest available offer, or None.
        """
        try:
            resp = await self.client.get(
                f"{MEDIMOPS_API}/search",
                params={"q": isbn, "marketplace_id": MARKETPLACE_ID},
                extra_headers={"Accept": "application/json"},
            )

            if resp.status_code != 200:
                logger.debug("Medimops API %d for %s", resp.status_code, isbn)
                return None

            data = resp.json()
            products = data.get("data", {}).get("products", [])
            if not products:
                return None

            product = products[0]
            attrs = product.get("attributes", {})

            # Find FRA marketplace data
            marketplace_data = attrs.get("marketplaceData", [])
            fra = next(
                (m for m in marketplace_data if m["marketplaceId"] == "FRA"),
                None,
            )
            if not fra:
                return None

            shop = fra["data"]
            best_price = shop.get("bestPrice")
            stock = shop.get("stock", 0)

            if not best_price or stock <= 0:
                return None

            # Get condition from best variant
            best_variant = shop.get("bestAvailableVariant", {})
            variant_type = best_variant.get("variantType", "")
            condition = CONDITION_MAP.get(variant_type)

            # Build product URL — always use MPID format (webPath from API gives 404)
            mpid = attrs.get("mpid", "")
            product_url = f"{SHOP_BASE_URL}/{mpid}.html" if mpid else f"{SHOP_BASE_URL}"

            title = attrs.get("name", f"ISBN {isbn}")
            author = attrs.get("manufacturer", {}).get("name")
            image_url = attrs.get("imageUrl")

            logger.info(
                "Momox API: %s — %.2f€ (%s) stock=%d",
                title, best_price, condition or "?", stock,
            )

            return Listing(
                title=str(title),
                price=float(best_price),
                url=product_url,
                platform=self.platform_name,
                isbn=isbn,
                condition=condition,
                seller="Momox",
                author=author,
                found_at=datetime.now(),
                image_url=image_url,
            )

        except Exception as e:
            logger.warning("Momox API error for %s: %s", isbn, e)
            return None

    async def check_availability(self, isbn: str) -> dict | None:
        """Lightweight availability check — returns stock info without building a Listing.

        Returns dict with keys: isbn, in_stock, best_price, stock, condition
        or None on error.
        """
        try:
            resp = await self.client.get(
                f"{MEDIMOPS_API}/search",
                params={"q": isbn, "marketplace_id": MARKETPLACE_ID},
                extra_headers={"Accept": "application/json"},
            )

            if resp.status_code != 200:
                return None

            data = resp.json()
            products = data.get("data", {}).get("products", [])
            if not products:
                return {"isbn": isbn, "in_stock": False, "best_price": None, "stock": 0, "condition": None}

            attrs = products[0].get("attributes", {})
            marketplace_data = attrs.get("marketplaceData", [])
            fra = next(
                (m for m in marketplace_data if m["marketplaceId"] == "FRA"),
                None,
            )
            if not fra:
                return {"isbn": isbn, "in_stock": False, "best_price": None, "stock": 0, "condition": None}

            shop = fra["data"]
            best_price = shop.get("bestPrice")
            stock = shop.get("stock", 0)
            best_variant = shop.get("bestAvailableVariant", {})
            condition = CONDITION_MAP.get(best_variant.get("variantType", ""))

            return {
                "isbn": isbn,
                "in_stock": bool(best_price and stock > 0),
                "best_price": float(best_price) if best_price else None,
                "stock": stock,
                "condition": condition,
            }

        except Exception as e:
            logger.warning("Momox API availability check error for %s: %s", isbn, e)
            return None
