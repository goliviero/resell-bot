"""Tests for the multi-channel notification system (Discord + Email)."""

from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from resell_bot.core.database import Database
from resell_bot.core.models import Alert, Listing
from resell_bot.core.notifier import Notifier


def _make_alert() -> Alert:
    listing = Listing(
        title="Test Book",
        price=5.0,
        url="https://www.momox-shop.fr/M02070360557.html",
        platform="momox_shop",
        isbn="9782070360550",
        condition="très bon",
        seller="Momox",
        found_at=datetime.now(),
    )
    return Alert(listing=listing, max_buy_price=50.0, savings=45.0)


class TestNotifierConfig:
    def test_no_channels_by_default(self, tmp_path):
        db = Database(tmp_path / "test.db")
        n = Notifier(db)
        n.reload_channels()
        assert not n.discord_enabled
        assert not n.email_enabled
        assert not n.any_enabled
        db.close()

    def test_discord_enabled_after_adding_webhook(self, tmp_path):
        db = Database(tmp_path / "test.db")
        db.add_discord_webhook("test", "https://discord.com/api/webhooks/123/abc")
        n = Notifier(db)
        n.reload_channels()
        assert n.discord_enabled
        assert n.any_enabled
        db.close()

    def test_multiple_webhooks(self, tmp_path):
        db = Database(tmp_path / "test.db")
        db.add_discord_webhook("wh1", "https://discord.com/api/webhooks/111/aaa")
        db.add_discord_webhook("wh2", "https://discord.com/api/webhooks/222/bbb")
        n = Notifier(db)
        n.reload_channels()
        assert len(n._discord_webhooks) == 2
        db.close()

    def test_disabled_webhook_not_loaded(self, tmp_path):
        db = Database(tmp_path / "test.db")
        wh_id = db.add_discord_webhook("test", "https://discord.com/api/webhooks/123/abc")
        db.toggle_discord_webhook(wh_id, False)
        n = Notifier(db)
        n.reload_channels()
        assert not n.discord_enabled
        db.close()

    def test_email_enabled_after_adding_config(self, tmp_path):
        db = Database(tmp_path / "test.db")
        db.add_email_config("test", "a@b.com", "smtp.test.com", 587, "user", "pass")
        n = Notifier(db)
        n.reload_channels()
        assert n.email_enabled
        assert n.any_enabled
        db.close()

    def test_status_summary(self, tmp_path):
        db = Database(tmp_path / "test.db")
        db.add_discord_webhook("Alertes", "https://discord.com/api/webhooks/1/a")
        db.add_email_config("Gmail", "a@b.com", "smtp.test.com", 587, "user", "pass")
        n = Notifier(db)
        n.reload_channels()
        summary = n.get_status_summary()
        assert "Discord (Alertes)" in summary
        assert "Email (Gmail)" in summary
        db.close()


class TestNotifierSendAlert:
    async def test_no_channels_returns_false(self, tmp_path):
        db = Database(tmp_path / "test.db")
        n = Notifier(db)
        result = await n.send_alert(_make_alert())
        assert result is False
        db.close()

    @patch("resell_bot.core.notifier.send_discord_alert", new_callable=AsyncMock, return_value=True)
    async def test_sends_to_all_webhooks(self, mock_discord, tmp_path):
        db = Database(tmp_path / "test.db")
        db.add_discord_webhook("wh1", "https://discord.com/api/webhooks/111/aaa")
        db.add_discord_webhook("wh2", "https://discord.com/api/webhooks/222/bbb")
        n = Notifier(db)
        result = await n.send_alert(_make_alert())
        assert result is True
        assert mock_discord.call_count == 2
        db.close()

    @patch("resell_bot.core.notifier.send_discord_alert", new_callable=AsyncMock, return_value=False)
    async def test_discord_failure_returns_false(self, mock_discord, tmp_path):
        db = Database(tmp_path / "test.db")
        db.add_discord_webhook("wh1", "https://discord.com/api/webhooks/111/aaa")
        n = Notifier(db)
        result = await n.send_alert(_make_alert())
        assert result is False
        db.close()

    @patch("resell_bot.core.notifier.send_email_alert", return_value=True)
    async def test_sends_to_all_emails(self, mock_email, tmp_path):
        db = Database(tmp_path / "test.db")
        db.add_email_config("e1", "a@b.com", "smtp.test.com", 587, "user", "pass")
        db.add_email_config("e2", "c@d.com", "smtp.test.com", 587, "user", "pass")
        n = Notifier(db)
        result = await n.send_alert(_make_alert())
        assert result is True
        assert mock_email.call_count == 2
        db.close()


