"""Email notification sender via SMTP (stdlib only)."""

import logging
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from resell_bot.core.models import Alert

logger = logging.getLogger(__name__)


def _build_alert_html(alert: Alert) -> str:
    """Build HTML email body for a single deal alert."""
    author_html = f"<p style='color:#888;'>Auteur: {alert.listing.author}</p>" if alert.listing.author else ""
    return f"""
    <div style="font-family:sans-serif; max-width:600px; margin:0 auto; background:#1a1d27; color:#e1e4ed; padding:20px; border-radius:8px;">
        <h2 style="color:#22c55e;">BONNE AFFAIRE</h2>
        <h3>{alert.listing.title}</h3>
        {author_html}
        <table style="width:100%; margin:15px 0;">
            <tr><td style="color:#888;">Prix</td><td><strong>{alert.listing.price:.2f} EUR</strong> sur {alert.listing.platform}</td></tr>
            <tr><td style="color:#888;">Budget max</td><td>{alert.max_buy_price:.2f} EUR</td></tr>
            <tr><td style="color:#888;">Economie</td><td style="color:#22c55e; font-weight:bold;">+{alert.savings:.2f} EUR</td></tr>
            <tr><td style="color:#888;">ISBN</td><td>{alert.listing.isbn or '?'}</td></tr>
        </table>
        <a href="{alert.listing.url}" style="display:inline-block; padding:10px 20px; background:#22c55e; color:white; text-decoration:none; border-radius:6px;">Voir sur {alert.listing.platform}</a>
        <p style="color:#888; font-size:12px; margin-top:15px;">{alert.listing.found_at.strftime('%Y-%m-%d %H:%M')}</p>
    </div>
    """


def _build_digest_html(deals: list[dict]) -> str:
    """Build HTML email body for daily digest."""
    rows = ""
    total_savings = 0.0
    for d in deals:
        savings = d["savings"]
        total_savings += savings
        isbn = d["isbn"]
        rows += f"""
        <tr>
            <td style="padding:6px 10px;">{d['title'][:60]}</td>
            <td style="padding:6px 10px;">{d.get('author') or '—'}</td>
            <td style="padding:6px 10px; font-weight:bold;">{d['momox_price']:.2f} EUR</td>
            <td style="padding:6px 10px;">{d['max_buy_price']:.2f} EUR</td>
            <td style="padding:6px 10px; color:#22c55e; font-weight:bold;">+{savings:.2f} EUR</td>
            <td style="padding:6px 10px;"><a href="https://www.momox-shop.fr/angebote?searchparam={isbn}" style="color:#6c63ff;">Acheter</a></td>
        </tr>
        """

    return f"""
    <div style="font-family:sans-serif; max-width:800px; margin:0 auto; background:#1a1d27; color:#e1e4ed; padding:20px; border-radius:8px;">
        <h2 style="color:#6c63ff;">Recap journalier — {len(deals)} bonnes affaires</h2>
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
        <p style="color:#888; font-size:12px; margin-top:15px;">{datetime.now().strftime('%Y-%m-%d %H:%M')} — resell-bot</p>
    </div>
    """


def send_email_alert(
    smtp_host: str,
    smtp_port: int,
    smtp_user: str,
    smtp_password: str,
    to_email: str,
    alert: Alert,
    use_tls: bool = True,
) -> bool:
    """Send a deal alert email. Returns True on success."""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Deal: {alert.listing.title[:50]} — {alert.listing.price:.2f} EUR (+{alert.savings:.2f})"
    msg["From"] = smtp_user
    msg["To"] = to_email

    html = _build_alert_html(alert)
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
        logger.info("Email alert sent to %s: %s", to_email, alert.listing.title)
        return True
    except Exception as e:
        logger.error("Email send failed: %s", e)
        return False


def send_email_digest(
    smtp_host: str,
    smtp_port: int,
    smtp_user: str,
    smtp_password: str,
    to_email: str,
    deals: list[dict],
    use_tls: bool = True,
) -> bool:
    """Send daily digest email. Returns True on success."""
    if not deals:
        return True

    total_savings = sum(d["savings"] for d in deals)
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Recap resell-bot: {len(deals)} deals dispo (+{total_savings:.2f} EUR)"
    msg["From"] = smtp_user
    msg["To"] = to_email

    html = _build_digest_html(deals)
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
        logger.info("Email digest sent to %s: %d deals", to_email, len(deals))
        return True
    except Exception as e:
        logger.error("Email digest send failed: %s", e)
        return False
