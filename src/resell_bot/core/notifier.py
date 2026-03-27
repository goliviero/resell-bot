"""Multi-channel notification hub — Discord webhooks + Email SMTP.

Routing:
- Instant alerts → Discord + Email (1 email per alert)
- Daily digest  → Discord only (recap of active deals at 08:00)

Each channel is stored in its own DB table and can be toggled independently.
"""

import logging

from resell_bot.core.discord_notifier import send_discord_alert, send_discord_digest
from resell_bot.core.email_notifier import send_email_alert
from resell_bot.core.models import Alert

logger = logging.getLogger(__name__)


class Notifier:
    """Sends alerts to all enabled Discord webhooks + Email configs."""

    def __init__(self, db=None) -> None:
        self.db = db
        # Cached channels — refreshed before each send
        self._discord_webhooks: list[dict] = []
        self._smtp_config: dict | None = None
        self._email_subscribers: list[dict] = []
        self._email_configs: list[dict] = []  # legacy

    def reload_channels(self) -> None:
        """Reload enabled channels from DB."""
        if not self.db:
            return
        self._discord_webhooks = self.db.get_discord_webhooks(enabled_only=True)
        # New model: single SMTP config + multiple subscribers
        self._smtp_config = self.db.get_smtp_config()
        self._email_subscribers = self.db.get_email_subscribers(enabled_only=True)
        # Legacy support: also load old email_configs
        self._email_configs = self.db.get_email_configs(enabled_only=True)

    @property
    def discord_enabled(self) -> bool:
        return len(self._discord_webhooks) > 0

    @property
    def email_enabled(self) -> bool:
        return (self._smtp_config is not None and len(self._email_subscribers) > 0) or len(self._email_configs) > 0

    @property
    def any_enabled(self) -> bool:
        return self.discord_enabled or self.email_enabled

    def get_status_summary(self) -> list[str]:
        """Return list of active channel descriptions for logging."""
        channels = []
        for wh in self._discord_webhooks:
            channels.append(f"Discord ({wh['name']})")
        if self._smtp_config and self._email_subscribers:
            emails = ", ".join(s["label"] for s in self._email_subscribers)
            channels.append(f"Email ({emails})")
        for ec in self._email_configs:
            channels.append(f"Email legacy ({ec['label']})")
        return channels

    async def send_alert(self, alert: Alert) -> bool:
        """Send a deal alert to Discord + Email. Logs each attempt."""
        self.reload_channels()
        results = []

        for wh in self._discord_webhooks:
            ok = await send_discord_alert(wh["url"], alert)
            results.append(ok)
            if self.db:
                self.db.log_notification(
                    alert_id=None, channel="discord", channel_name=wh["name"],
                    title=alert.listing.title, isbn=alert.listing.isbn,
                    price=alert.listing.price, savings=alert.savings,
                    success=ok, error=None if ok else "webhook error",
                )

        # New model: single SMTP config → all subscribers
        smtp = self._smtp_config
        if smtp:
            for sub in self._email_subscribers:
                ok = send_email_alert(
                    smtp["smtp_host"], smtp["smtp_port"], smtp["smtp_user"], smtp["smtp_password"],
                    sub["email"], alert, bool(smtp["smtp_use_tls"]),
                )
                results.append(ok)
                if self.db:
                    self.db.log_notification(
                        alert_id=None, channel="email", channel_name=sub["label"],
                        title=alert.listing.title, isbn=alert.listing.isbn,
                        price=alert.listing.price, savings=alert.savings,
                        success=ok, error=None if ok else "smtp error",
                    )

        # Legacy email configs (backwards compat)
        for ec in self._email_configs:
            ok = send_email_alert(
                ec["smtp_host"], ec["smtp_port"], ec["smtp_user"], ec["smtp_password"],
                ec["email_to"], alert, bool(ec["smtp_use_tls"]),
            )
            results.append(ok)
            if self.db:
                self.db.log_notification(
                    alert_id=None, channel="email", channel_name=ec["label"],
                    title=alert.listing.title, isbn=alert.listing.isbn,
                    price=alert.listing.price, savings=alert.savings,
                    success=ok, error=None if ok else "smtp error",
                )

        if not results:
            logger.debug("No notification channels configured — alert not sent")
            return False

        return any(results)

    async def send_daily_digest(self, deals: list[dict]) -> bool:
        """Send daily digest to Discord ONLY (no email recap). Returns True if succeeded."""
        if not deals:
            logger.info("No deals for daily digest — skipping")
            return True

        self.reload_channels()
        results = []

        for wh in self._discord_webhooks:
            results.append(await send_discord_digest(wh["url"], deals))

        return any(results) if results else False
