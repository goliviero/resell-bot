"""Scraper for ebay.fr — used book marketplace.

eBay has both auction and fixed-price listings.
Priority: P2 — implement after FNAC.
"""

import logging

from resell_bot.core.models import Listing
from resell_bot.scrapers.base import BaseScraper
from resell_bot.utils.http_client import HttpClient

logger = logging.getLogger(__name__)


class EbayScraper(BaseScraper):
    def __init__(self, http_client: HttpClient) -> None:
        self.client = http_client

    @property
    def platform_name(self) -> str:
        return "ebay"

    async def get_offer(self, isbn: str) -> Listing | None:
        logger.debug("EbayScraper.get_offer() not yet implemented")
        return None
