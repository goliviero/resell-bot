"""Tests for the continuous parallel scan scheduler."""

import asyncio
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from resell_bot.core.database import Database
from resell_bot.core.models import Alert, Listing, ReferencePrice
from resell_bot.scheduler import ScanScheduler


def _make_settings(**overrides) -> dict:
    defaults = {
        "scan": {
            "max_workers": 2,
            "delay_between_requests": {"min_seconds": 0.01, "max_seconds": 0.02},
        },
        "http": {"timeout_seconds": 5, "max_retries": 1},
        "dedup": {"cooldown_hours": 24},
    }
    defaults.update(overrides)
    return defaults


def _make_listing(isbn: str = "9782070360550", price: float = 5.0) -> Listing:
    return Listing(
        title="Test Book",
        price=price,
        url=f"https://www.momox-shop.fr/M0{isbn[-10:]}.html",
        platform="momox_shop",
        isbn=isbn,
        condition="très bon",
        seller="Momox",
        found_at=datetime.now(),
    )


def _insert_ref(db: Database, isbn: str, title: str, max_buy_price: float) -> None:
    ref = ReferencePrice(isbn=isbn, title=title, max_buy_price=max_buy_price, source="test")
    db.upsert_reference_price(ref)


class TestSchedulerInit:
    def test_default_workers(self, tmp_path):
        db = Database(tmp_path / "test.db")
        s = ScanScheduler(_make_settings(), db, None)
        assert s.max_workers == 2
        assert s.delay_min == 0.01
        assert s.delay_max == 0.02
        db.close()

    def test_custom_workers_from_settings(self, tmp_path):
        db = Database(tmp_path / "test.db")
        settings = _make_settings()
        settings["scan"]["max_workers"] = 5
        s = ScanScheduler(settings, db, None)
        assert s.max_workers == 5
        db.close()

    def test_scrapers_list_has_all_platforms(self, tmp_path):
        db = Database(tmp_path / "test.db")
        s = ScanScheduler(_make_settings(), db, None)
        assert len(s.scrapers) == 2
        platforms = [sc.platform_name for sc in s.scrapers]
        assert "momox_shop" in platforms
        assert "recyclivre" in platforms
        db.close()


class TestScanSingle:
    async def test_available_book_updates_availability(self, tmp_path):
        db = Database(tmp_path / "test.db")
        _insert_ref(db, "9782070360550", "Test Book", 50.0)
        s = ScanScheduler(_make_settings(), db, None)

        listing = _make_listing()
        mock_scraper = AsyncMock()
        mock_scraper.platform_name = "momox_shop"
        mock_scraper.get_offer = AsyncMock(return_value=listing)

        alert = await s._scan_single("9782070360550", 50.0, mock_scraper)

        # Should return an alert (price 5€ <= budget 50€)
        assert alert is not None
        assert alert.savings == 45.0

        # Availability should be tracked
        row = db.conn.execute(
            "SELECT status, last_price FROM isbn_availability WHERE isbn=?",
            ("9782070360550",),
        ).fetchone()
        assert row["status"] == "available"
        assert row["last_price"] == 5.0
        db.close()

    async def test_unavailable_book_returns_none(self, tmp_path):
        db = Database(tmp_path / "test.db")
        s = ScanScheduler(_make_settings(), db, None)

        mock_scraper = AsyncMock()
        mock_scraper.platform_name = "momox_shop"
        mock_scraper.get_offer = AsyncMock(return_value=None)

        alert = await s._scan_single("9782070360550", 50.0, mock_scraper)
        assert alert is None

        row = db.conn.execute(
            "SELECT status FROM isbn_availability WHERE isbn=?",
            ("9782070360550",),
        ).fetchone()
        assert row["status"] == "unavailable"
        db.close()

    async def test_price_above_budget_no_alert(self, tmp_path):
        db = Database(tmp_path / "test.db")
        s = ScanScheduler(_make_settings(), db, None)

        listing = _make_listing(price=60.0)
        mock_scraper = AsyncMock()
        mock_scraper.platform_name = "momox_shop"
        mock_scraper.get_offer = AsyncMock(return_value=listing)

        alert = await s._scan_single("9782070360550", 50.0, mock_scraper)
        assert alert is None  # Price 60€ > budget 50€
        db.close()

    async def test_scraper_exception_returns_none(self, tmp_path):
        db = Database(tmp_path / "test.db")
        s = ScanScheduler(_make_settings(), db, None)

        mock_scraper = AsyncMock()
        mock_scraper.platform_name = "momox_shop"
        mock_scraper.get_offer = AsyncMock(side_effect=Exception("Network error"))

        alert = await s._scan_single("9782070360550", 50.0, mock_scraper)
        assert alert is None
        db.close()


class TestProcessAlert:
    async def test_alert_saved_to_db(self, tmp_path):
        db = Database(tmp_path / "test.db")
        s = ScanScheduler(_make_settings(), db, None)

        listing = _make_listing()
        db.save_listing(listing)  # Must exist for JOIN in get_alerts
        alert = Alert(listing=listing, max_buy_price=50.0, savings=45.0)
        await s._process_alert(alert)

        alerts = db.get_alerts()
        assert len(alerts) == 1
        assert alerts[0]["title"] == "Test Book"
        db.close()

    async def test_dedup_blocks_repeat_alert(self, tmp_path):
        db = Database(tmp_path / "test.db")
        s = ScanScheduler(_make_settings(), db, None)

        listing = _make_listing()
        db.save_listing(listing)
        alert = Alert(listing=listing, max_buy_price=50.0, savings=45.0)

        await s._process_alert(alert)
        await s._process_alert(alert)  # Same URL again

        alerts = db.get_alerts()
        assert len(alerts) == 1  # Should be deduped
        db.close()

    async def test_notifier_called_on_alert(self, tmp_path):
        db = Database(tmp_path / "test.db")
        mock_notifier = AsyncMock()
        mock_notifier.send_alert = AsyncMock(return_value=True)
        s = ScanScheduler(_make_settings(), db, mock_notifier)

        listing = _make_listing()
        db.save_listing(listing)
        alert = Alert(listing=listing, max_buy_price=50.0, savings=45.0)
        await s._process_alert(alert)

        mock_notifier.send_alert.assert_called_once_with(alert)
        db.close()


class TestRunOnce:
    async def test_run_once_scans_all_isbns(self, tmp_path):
        db = Database(tmp_path / "test.db")
        _insert_ref(db, "9782070360550", "Book A", 50.0)
        _insert_ref(db, "9782070360024", "Book B", 30.0)
        s = ScanScheduler(_make_settings(), db, None)

        call_count = 0

        async def mock_get_offer(isbn):
            nonlocal call_count
            call_count += 1
            return None

        s.scrapers[0].get_offer = mock_get_offer
        s._running = True

        await s.run_once()
        assert call_count == 2  # Both ISBNs scanned
        db.close()


class TestScanStatus:
    def test_initial_status(self, tmp_path):
        db = Database(tmp_path / "test.db")
        s = ScanScheduler(_make_settings(), db, None)
        assert s.scan_status["momox_shop"]["running"] is False
        assert s.scan_status["momox_shop"]["cycle_count"] == 0
        assert s.scan_status["recyclivre"]["running"] is False
        db.close()
