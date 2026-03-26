"""SQLite database for listings, alerts, and dedup tracking."""

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from resell_bot.core.models import Alert, Listing

DB_SCHEMA = """
CREATE TABLE IF NOT EXISTS listings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    price REAL NOT NULL,
    url TEXT NOT NULL UNIQUE,
    platform TEXT NOT NULL,
    isbn TEXT,
    condition TEXT,
    seller TEXT,
    author TEXT,
    found_at TEXT NOT NULL,
    image_url TEXT
);

CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_url TEXT NOT NULL,
    estimated_margin REAL NOT NULL,
    buyback_price REAL NOT NULL,
    buyback_platform TEXT NOT NULL,
    notified_at TEXT NOT NULL,
    FOREIGN KEY (listing_url) REFERENCES listings(url)
);

CREATE INDEX IF NOT EXISTS idx_listings_isbn ON listings(isbn);
CREATE INDEX IF NOT EXISTS idx_listings_url ON listings(url);
CREATE INDEX IF NOT EXISTS idx_alerts_listing_url ON alerts(listing_url);
"""


class Database:
    """Thin wrapper around sqlite3 for Book Sniper storage."""

    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self.conn.executescript(DB_SCHEMA)
        self.conn.commit()

    def save_listing(self, listing: Listing) -> bool:
        """Insert a listing. Returns True if new, False if duplicate (same URL)."""
        try:
            self.conn.execute(
                """INSERT INTO listings
                   (title, price, url, platform, isbn, condition, seller, author, found_at, image_url)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    listing.title,
                    listing.price,
                    listing.url,
                    listing.platform,
                    listing.isbn,
                    listing.condition,
                    listing.seller,
                    listing.author,
                    listing.found_at.isoformat(),
                    listing.image_url,
                ),
            )
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def save_alert(self, alert: Alert) -> None:
        """Record a sent alert for dedup tracking."""
        self.conn.execute(
            """INSERT INTO alerts (listing_url, estimated_margin, buyback_price, buyback_platform, notified_at)
               VALUES (?, ?, ?, ?, ?)""",
            (
                alert.listing.url,
                alert.estimated_margin,
                alert.buyback_price,
                alert.buyback_platform,
                datetime.now().isoformat(),
            ),
        )
        self.conn.commit()

    def was_recently_alerted(self, url: str, cooldown_hours: int = 24) -> bool:
        """Check if we already sent an alert for this URL within the cooldown."""
        cutoff = (datetime.now() - timedelta(hours=cooldown_hours)).isoformat()
        row = self.conn.execute(
            "SELECT 1 FROM alerts WHERE listing_url = ? AND notified_at > ?",
            (url, cutoff),
        ).fetchone()
        return row is not None

    def get_listings_by_isbn(self, isbn: str) -> list[dict]:
        """Retrieve all listings for a given ISBN."""
        rows = self.conn.execute(
            "SELECT * FROM listings WHERE isbn = ? ORDER BY price ASC",
            (isbn,),
        ).fetchall()
        return [dict(r) for r in rows]

    def close(self) -> None:
        self.conn.close()
