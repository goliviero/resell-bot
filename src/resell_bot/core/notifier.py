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
        self._email_configs: list[dict] = []

    def reload_channels(self) -> None:
        """Reload enabled channels from DB."""
        if not self.db:
            return
        self._discord_webhooks = self.db.get_discord_webhooks(enabled_only=True)
        self._email_configs = self.db.get_email_configs(enabled_only=True)

    @property
    def discord_enabled(self) -> bool:
        return len(self._discord_webhooks) > 0

    @property
    def email_enabled(self) -> bool:
        return len(self._email_configs) > 0

    @property
    def any_enabled(self) -> bool:
        return self.discord_enabled or self.email_enabled

    def get_status_summary(self) -> list[str]:
        """Return list of active channel descriptions for logging."""
        channels = []
        for wh in self._discord_webhooks:
            channels.append(f"Discord ({wh['name']})")
        for ec in self._email_configs:
            channels.append(f"Email ({ec['label']})")
        return channels

    async def send_alert(self, alert: Alert) -> bool:
        """Send a deal alert to Discord + Email. Returns True if at least one succeeded."""
        self.reload_channels()
        results = []

        for wh in self._discord_webhooks:
            results.append(await send_discord_alert(wh["url"], alert))

        for ec in self._email_configs:
            results.append(send_email_alert(
                ec["smtp_host"], ec["smtp_port"], ec["smtp_user"], ec["smtp_password"],
                ec["email_to"], alert, bool(ec["smtp_use_tls"]),
            ))

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
