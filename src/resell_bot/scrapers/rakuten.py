"""Scraper stub for fr.shopping.rakuten.com (ex-PriceMinister).

TODO: Phase 4 — explore Rakuten search + occasion listings, implement.
"""

import logging

from resell_bot.core.models import Listing
from resell_bot.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class RakutenScraper(BaseScraper):
    @property
    def platform_name(self) -> str:
        return "rakuten"

    async def search(self, query: str) -> list[Listing]:
        logger.info("RakutenScraper.search() not yet implemented")
        return []

    async def get_price(self, isbn: str) -> float | None:
        logger.info("RakutenScraper.get_price() not yet implemented")
        return None
