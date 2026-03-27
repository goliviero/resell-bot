"""Discord notification sender via webhook (no external lib)."""

import logging
from datetime import datetime

import httpx

from resell_bot.core.models import Alert

logger = logging.getLogger(__name__)

PLATFORM_LABELS = {"momox_shop": "Momox", "recyclivre": "RecycLivre"}


async def send_discord_alert(webhook_url: str, alert: Alert, is_test: bool = False) -> bool:
    """Send a deal alert to Discord via webhook. Returns True on success."""
    platform = alert.listing.platform
    platform_label = PLATFORM_LABELS.get(platform, platform)
    condition = alert.listing.condition or "non precise"

    if is_test:
        title_prefix = "TEST — "
        color = 0xF59E0B  # orange for test
    else:
        title_prefix = "DEAL — "
        color = 0x22C55E  # green

    embed = {
        "title": f"{title_prefix}{alert.listing.title[:80]}",
        "url": alert.listing.url,
        "color": color,
        "fields": [
            {"name": "Prix", "value": f"**{alert.listing.price:.2f} EUR**", "inline": True},
            {"name": "Budget max", "value": f"{alert.max_buy_price:.2f} EUR", "inline": True},
            {"name": "Economie", "value": f"**+{alert.savings:.2f} EUR**", "inline": True},
            {"name": "Plateforme", "value": platform_label, "inline": True},
            {"name": "Etat", "value": condition, "inline": True},
            {"name": "ISBN", "value": alert.listing.isbn or "?", "inline": True},
        ],
        "timestamp": alert.listing.found_at.isoformat(),
    }
    if alert.listing.author:
        embed["description"] = f"*{alert.listing.author}*"
    if alert.listing.image_url:
        embed["thumbnail"] = {"url": alert.listing.image_url}

    # Action buttons as description links
    buy_link = f"[Acheter sur {platform_label}]({alert.listing.url})"
    dashboard_link = "[Dashboard](http://127.0.0.1:8000/)"

    # Build search links for other platforms
    isbn = alert.listing.isbn or ""
    links = [buy_link]
    if platform != "momox_shop" and isbn:
        links.append(f"[Momox](https://www.momox-shop.fr/angebote?searchparam={isbn})")
    if platform != "recyclivre" and isbn:
        links.append(f"[RecycLivre](https://www.recyclivre.com/search?q={isbn})")
    links.append(dashboard_link)

    # Add links below author if present, otherwise as description
    link_line = " | ".join(links)
    if embed.get("description"):
        embed["description"] += f"\n\n{link_line}"
    else:
        embed["description"] = link_line

    if is_test:
        embed["footer"] = {"text": "⚠ ALERTE TEST — ne pas prendre en compte"}
    payload = {"content": "@everyone", "embeds": [embed]}

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
        isbn = d.get("isbn", "")
        platform = d.get("platform", "momox_shop")
        platform_label = PLATFORM_LABELS.get(platform, platform)
        url = d.get("url") or f"https://www.momox-shop.fr/angebote?searchparam={isbn}"
        lines.append(
            f"**[{d['title'][:50]}]({url})** — {d.get('momox_price', d.get('price', 0)):.2f} EUR "
            f"sur {platform_label} (budget {d['max_buy_price']:.2f} EUR, **+{savings:.2f} EUR**)"
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
