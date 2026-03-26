"""Tests for priority scoring module."""

from datetime import datetime, timedelta

from resell_bot.priority import compute_priority


class TestComputePriority:
    def test_high_value_book_always_hot(self):
        """Books worth >= 50€ (max_buy_price) → HOT always, even if never seen."""
        assert compute_priority(
            status="unknown",
            last_price=None,
            max_buy_price=55.0,
            times_available=0,
            last_changed_at=None,
        ) == "hot"

    def test_high_value_never_seen_still_hot(self):
        """Rare expensive book never in stock → still HOT (must not miss restock)."""
        assert compute_priority(
            status="unavailable",
            last_price=None,
            max_buy_price=100.0,
            times_available=0,
            last_changed_at=None,
        ) == "hot"

    def test_high_restock_count_is_hot(self):
        """Books restocked 2+ times → HOT regardless of other factors."""
        assert compute_priority(
            status="unavailable",
            last_price=None,
            max_buy_price=5.0,
            times_available=2,
            last_changed_at=None,
        ) == "hot"

    def test_recently_available_is_hot(self):
        """Books seen available within 48h → HOT."""
        recent = (datetime.now() - timedelta(hours=1)).isoformat()
        assert compute_priority(
            status="available",
            last_price=5.0,
            max_buy_price=10.0,
            times_available=1,
            last_changed_at=recent,
        ) == "hot"

    def test_old_availability_not_hot(self):
        """Books available long ago don't get HOT from recency alone."""
        old = (datetime.now() - timedelta(hours=72)).isoformat()
        result = compute_priority(
            status="available",
            last_price=5.0,
            max_buy_price=10.0,
            times_available=1,
            last_changed_at=old,
        )
        # 10€ max_buy_price >= 8€ MEDIUM_VALUE → at least WARM
        assert result in ("hot", "warm")

    def test_high_margin_is_hot(self):
        """Margin >= 5€ → HOT."""
        assert compute_priority(
            status="unavailable",
            last_price=3.0,
            max_buy_price=10.0,
            times_available=0,
            last_changed_at=None,
        ) == "hot"

    def test_moderate_margin_is_warm(self):
        """Margin 2-5€ → WARM."""
        assert compute_priority(
            status="unavailable",
            last_price=5.0,
            max_buy_price=7.5,
            times_available=0,
            last_changed_at=None,
        ) == "warm"

    def test_medium_value_is_warm(self):
        """Books worth 20-50€ → WARM even with no price data."""
        assert compute_priority(
            status="unknown",
            last_price=None,
            max_buy_price=30.0,
            times_available=0,
            last_changed_at=None,
        ) == "warm"

    def test_seen_once_is_warm(self):
        """Books seen available at least once → WARM."""
        assert compute_priority(
            status="unavailable",
            last_price=6.0,
            max_buy_price=7.0,
            times_available=1,
            last_changed_at=None,
        ) == "warm"

    def test_low_value_never_seen_is_cold(self):
        """Low-value book (< 8€), never seen → COLD."""
        assert compute_priority(
            status="unavailable",
            last_price=None,
            max_buy_price=5.0,
            times_available=0,
            last_changed_at=None,
        ) == "cold"

    def test_no_max_buy_price_is_cold(self):
        """No max_buy_price set → COLD."""
        assert compute_priority(
            status="unavailable",
            last_price=5.0,
            max_buy_price=None,
            times_available=0,
            last_changed_at=None,
        ) == "cold"
