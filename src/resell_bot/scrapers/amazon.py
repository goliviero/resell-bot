"""Scraper for amazon.fr — used book marketplace.

Amazon has third-party sellers with used book offers.
Priority: P3 — hardest to scrape (aggressive anti-bot).
"""

import logging

from resell_bot.core.models import Listing
from resell_bot.scrapers.base import BaseScraper
from resell_bot.utils.http_client import HttpClient

logger = logging.getLogger(__name__)


class AmazonScraper(BaseScraper):
    def __init__(self, http_client: HttpClient) -> None:
        self.client = http_client

    @property
    def platform_name(self) -> str:
        return "amazon"

    async def get_offer(self, isbn: str) -> Listing | None:
        logger.debug("AmazonScraper.get_offer() not yet implemented")
        return None
