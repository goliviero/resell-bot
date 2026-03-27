"""Email notification sender via SMTP (stdlib only)."""

import logging
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from resell_bot.core.models import Alert

logger = logging.getLogger(__name__)

PLATFORM_LABELS = {"momox_shop": "Momox", "recyclivre": "RecycLivre"}


def _build_alert_html(alert: Alert) -> str:
    """Build HTML email body for a single deal alert with clickable links."""
    platform = alert.listing.platform
    platform_label = PLATFORM_LABELS.get(platform, platform)
    condition = alert.listing.condition or "non precise"
    isbn = alert.listing.isbn or ""

    # Image section
    img_html = ""
    if alert.listing.image_url:
        img_html = f'<img src="{alert.listing.image_url}" alt="" style="max-width:120px; border-radius:6px; margin-bottom:10px;">'

    # Author
    author_html = f'<p style="color:#a0a6b8; margin:4px 0;">{alert.listing.author}</p>' if alert.listing.author else ""

    # Platform links
    links = [f'<a href="{alert.listing.url}" style="display:inline-block; padding:10px 24px; background:#22c55e; color:white; text-decoration:none; border-radius:6px; font-weight:bold; margin-right:8px;">Acheter sur {platform_label}</a>']

    if platform != "momox_shop" and isbn:
        links.append(f'<a href="https://www.momox-shop.fr/angebote?searchparam={isbn}" style="display:inline-block; padding:10px 16px; background:#2a2d3a; color:#a0a6b8; text-decoration:none; border-radius:6px; margin-right:8px;">Momox</a>')
    if platform != "recyclivre" and isbn:
        links.append(f'<a href="https://www.recyclivre.com/search?q={isbn}" style="display:inline-block; padding:10px 16px; background:#2a2d3a; color:#a0a6b8; text-decoration:none; border-radius:6px; margin-right:8px;">RecycLivre</a>')

    return f"""
    <div style="font-family:sans-serif; max-width:600px; margin:0 auto; background:#1a1d27; color:#e1e4ed; padding:24px; border-radius:10px;">
        <h2 style="color:#22c55e; margin-top:0;">BONNE AFFAIRE</h2>
        {img_html}
        <h3 style="margin:8px 0 4px;">{alert.listing.title}</h3>
        {author_html}

        <table style="width:100%; margin:16px 0; border-collapse:collapse;">
            <tr style="border-bottom:1px solid #2a2d3a;">
                <td style="color:#888; padding:8px 0;">Prix</td>
                <td style="padding:8px 0; text-align:right;"><strong style="font-size:1.1em;">{alert.listing.price:.2f} EUR</strong></td>
            </tr>
            <tr style="border-bottom:1px solid #2a2d3a;">
                <td style="color:#888; padding:8px 0;">Budget max</td>
                <td style="padding:8px 0; text-align:right;">{alert.max_buy_price:.2f} EUR</td>
            </tr>
            <tr style="border-bottom:1px solid #2a2d3a;">
                <td style="color:#888; padding:8px 0;">Economie</td>
                <td style="padding:8px 0; text-align:right; color:#22c55e; font-weight:bold; font-size:1.1em;">+{alert.savings:.2f} EUR</td>
            </tr>
            <tr style="border-bottom:1px solid #2a2d3a;">
                <td style="color:#888; padding:8px 0;">Plateforme</td>
                <td style="padding:8px 0; text-align:right;">{platform_label}</td>
            </tr>
            <tr style="border-bottom:1px solid #2a2d3a;">
                <td style="color:#888; padding:8px 0;">Etat</td>
                <td style="padding:8px 0; text-align:right;">{condition}</td>
            </tr>
            <tr>
                <td style="color:#888; padding:8px 0;">ISBN</td>
                <td style="padding:8px 0; text-align:right; font-family:monospace;">{isbn}</td>
            </tr>
        </table>

        <div style="margin:20px 0;">
            {''.join(links)}
        </div>

        <p style="color:#555; font-size:11px; margin-top:20px; border-top:1px solid #2a2d3a; padding-top:10px;">
            {alert.listing.found_at.strftime('%Y-%m-%d %H:%M')} — resell-bot
        </p>
    </div>
    """


