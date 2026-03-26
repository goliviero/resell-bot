"""Abstract base class for all platform scrapers."""

from abc import ABC, abstractmethod

from resell_bot.core.models import Listing


class BaseScraper(ABC):
    """Interface for platform scrapers.

    Each scraper checks a single platform (Momox Shop, Rakuten, etc.)
    for book sale prices by ISBN.
    """

    @property
    @abstractmethod
    def platform_name(self) -> str:
        """Unique platform identifier (e.g. 'momox_shop')."""
        ...

    @abstractmethod
    async def get_offer(self, isbn: str) -> Listing | None:
        """Check if a book is available for sale on this platform.

        Returns a Listing with price/URL/condition, or None if not available.
        """
        ...

    async def search(self, query: str) -> list[Listing]:
        """Optional: search for books by keyword. Not all platforms need this."""
        return []
