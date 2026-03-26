"""Data models for Book Sniper."""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Listing:
    """A book listing found on a platform."""

    title: str
    price: float
    url: str
    platform: str
    isbn: str | None
    condition: str | None  # "neuf", "très bon", "bon", "acceptable"
    seller: str | None
    found_at: datetime
    author: str | None = None
    image_url: str | None = None
    publisher: str | None = None
    pages: int | None = None


@dataclass
class PriceCheck:
    """Cross-platform price comparison for a given ISBN."""

    isbn: str
    buyback_prices: dict[str, float] = field(default_factory=dict)
    market_prices: dict[str, float] = field(default_factory=dict)
    best_margin: float = 0.0
    best_buy_platform: str = ""
    best_sell_platform: str = ""


@dataclass
class Alert:
    """A profitable deal worth notifying about."""

    listing: Listing
    estimated_margin: float
    buyback_price: float
    buyback_platform: str
