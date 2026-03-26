"""Stub scrapers for platforms not yet implemented.

Each platform will get its own file when implemented.
See docs/SWOT.md for scraping feasibility per platform.
"""

import logging

from resell_bot.core.models import Listing
from resell_bot.scrapers.base import BaseScraper
from resell_bot.utils.http_client import HttpClient

logger = logging.getLogger(__name__)


def _make_stub(name: str) -> type:
    """Generate a stub scraper class for an unimplemented platform."""

    class StubScraper(BaseScraper):
        def __init__(self, http_client: HttpClient) -> None:
            self.client = http_client

        @property
        def platform_name(self) -> str:
            return name

        async def get_offer(self, isbn: str) -> Listing | None:
            return None

    StubScraper.__name__ = f"{name.title()}Scraper"
    StubScraper.__qualname__ = StubScraper.__name__
    return StubScraper


# P1 — Easy/Medium
RecyclivreScraper = _make_stub("recyclivre")
RakutenScraper = _make_stub("rakuten")

# P2 — Medium/Hard
EbayScraper = _make_stub("ebay")
FnacScraper = _make_stub("fnac")

# P3 — Very Hard
AmazonScraper = _make_stub("amazon")
