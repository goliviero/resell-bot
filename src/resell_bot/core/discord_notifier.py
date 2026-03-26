"""Discord notification sender via webhook (no external lib)."""

import logging
from datetime import datetime

import httpx

from resell_bot.core.models import Alert

logger = logging.getLogger(__name__)


async def send_discord_alert(webhook_url: str, alert: Alert) -> bool:
    """Send a deal alert to Discord via webhook. Returns True on success."""
    author_line = f"**Auteur:** {alert.listing.author}\n" if alert.listing.author else ""
    embed = {
        "title": f"BONNE AFFAIRE - {alert.listing.title[:80]}",
        "color": 0x22C55E,  # green
        "fields": [
            {"name": "Prix", "value": f"{alert.listing.price:.2f} EUR", "inline": True},
            {"name": "Budget max", "value": f"{alert.max_buy_price:.2f} EUR", "inline": True},
            {"name": "Economie", "value": f"+{alert.savings:.2f} EUR", "inline": True},
            {"name": "Plateforme", "value": alert.listing.platform, "inline": True},
            {"name": "ISBN", "value": alert.listing.isbn or "?", "inline": True},
        ],
        "url": alert.listing.url,
        "timestamp": alert.listing.found_at.isoformat(),
    }
    if alert.listing.author:
        embed["fields"].insert(0, {"name": "Auteur", "value": alert.listing.author, "inline": False})
    if alert.listing.image_url:
        embed["thumbnail"] = {"url": alert.listing.image_url}

    payload = {"embeds": [embed]}

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(webhook_url, json=payload, timeout=10)
            if resp.status_code in (200, 204):
                logger.info("Discord alert sent: %s", alert.listing.title)
                return True
            logger.warning("Discord webhook error %d: %s", resp.status_code, resp.text)
            return False
    except httpx.HTTPError as e:
        logger.error("Discord send failed: %s", e)
        return False


async def send_discord_digest(webhook_url: str, deals: list[dict]) -> bool:
    """Send daily digest of available deals to Discord. Returns True on success."""
    if not deals:
        return True

    lines = []
    total_savings = 0.0
    for d in deals[:25]:  # Discord embed field limit
        savings = d["savings"]
        total_savings += savings
        lines.append(
            f"**{d['title'][:50]}** — {d['momox_price']:.2f} EUR "
            f"(budget {d['max_buy_price']:.2f} EUR, +{savings:.2f} EUR)"
        )

    description = "\n".join(lines)
    if len(deals) > 25:
        description += f"\n\n... et {len(deals) - 25} autres"

    embed = {
        "title": f"Recap journalier — {len(deals)} bonnes affaires disponibles",
        "description": description,
        "color": 0x6C63FF,  # accent purple
        "footer": {"text": f"Total economies potentielles: +{total_savings:.2f} EUR"},
        "timestamp": datetime.now().isoformat(),
    }

    payload = {"embeds": [embed]}

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(webhook_url, json=payload, timeout=15)
            if resp.status_code in (200, 204):
                logger.info("Discord digest sent: %d deals", len(deals))
                return True
            logger.warning("Discord digest error %d: %s", resp.status_code, resp.text)
            return False
    except httpx.HTTPError as e:
        logger.error("Discord digest send failed: %s", e)
        return False
