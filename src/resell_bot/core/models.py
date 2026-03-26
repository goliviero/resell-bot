"""Data models for resell-bot."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class AlertStatus(str, Enum):
    """Lifecycle of an alert in the dashboard."""

    NEW = "new"
    SEEN = "seen"
    BOUGHT = "bought"
    IGNORED = "ignored"


@dataclass
class Listing:
    """A book listing found on a sale platform."""

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
class ReferencePrice:
    """A book in the watchlist — imported from CaL CSV.

    max_buy_price is the maximum price we're willing to pay.
    The bot scans platforms for listings below this price.
    """

    isbn: str
    max_buy_price: float | None = None
    source: str = ""  # "cal_import", "manual"
    updated_at: datetime | None = None
    title: str | None = None
    author: str | None = None
    url: str | None = None


@dataclass
class Alert:
    """A deal found: a book from the watchlist is available below max buy price."""

    listing: Listing
    max_buy_price: float  # from watchlist — the max we'd pay
    savings: float  # max_buy_price - listing.price
    id: int | None = None
    status: AlertStatus = AlertStatus.NEW
    notified_at: datetime | None = None
