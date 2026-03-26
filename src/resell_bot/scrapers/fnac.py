"""Scraper for fnac.com marketplace (occasion/reconditionné).

FNAC sells new and used books via their marketplace.
Priority: P2 — implement after Rakuten + Recyclivre.
"""

import logging

from resell_bot.core.models import Listing
from resell_bot.scrapers.base import BaseScraper
from resell_bot.utils.http_client import HttpClient

logger = logging.getLogger(__name__)


class FnacScraper(BaseScraper):
    def __init__(self, http_client: HttpClient) -> None:
        self.client = http_client

    @property
    def platform_name(self) -> str:
        return "fnac"

    async def get_offer(self, isbn: str) -> Listing | None:
        logger.debug("FnacScraper.get_offer() not yet implemented")
        return None