def _build_digest_html(deals: list[dict]) -> str:
    """Build HTML email body for daily digest."""
    rows = ""
    total_savings = 0.0
    for d in deals:
        savings = d["savings"]
        total_savings += savings
        isbn = d.get("isbn", "")
        platform = d.get("platform", "momox_shop")
        url = d.get("url") or f"https://www.momox-shop.fr/angebote?searchparam={isbn}"
        platform_label = PLATFORM_LABELS.get(platform, platform)
        price = d.get("momox_price", d.get("price", 0))
        rows += f"""
        <tr style="border-bottom:1px solid #2a2d3a;">
            <td style="padding:8px 10px;"><a href="{url}" style="color:#6c63ff; text-decoration:none;">{d['title'][:55]}</a></td>
            <td style="padding:8px 10px; color:#a0a6b8;">{d.get('author') or '—'}</td>
            <td style="padding:8px 10px; font-weight:bold;">{price:.2f} EUR</td>
            <td style="padding:8px 10px;">{d['max_buy_price']:.2f} EUR</td>
            <td style="padding:8px 10px; color:#22c55e; font-weight:bold;">+{savings:.2f} EUR</td>
            <td style="padding:8px 10px;"><a href="{url}" style="display:inline-block; padding:4px 12px; background:#22c55e; color:white; text-decoration:none; border-radius:4px; font-size:12px;">Acheter</a></td>
        </tr>
        """

    return f"""
    <div style="font-family:sans-serif; max-width:800px; margin:0 auto; background:#1a1d27; color:#e1e4ed; padding:24px; border-radius:10px;">
        <h2 style="color:#6c63ff; margin-top:0;">Recap journalier — {len(deals)} bonnes affaires</h2>
        <p style="color:#888;">Total economies potentielles: <strong style="color:#22c55e;">+{total_savings:.2f} EUR</strong></p>
        <table style="width:100%; border-collapse:collapse; margin-top:15px;">
            <thead>
                <tr style="border-bottom:1px solid #2a2d3a; color:#888; font-size:12px; text-transform:uppercase;">
                    <th style="padding:8px 10px; text-align:left;">Titre</th>
                    <th style="padding:8px 10px; text-align:left;">Auteur</th>
                    <th style="padding:8px 10px; text-align:left;">Prix</th>
                    <th style="padding:8px 10px; text-align:left;">Budget</th>
                    <th style="padding:8px 10px; text-align:left;">Economie</th>
                    <th style="padding:8px 10px; text-align:left;">Lien</th>
                </tr>
            </thead>
            <tbody>
                {rows}
            </tbody>
        </table>
        <p style="color:#555; font-size:11px; margin-top:20px; border-top:1px solid #2a2d3a; padding-top:10px;">
            {datetime.now().strftime('%Y-%m-%d %H:%M')} — resell-bot
        </p>
    </div>
    """


def _send_smtp(
    smtp_host: str, smtp_port: int, smtp_user: str, smtp_password: str,
    to_email: str, subject: str, html: str, use_tls: bool = True,
) -> bool:
    """Send an HTML email via SMTP. Returns True on success."""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = smtp_user
    msg["To"] = to_email
    msg.attach(MIMEText(html, "html"))

    try:
        if use_tls:
            server = smtplib.SMTP(smtp_host, smtp_port, timeout=15)
            server.starttls()
        else:
            server = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=15)
        server.login(smtp_user, smtp_password)
        server.sendmail(smtp_user, to_email, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        logger.error("SMTP send failed to %s: %s", to_email, e)
        return False


def send_test_email(
    smtp_host: str, smtp_port: int, smtp_user: str, smtp_password: str,
    to_email: str, use_tls: bool = True,
) -> bool:
    """Send a simple test email to verify SMTP config. Returns True on success."""
    html = """
    <div style="font-family:sans-serif; max-width:500px; margin:0 auto; background:#1a1d27; color:#e1e4ed; padding:20px; border-radius:8px; text-align:center;">
        <h2 style="color:#22c55e;">resell-bot</h2>
        <p>Les notifications email fonctionnent correctement.</p>
        <p style="color:#888; font-size:12px; margin-top:15px;">Ce message est un test automatique.</p>
    </div>
    """
    ok = _send_smtp(smtp_host, smtp_port, smtp_user, smtp_password, to_email,
                    "Test resell-bot — Email OK!", html, use_tls)
    if ok:
        logger.info("Test email sent to %s", to_email)
    return ok


def send_test_alert_email(
    smtp_host: str, smtp_port: int, smtp_user: str, smtp_password: str,
    to_email: str, alert: Alert, use_tls: bool = True,
) -> bool:
    """Send a realistic test alert email (same format as real alerts)."""
    html = _build_alert_html(alert)
    subject = f"[TEST] Deal: {alert.listing.title[:50]} — {alert.listing.price:.2f} EUR (+{alert.savings:.2f})"
    ok = _send_smtp(smtp_host, smtp_port, smtp_user, smtp_password, to_email,
                    subject, html, use_tls)
    if ok:
        logger.info("Test alert email sent to %s: %s", to_email, alert.listing.title)
    return ok


def send_email_alert(
    smtp_host: str, smtp_port: int, smtp_user: str, smtp_password: str,
    to_email: str, alert: Alert, use_tls: bool = True,
) -> bool:
    """Send a deal alert email. Returns True on success."""
    html = _build_alert_html(alert)
    subject = f"Deal: {alert.listing.title[:50]} — {alert.listing.price:.2f} EUR (+{alert.savings:.2f})"
    ok = _send_smtp(smtp_host, smtp_port, smtp_user, smtp_password, to_email,
                    subject, html, use_tls)
    if ok:
        logger.info("Email alert sent to %s: %s", to_email, alert.listing.title)
    return ok


def send_email_digest(
    smtp_host: str, smtp_port: int, smtp_user: str, smtp_password: str,
    to_email: str, deals: list[dict], use_tls: bool = True,
) -> bool:
    """Send daily digest email. Returns True on success."""
    if not deals:
        return True
    total_savings = sum(d["savings"] for d in deals)
    html = _build_digest_html(deals)
    subject = f"Recap resell-bot: {len(deals)} deals dispo (+{total_savings:.2f} EUR)"
    ok = _send_smtp(smtp_host, smtp_port, smtp_user, smtp_password, to_email,
                    subject, html, use_tls)
    if ok:
        logger.info("Email digest sent to %s: %d deals", to_email, len(deals))
    return ok
