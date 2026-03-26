"""Tests for the SQLite database layer."""

from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from resell_bot.core.database import Database
from resell_bot.core.models import Alert, AlertStatus, Listing, ReferencePrice


def _make_listing(url: str = "https://example.com/book/1") -> Listing:
    return Listing(
        title="Fondation",
        price=5.0,
        url=url,
        platform="momox_shop",
        isbn="9782070360550",
        condition="bon",
        seller="Momox",
        found_at=datetime.now(),
    )


class TestDatabase:
    def setup_method(self):
        self._tmpdir = TemporaryDirectory()
        self.db = Database(Path(self._tmpdir.name) / "test.db")

    def teardown_method(self):
        self.db.close()
        self._tmpdir.cleanup()

    # ── Listings ──

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

    # ── Alerts ──

    def test_alert_dedup(self):
        listing = _make_listing()
        self.db.save_listing(listing)
        alert = Alert(listing=listing, max_buy_price=15.0, savings=10.0)
        self.db.save_alert(alert)
        assert self.db.was_recently_alerted(listing.url) is True

    def test_no_recent_alert(self):
        assert self.db.was_recently_alerted("https://nonexistent.com") is False

    def test_save_alert_returns_id(self):
        listing = _make_listing()
        self.db.save_listing(listing)
        alert = Alert(listing=listing, max_buy_price=15.0, savings=10.0)
        alert_id = self.db.save_alert(alert)
        assert isinstance(alert_id, int)
        assert alert_id > 0

    def test_alert_status_default_new(self):
        listing = _make_listing()
        self.db.save_listing(listing)
        alert = Alert(listing=listing, max_buy_price=15.0, savings=10.0)
        self.db.save_alert(alert)
        alerts = self.db.get_alerts()
        assert alerts[0]["status"] == "new"

    def test_update_alert_status(self):
        listing = _make_listing()
        self.db.save_listing(listing)
        alert = Alert(listing=listing, max_buy_price=15.0, savings=10.0)
        alert_id = self.db.save_alert(alert)
        assert self.db.update_alert_status(alert_id, AlertStatus.BOUGHT) is True
        updated = self.db.get_alert_by_id(alert_id)
        assert updated["status"] == "bought"

    def test_get_alerts_filter_by_status(self):
        listing1 = _make_listing("https://a.com/1")
        listing2 = _make_listing("https://a.com/2")
        self.db.save_listing(listing1)
        self.db.save_listing(listing2)
        a1 = Alert(listing=listing1, max_buy_price=15.0, savings=10.0)
        a2 = Alert(listing=listing2, max_buy_price=12.0, savings=7.0)
        self.db.save_alert(a1)
        id2 = self.db.save_alert(a2)
        self.db.update_alert_status(id2, AlertStatus.BOUGHT)

        new_alerts = self.db.get_alerts(status=AlertStatus.NEW)
        bought_alerts = self.db.get_alerts(status=AlertStatus.BOUGHT)
        assert len(new_alerts) == 1
        assert len(bought_alerts) == 1

    def test_get_alert_stats(self):
        listing = _make_listing()
        self.db.save_listing(listing)
        alert = Alert(listing=listing, max_buy_price=15.0, savings=10.0)
        self.db.save_alert(alert)
        stats = self.db.get_alert_stats()
        assert stats["new"] == 1
        assert stats["total"] == 1

    def test_get_alert_by_id_not_found(self):
        assert self.db.get_alert_by_id(999) is None

    def test_alert_has_savings_and_max_buy_price(self):
        listing = _make_listing()
        self.db.save_listing(listing)
        alert = Alert(listing=listing, max_buy_price=15.0, savings=10.0)
        alert_id = self.db.save_alert(alert)
        result = self.db.get_alert_by_id(alert_id)
        assert result["max_buy_price"] == 15.0
        assert result["savings"] == 10.0

    # ── Reference Prices ──

    def test_upsert_reference_price(self):
        ref = ReferencePrice(isbn="9782070360550", max_buy_price=15.0, source="test")
        self.db.upsert_reference_price(ref)
        result = self.db.get_reference_price("9782070360550")
        assert result is not None
        assert result["max_buy_price"] == 15.0
        assert result["source"] == "test"

    def test_upsert_reference_price_updates(self):
        ref1 = ReferencePrice(isbn="9782070360550", max_buy_price=15.0, source="v1")
        self.db.upsert_reference_price(ref1)
        ref2 = ReferencePrice(isbn="9782070360550", max_buy_price=12.0, source="v2")
        self.db.upsert_reference_price(ref2)
        result = self.db.get_reference_price("9782070360550")
        assert result["max_buy_price"] == 12.0
        assert result["source"] == "v2"

    def test_get_reference_price_not_found(self):
        assert self.db.get_reference_price("9999999999999") is None

    def test_bulk_upsert_reference_prices(self):
        refs = [
            ReferencePrice(isbn="9782070360550", max_buy_price=10.0, source="bulk"),
            ReferencePrice(isbn="9782070584628", max_buy_price=20.0, source="bulk"),
            ReferencePrice(isbn="9782253040835", max_buy_price=5.0, source="bulk"),
        ]
        count = self.db.bulk_upsert_reference_prices(refs)
        assert count == 3
        assert self.db.get_reference_price("9782070584628")["max_buy_price"] == 20.0
