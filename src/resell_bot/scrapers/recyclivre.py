"""Scraper stub for recyclivre.com — book buyback platform.

Recyclivre buys used books. The scraper will query their
pricing by ISBN.

TODO: Phase 3 — explore recyclivre.com endpoints, implement.
"""

import logging

from resell_bot.core.models import Listing
from resell_bot.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class RecyclivreScraper(BaseScraper):
    @property
    def platform_name(self) -> str:
        return "recyclivre"

    async def search(self, query: str) -> list[Listing]:
        logger.info("RecyclivreScraper.search() not yet implemented")
        return []

    async def get_price(self, isbn: str) -> float | None:
        logger.info("RecyclivreScraper.get_price() not yet implemented")
        return None
