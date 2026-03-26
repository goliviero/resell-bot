"""Tests for the multi-channel notification system."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from resell_bot.core.models import Alert, Listing
from resell_bot.core.notifier import Notifier


def _make_alert(**overrides) -> Alert:
    listing = Listing(
        title="Le Livre Rouge",
        price=5.0,
        url="https://www.momox-shop.fr/M012345.html",
        platform="momox_shop",
        isbn="9782070360550",
        condition="très bon",
        seller="Momox",
        author="Victor Hugo",
        found_at=datetime(2026, 3, 27, 10, 0),
    )
    defaults = {"listing": listing, "max_buy_price": 50.0, "savings": 45.0}
    defaults.update(overrides)
    return Alert(**defaults)


def _make_deals() -> list[dict]:
    return [
        {
            "title": "Le Livre Rouge",
            "author": "Hugo",
            "isbn": "9782070360550",
            "momox_price": 5.0,
            "max_buy_price": 50.0,
            "savings": 45.0,
        },
    ]


class TestNotifierConfig:
    def test_telegram_enabled_with_both(self):
        n = Notifier(bot_token="tok", chat_id="123")
        assert n.telegram_enabled is True

    def test_telegram_disabled_without_token(self):
        n = Notifier(bot_token=None, chat_id="123")
        assert n.telegram_enabled is False

    def test_discord_disabled_by_default(self):
        n = Notifier()
        assert n.discord_enabled is False

    def test_email_disabled_by_default(self):
        n = Notifier()
        assert n.email_enabled is False

    def test_configure_from_settings(self):
        n = Notifier()
        n.configure_from_settings({
            "discord_webhook_url": "https://discord.com/api/webhooks/123/abc",
            "email_to": "test@example.com",
            "smtp_host": "smtp.example.com",
            "smtp_user": "user",
            "smtp_password": "pass",
            "smtp_port": "465",
            "smtp_use_tls": "false",
        })
        assert n.discord_enabled is True
        assert n.email_enabled is True
        assert n.smtp_port == 465
        assert n.smtp_use_tls is False

    def test_configure_empty_strings_treated_as_none(self):
        n = Notifier()
        n.configure_from_settings({"discord_webhook_url": "", "email_to": ""})
        assert n.discord_enabled is False
        assert n.email_enabled is False


class TestNotifierSendAlert:
    @pytest.fixture
    def notifier_telegram(self):
        return Notifier(bot_token="fake_token", chat_id="12345")

    async def test_no_channels_returns_false(self):
        n = Notifier()
        alert = _make_alert()
        result = await n.send_alert(alert)
        assert result is False

    async def test_telegram_alert_success(self, notifier_telegram):
        alert = _make_alert()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with patch("resell_bot.core.notifier.httpx.AsyncClient", return_value=mock_client):
            result = await notifier_telegram.send_alert(alert)

        assert result is True
        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        assert "fake_token" in call_args[0][0]
        assert "Le Livre Rouge" in call_args[1]["json"]["text"]

    async def test_telegram_alert_failure(self, notifier_telegram):
        alert = _make_alert()
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_resp.text = "Forbidden"
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with patch("resell_bot.core.notifier.httpx.AsyncClient", return_value=mock_client):
            result = await notifier_telegram.send_alert(alert)

        assert result is False


class TestNotifierDigest:
    async def test_empty_digest_returns_true(self):
        n = Notifier()
        result = await n.send_digest([])
        assert result is True

    async def test_telegram_digest_sends(self):
        n = Notifier(bot_token="tok", chat_id="123")
        deals = _make_deals()

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with patch("resell_bot.core.notifier.httpx.AsyncClient", return_value=mock_client):
            result = await n.send_digest(deals)

        assert result is True


class TestDiscordNotifier:
    async def test_discord_alert_success(self):
        from resell_bot.core.discord_notifier import send_discord_alert

        alert = _make_alert()
        mock_resp = MagicMock()
        mock_resp.status_code = 204
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with patch("resell_bot.core.discord_notifier.httpx.AsyncClient", return_value=mock_client):
            result = await send_discord_alert("https://discord.com/api/webhooks/1/x", alert)

        assert result is True
        payload = mock_client.post.call_args[1]["json"]
        assert len(payload["embeds"]) == 1
        assert "Le Livre Rouge" in payload["embeds"][0]["title"]

    async def test_discord_alert_http_error(self):
        from resell_bot.core.discord_notifier import send_discord_alert

        alert = _make_alert()
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.text = "Bad Request"
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with patch("resell_bot.core.discord_notifier.httpx.AsyncClient", return_value=mock_client):
            result = await send_discord_alert("https://discord.com/api/webhooks/1/x", alert)

        assert result is False

    async def test_discord_digest_success(self):
        from resell_bot.core.discord_notifier import send_discord_digest

        deals = _make_deals()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with patch("resell_bot.core.discord_notifier.httpx.AsyncClient", return_value=mock_client):
            result = await send_discord_digest("https://discord.com/api/webhooks/1/x", deals)

        assert result is True


class TestEmailNotifier:
    def test_alert_html_build(self):
        from resell_bot.core.email_notifier import _build_alert_html

        alert = _make_alert()
        html = _build_alert_html(alert)
        assert "Le Livre Rouge" in html
        assert "5.00 EUR" in html
        assert "Victor Hugo" in html
        assert "45.00 EUR" in html

    def test_digest_html_build(self):
        from resell_bot.core.email_notifier import _build_digest_html

        deals = _make_deals()
        html = _build_digest_html(deals)
        assert "Le Livre Rouge" in html
        assert "1 bonnes affaires" in html

    @patch("resell_bot.core.email_notifier.smtplib.SMTP")
    def test_send_email_alert_success(self, mock_smtp_class):
        from resell_bot.core.email_notifier import send_email_alert

        mock_server = MagicMock()
        mock_smtp_class.return_value = mock_server

        alert = _make_alert()
        result = send_email_alert("smtp.test.com", 587, "user@test.com", "pass", "to@test.com", alert)

        assert result is True
        mock_server.starttls.assert_called_once()
        mock_server.login.assert_called_once_with("user@test.com", "pass")
        mock_server.sendmail.assert_called_once()
        mock_server.quit.assert_called_once()

    @patch("resell_bot.core.email_notifier.smtplib.SMTP")
    def test_send_email_alert_smtp_error(self, mock_smtp_class):
        from resell_bot.core.email_notifier import send_email_alert

        mock_smtp_class.side_effect = ConnectionRefusedError("SMTP down")

        alert = _make_alert()
        result = send_email_alert("smtp.test.com", 587, "user@test.com", "pass", "to@test.com", alert)

        assert result is False
