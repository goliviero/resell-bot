"""Telegram notification sender via Bot API (httpx, no wrapper lib)."""

import logging

import httpx

from resell_bot.core.models import Alert

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"

MESSAGE_TEMPLATE = """📚 BONNE AFFAIRE détectée !

{title}
{author_line}ISBN: {isbn}

💰 Achat: {buy_price:.2f}€ sur {buy_platform}
💵 Revente: {sell_price:.2f}€ sur {sell_platform}
📈 Marge estimée: {margin:.2f}€

🔗 {url}

⏰ {timestamp}"""


class Notifier:
    """Sends alerts to Telegram."""

    def __init__(self, bot_token: str, chat_id: str) -> None:
        self.bot_token = bot_token
        self.chat_id = chat_id

    async def send_alert(self, alert: Alert) -> bool:
        """Send a deal alert to Telegram. Returns True on success."""
        author_line = f"Auteur: {alert.listing.author}\n" if alert.listing.author else ""
        text = MESSAGE_TEMPLATE.format(
            title=alert.listing.title,
            author_line=author_line,
            isbn=alert.listing.isbn or "inconnu",
            buy_price=alert.listing.price,
            buy_platform=alert.listing.platform,
            sell_price=alert.buyback_price,
            sell_platform=alert.buyback_platform,
            margin=alert.estimated_margin,
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
                    logger.info("Alert sent: %s", alert.listing.title)
                    return True
                logger.warning("Telegram API error %d: %s", resp.status_code, resp.text)
                return False
        except httpx.HTTPError as e:
            logger.error("Telegram send failed: %s", e)
            return False

    async def send_message(self, text: str) -> bool:
        """Send a raw text message to Telegram."""
        url = TELEGRAM_API.format(token=self.bot_token)
        payload = {"chat_id": self.chat_id, "text": text}
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(url, json=payload, timeout=10)
                return resp.status_code == 200
        except httpx.HTTPError as e:
            logger.error("Telegram send failed: %s", e)
            return False
