"""Scraper for recyclivre.com — used book marketplace.

Recyclivre sells used books at fixed prices.
Priority: P1 — implement after Momox Shop.
"""

import logging

from resell_bot.core.models import Listing
from resell_bot.scrapers.base import BaseScraper
from resell_bot.utils.http_client import HttpClient

logger = logging.getLogger(__name__)


class RecyclivreScraper(BaseScraper):
    def __init__(self, http_client: HttpClient) -> None:
        self.client = http_client

    @property
    def platform_name(self) -> str:
        return "recyclivre"

    async def get_offer(self, isbn: str) -> Listing | None:
        logger.debug("RecyclivreScraper.get_offer() not yet implemented")
        return None
