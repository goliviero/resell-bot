"""Multi-channel notification hub — Telegram, Discord, Email."""

import logging

import httpx

from resell_bot.core.discord_notifier import send_discord_alert, send_discord_digest
from resell_bot.core.email_notifier import send_email_alert, send_email_digest
from resell_bot.core.models import Alert

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"

MESSAGE_TEMPLATE = """📚 BONNE AFFAIRE détectée !

{title}
{author_line}ISBN: {isbn}

💰 Prix: {price:.2f}€ sur {platform}
📊 Budget max: {max_buy_price:.2f}€
💵 Économie: {savings:.2f}€

🔗 {url}

⏰ {timestamp}"""


class Notifier:
    """Sends alerts to Telegram + Discord + Email based on configured settings."""

    def __init__(self, bot_token: str | None = None, chat_id: str | None = None) -> None:
        self.bot_token = bot_token
        self.chat_id = chat_id
        # These are set dynamically from DB notification_settings
        self.discord_webhook_url: str | None = None
        self.email_to: str | None = None
        self.smtp_host: str | None = None
        self.smtp_port: int = 587
        self.smtp_user: str | None = None
        self.smtp_password: str | None = None
        self.smtp_use_tls: bool = True

    def configure_from_settings(self, settings: dict[str, str]) -> None:
        """Load notification channels from DB settings dict."""
        self.discord_webhook_url = settings.get("discord_webhook_url") or None
        self.email_to = settings.get("email_to") or None
        self.smtp_host = settings.get("smtp_host") or None
        self.smtp_port = int(settings.get("smtp_port", "587"))
        self.smtp_user = settings.get("smtp_user") or None
        self.smtp_password = settings.get("smtp_password") or None
        self.smtp_use_tls = settings.get("smtp_use_tls", "true").lower() == "true"

    @property
    def telegram_enabled(self) -> bool:
        return bool(self.bot_token and self.chat_id)

    @property
    def discord_enabled(self) -> bool:
        return bool(self.discord_webhook_url)

    @property
    def email_enabled(self) -> bool:
        return bool(self.email_to and self.smtp_host and self.smtp_user and self.smtp_password)

    async def send_alert(self, alert: Alert) -> bool:
        """Send a deal alert to all configured channels. Returns True if at least one succeeded."""
        results = []

        if self.telegram_enabled:
            results.append(await self._send_telegram_alert(alert))

        if self.discord_enabled:
            results.append(await send_discord_alert(self.discord_webhook_url, alert))

        if self.email_enabled:
            results.append(send_email_alert(
                self.smtp_host, self.smtp_port, self.smtp_user, self.smtp_password,
                self.email_to, alert, self.smtp_use_tls,
            ))

        if not results:
            logger.debug("No notification channels configured — alert not sent")
            return False

        return any(results)

    async def send_digest(self, deals: list[dict]) -> bool:
        """Send daily digest to all configured channels. Returns True if at least one succeeded."""
        if not deals:
            logger.info("No deals for daily digest — skipping")
            return True

        results = []

        if self.telegram_enabled:
            results.append(await self._send_telegram_digest(deals))

        if self.discord_enabled:
            results.append(await send_discord_digest(self.discord_webhook_url, deals))

        if self.email_enabled:
            results.append(send_email_digest(
                self.smtp_host, self.smtp_port, self.smtp_user, self.smtp_password,
                self.email_to, deals, self.smtp_use_tls,
            ))

        return any(results) if results else False

    async def send_message(self, text: str) -> bool:
        """Send a raw text message to Telegram."""
        if not self.telegram_enabled:
            return False
        url = TELEGRAM_API.format(token=self.bot_token)
        payload = {"chat_id": self.chat_id, "text": text}
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(url, json=payload, timeout=10)
                return resp.status_code == 200
        except httpx.HTTPError as e:
            logger.error("Telegram send failed: %s", e)
            return False

    # ── Telegram internals ────────────────────────────────────

    async def _send_telegram_alert(self, alert: Alert) -> bool:
        """Send deal alert to Telegram."""
        author_line = f"Auteur: {alert.listing.author}\n" if alert.listing.author else ""
        text = MESSAGE_TEMPLATE.format(
            title=alert.listing.title,
            author_line=author_line,
            isbn=alert.listing.isbn or "inconnu",
            price=alert.listing.price,
            platform=alert.listing.platform,
            max_buy_price=alert.max_buy_price,
            savings=alert.savings,
            url=alert.listing.url,
            timestamp=alert.listing.found_at.strftime("%Y-%m-%d %H:%M"),
        )

        url = TELEGRAM_API.format(token=self.bot_token)
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "disable_web_page_preview": False,
        }

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(url, json=payload, timeout=10)
                if resp.status_code == 200:
                    logger.info("Telegram alert sent: %s", alert.listing.title)
                    return True
                logger.warning("Telegram API error %d: %s", resp.status_code, resp.text)
                return False
        except httpx.HTTPError as e:
            logger.error("Telegram send failed: %s", e)
            return False

    async def _send_telegram_digest(self, deals: list[dict]) -> bool:
        """Send daily digest to Telegram."""
        lines = [f"📋 Recap journalier — {len(deals)} bonnes affaires\n"]
        total_savings = 0.0
        for d in deals[:30]:
            savings = d["savings"]
            total_savings += savings
            lines.append(f"• {d['title'][:40]} — {d['momox_price']:.2f}€ (+{savings:.2f}€)")
        if len(deals) > 30:
            lines.append(f"\n... et {len(deals) - 30} autres")
        lines.append(f"\n💰 Total economies: +{total_savings:.2f}€")

        return await self.send_message("\n".join(lines))
