"""Scraper stub for fnac.com marketplace (occasion/reconditionné).

TODO: Phase 5 — explore FNAC SearchResult page, implement.
"""

import logging

from resell_bot.core.models import Listing
from resell_bot.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class FnacScraper(BaseScraper):
    @property
    def platform_name(self) -> str:
        return "fnac"

    async def search(self, query: str) -> list[Listing]:
        logger.info("FnacScraper.search() not yet implemented")
        return []

    async def get_price(self, isbn: str) -> float | None:
        logger.info("FnacScraper.get_price() not yet implemented")
        return None