class TestNotifierDigest:
    async def test_empty_digest_returns_true(self, tmp_path):
        db = Database(tmp_path / "test.db")
        n = Notifier(db)
        result = await n.send_digest([])
        assert result is True
        db.close()

    @patch("resell_bot.core.notifier.send_discord_digest", new_callable=AsyncMock, return_value=True)
    async def test_digest_sent_to_webhooks(self, mock_digest, tmp_path):
        db = Database(tmp_path / "test.db")
        db.add_discord_webhook("wh1", "https://discord.com/api/webhooks/111/aaa")
        n = Notifier(db)
        deals = [{"title": "Book", "momox_price": 5.0, "max_buy_price": 50.0, "savings": 45.0, "isbn": "123"}]
        result = await n.send_digest(deals)
        assert result is True
        mock_digest.assert_called_once()
        db.close()


class TestDiscordWebhookDB:
    def test_add_and_get(self, tmp_path):
        db = Database(tmp_path / "test.db")
        wh_id = db.add_discord_webhook("test", "https://discord.com/api/webhooks/123/abc")
        webhooks = db.get_discord_webhooks()
        assert len(webhooks) == 1
        assert webhooks[0]["name"] == "test"
        assert webhooks[0]["id"] == wh_id
        db.close()

    def test_delete(self, tmp_path):
        db = Database(tmp_path / "test.db")
        wh_id = db.add_discord_webhook("test", "https://discord.com/api/webhooks/123/abc")
        db.delete_discord_webhook(wh_id)
        assert len(db.get_discord_webhooks()) == 0
        db.close()

    def test_toggle(self, tmp_path):
        db = Database(tmp_path / "test.db")
        wh_id = db.add_discord_webhook("test", "https://discord.com/api/webhooks/123/abc")
        db.toggle_discord_webhook(wh_id, False)
        assert db.get_discord_webhooks(enabled_only=True) == []
        db.toggle_discord_webhook(wh_id, True)
        assert len(db.get_discord_webhooks(enabled_only=True)) == 1
        db.close()

    def test_duplicate_url_rejected(self, tmp_path):
        db = Database(tmp_path / "test.db")
        db.add_discord_webhook("wh1", "https://discord.com/api/webhooks/123/abc")
        with pytest.raises(Exception):
            db.add_discord_webhook("wh2", "https://discord.com/api/webhooks/123/abc")
        db.close()


class TestEmailConfigDB:
    def test_add_and_get(self, tmp_path):
        db = Database(tmp_path / "test.db")
        ec_id = db.add_email_config("Gmail", "a@b.com", "smtp.gmail.com", 587, "user", "pass")
        configs = db.get_email_configs()
        assert len(configs) == 1
        assert configs[0]["label"] == "Gmail"
        assert configs[0]["id"] == ec_id
        db.close()

    def test_delete(self, tmp_path):
        db = Database(tmp_path / "test.db")
        ec_id = db.add_email_config("Gmail", "a@b.com", "smtp.gmail.com", 587, "user", "pass")
        db.delete_email_config(ec_id)
        assert len(db.get_email_configs()) == 0
        db.close()

    def test_toggle(self, tmp_path):
        db = Database(tmp_path / "test.db")
        ec_id = db.add_email_config("Gmail", "a@b.com", "smtp.gmail.com", 587, "user", "pass")
        db.toggle_email_config(ec_id, False)
        assert db.get_email_configs(enabled_only=True) == []
        db.toggle_email_config(ec_id, True)
        assert len(db.get_email_configs(enabled_only=True)) == 1
        db.close()
