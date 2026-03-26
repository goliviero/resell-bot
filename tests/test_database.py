"""Tests for the SQLite database layer."""

from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from resell_bot.core.database import Database
from resell_bot.core.models import Alert, Listing


def _make_listing(url: str = "https://example.com/book/1") -> Listing:
    return Listing(
        title="Fondation",
        price=5.0,
        url=url,
        platform="test",
        isbn="9782070360550",
        condition="bon",
        seller="Vendeur",
        found_at=datetime.now(),
    )


class TestDatabase:
    def setup_method(self):
        self._tmpdir = TemporaryDirectory()
        self.db = Database(Path(self._tmpdir.name) / "test.db")

    def teardown_method(self):
        self.db.close()
        self._tmpdir.cleanup()

    def test_save_listing_new(self):
        assert self.db.save_listing(_make_listing()) is True

    def test_save_listing_duplicate(self):
        listing = _make_listing()
        self.db.save_listing(listing)
        assert self.db.save_listing(listing) is False

    def test_get_listings_by_isbn(self):
        self.db.save_listing(_make_listing("https://a.com/1"))
        self.db.save_listing(_make_listing("https://a.com/2"))
        results = self.db.get_listings_by_isbn("9782070360550")
        assert len(results) == 2

    def test_alert_dedup(self):
        listing = _make_listing()
        self.db.save_listing(listing)
        alert = Alert(listing=listing, estimated_margin=5.0, buyback_price=13.0, buyback_platform="momox")
        self.db.save_alert(alert)
        assert self.db.was_recently_alerted(listing.url) is True

    def test_no_recent_alert(self):
        assert self.db.was_recently_alerted("https://nonexistent.com") is False
