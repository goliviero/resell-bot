"""Abstract base class for all scrapers."""

from abc import ABC, abstractmethod

from resell_bot.core.models import Listing


class BaseScraper(ABC):
    """Interface commune pour tous les scrapers."""

    @property
    @abstractmethod
    def platform_name(self) -> str:
        """Unique platform identifier (e.g. 'chasseauxlivres')."""
        ...

    @abstractmethod
    async def search(self, query: str) -> list[Listing]:
        """Search for books matching a keyword query."""
        ...

    @abstractmethod
    async def get_price(self, isbn: str) -> float | None:
        """Get the best price for a given ISBN on this platform."""
        ...
