"""Scraper stub for momox.fr — book buyback platform.

Momox buys used books at fixed prices. The scraper will query their
pricing endpoint by ISBN to get buyback offers.

TODO: Phase 2 — explore momox.fr API endpoints via curl, implement.
"""

import logging

from resell_bot.core.models import Listing
from resell_bot.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class MomoxScraper(BaseScraper):
    @property
    def platform_name(self) -> str:
        return "momox"

    async def search(self, query: str) -> list[Listing]:
        logger.info("MomoxScraper.search() not yet implemented")
        return []

    async def get_price(self, isbn: str) -> float | None:
        logger.info("MomoxScraper.get_price() not yet implemented")
        return None
