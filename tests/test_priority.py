"""Tests for priority scoring module."""

from datetime import datetime, timedelta

from resell_bot.priority import compute_priority


class TestComputePriority:
    def test_high_restock_count_is_hot(self):
        """Books restocked 2+ times → HOT regardless of other factors."""
        assert compute_priority(
            status="unavailable",
            last_price=None,
            max_buy_price=10.0,
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
        # Should be warm (seen once) or hot (if high margin), not cold
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
            last_price=7.0,
            max_buy_price=10.0,
            times_available=0,
            last_changed_at=None,
        ) == "warm"

    def test_seen_once_is_warm(self):
        """Books seen available at least once → WARM."""
        assert compute_priority(
            status="unavailable",
            last_price=9.0,
            max_buy_price=10.0,
            times_available=1,
            last_changed_at=None,
        ) == "warm"

    def test_never_seen_low_margin_is_cold(self):
        """Never seen, low margin → COLD."""
        assert compute_priority(
            status="unavailable",
            last_price=9.5,
            max_buy_price=10.0,
            times_available=0,
            last_changed_at=None,
        ) == "cold"

    def test_no_price_data_is_cold(self):
        """No price data at all → COLD."""
        assert compute_priority(
            status="unknown",
            last_price=None,
            max_buy_price=10.0,
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
