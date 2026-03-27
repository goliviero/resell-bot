"""FastAPI dashboard for resell-bot — alert viewer + buy actions."""

from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Form, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from resell_bot.core.buyer import BuyStep, get_all_jobs, get_job, set_scheduler as set_buyer_scheduler, start_buy
from resell_bot.core.database import Database
from resell_bot.core.models import AlertStatus
from resell_bot.web.auth import setup_auth

TEMPLATES_DIR = Path(__file__).parent / "templates"

app = FastAPI(title="resell-bot dashboard")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
setup_auth(app)

# Database + scheduler instances — set at startup via configure()
_db: Database | None = None
_scheduler = None


def configure(db: Database, scheduler=None) -> None:
    """Inject the database and optional scheduler into the web app."""
    global _db, _scheduler
    _db = db
    _scheduler = scheduler
    # Let the buyer pause/resume the scanner during purchases
    if scheduler is not None:
        set_buyer_scheduler(scheduler)


def get_db() -> Database:
    if _db is None:
        raise RuntimeError("Database not configured — call web.configure(db) first")
    return _db


# ── Pages ─────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    status: str | None = None,
    page: int = Query(1, ge=1),
):
    """Main dashboard — list of alerts."""
    db = get_db()
    per_page = 20
    offset = (page - 1) * per_page

    filter_status = AlertStatus(status) if status and status in AlertStatus.__members__.values() else None
    alerts = db.get_alerts(status=filter_status, limit=per_page, offset=offset)
    stats = db.get_alert_stats()

    # Get new (unseen) alerts for the banner — only on main view (no filter)
    new_alerts = []
    if not filter_status and page == 1:
        new_alerts = db.get_alerts(status=AlertStatus.NEW, limit=10)

    scan_momox = db.get_scan_overview("momox_shop")
    scan_recyclivre = db.get_scan_overview("recyclivre")
    live = _scheduler.scan_status if _scheduler else {}

    return templates.TemplateResponse(request, "dashboard.html", {
        "alerts": alerts,
        "new_alerts": new_alerts,
        "stats": stats,
        "current_status": status,
        "page": page,
        "per_page": per_page,
        "platforms": [
            {"name": "Momox", "scan": scan_momox, "live": live.get("momox_shop", {})},
            {"name": "RecycLivre", "scan": scan_recyclivre, "live": live.get("recyclivre", {})},
        ],
        "active_tab": "dashboard",
    })


@app.get("/books", response_class=HTMLResponse)
async def books_list(
    request: Request,
    q: str | None = None,
    sort: str = "deals",
    page: int = Query(1, ge=1),
    dispo: str | None = None,
):
    """All watchlist books with their current Momox availability and price."""
    db = get_db()
    per_page = 50
    offset = (page - 1) * per_page

    books = db.get_books_with_prices(
        search=q, sort=sort, limit=per_page, offset=offset,
        availability_filter=dispo,
    )
    total = db.count_books(search=q, availability_filter=dispo)

    # Availability summary
    scan_overview = db.get_scan_overview("momox_shop")

    return templates.TemplateResponse(request, "books.html", {
        "books": books,
        "total": total,
        "search": q or "",
        "sort": sort,
        "dispo": dispo or "",
        "page": page,
        "per_page": per_page,
        "scan": scan_overview,
        "active_tab": "books",
    })


@app.get("/alert/{alert_id}", response_class=HTMLResponse)
async def alert_detail(request: Request, alert_id: int):
    """Single alert detail view."""
    db = get_db()
    alert = db.get_alert_by_id(alert_id)
    if not alert:
        return HTMLResponse("<p>Alerte introuvable</p>", status_code=404)

    # Mark as seen if it was new
    if alert["status"] == AlertStatus.NEW.value:
        db.update_alert_status(alert_id, AlertStatus.SEEN)
        alert["status"] = AlertStatus.SEEN.value

    return templates.TemplateResponse(request, "alert_detail.html", {
        "alert": alert,
    })


# ── HTMX Actions ─────────────────────────────────────────────

@app.post("/alert/{alert_id}/status/{new_status}", response_class=HTMLResponse)
async def update_status(request: Request, alert_id: int, new_status: str):
    """HTMX: update alert status and return refreshed row."""
    db = get_db()
    try:
        target_status = AlertStatus(new_status)
    except ValueError:
        return HTMLResponse("Status invalide", status_code=400)

    db.update_alert_status(alert_id, target_status)
    alert = db.get_alert_by_id(alert_id)
    if not alert:
        return HTMLResponse("", status_code=404)

    return templates.TemplateResponse(request, "partials/alert_row.html", {
        "alert": alert,
    })


@app.get("/stats", response_class=HTMLResponse)
async def stats_fragment(request: Request):
    """HTMX: return updated stats counters."""
    db = get_db()
    stats = db.get_alert_stats()
    return templates.TemplateResponse(request, "partials/stats.html", {
        "stats": stats,
    })


@app.get("/scan-status", response_class=HTMLResponse)
async def scan_status_fragment(request: Request):
    """HTMX: return live scan status panels for all platforms."""
    db = get_db()
    live = _scheduler.scan_status if _scheduler else {}
    platforms = [
        {"name": "Momox", "scan": db.get_scan_overview("momox_shop"), "live": live.get("momox_shop", {})},
        {"name": "RecycLivre", "scan": db.get_scan_overview("recyclivre"), "live": live.get("recyclivre", {})},
    ]
    return templates.TemplateResponse(request, "partials/scan_status.html", {
        "platforms": platforms,
    })


@app.get("/bell", response_class=HTMLResponse)
async def bell_fragment():
    """HTMX: return bell icon content with new alert count.

    When new alerts exist, fires a 'refreshDashboard' event so the
    banner and stats sections auto-update without a full page reload.
    """
    db = get_db()
    stats = db.get_alert_stats()
    new_count = stats.get("new", 0)
    svg = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align: middle;"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg>'
    if new_count > 0:
        return HTMLResponse(
            f'{svg}<span class="bell-count">{new_count}</span>',
            headers={"HX-Trigger": "refreshDashboard"},
        )
    return HTMLResponse(svg)


@app.get("/dashboard/new-alerts", response_class=HTMLResponse)
async def new_alerts_fragment(request: Request):
    """HTMX: return the new alerts banner partial."""
    db = get_db()
    new_alerts = db.get_alerts(status=AlertStatus.NEW, limit=10)
    return templates.TemplateResponse(request, "partials/new_alerts_banner.html", {
        "new_alerts": new_alerts,
    })


@app.post("/alerts/mark-all-seen", response_class=HTMLResponse)
async def mark_all_seen():
    """Mark all NEW alerts as SEEN. Called when user clicks bell or after banner timeout."""
    db = get_db()
    count = db.mark_all_new_as_seen()
    return HTMLResponse(f"{count}", status_code=200)


# ── Settings ──────────────────────────────────────────────

def _settings_ctx(db, message: str = "", error: str = "", log_page: int = 1) -> dict:
    """Build template context for the settings page."""
    log_per_page = 25
    notif_log = db.get_notification_log(limit=log_per_page, offset=(log_page - 1) * log_per_page)
    notif_log_total = db.count_notification_log()
    return {
        "discord_webhooks": db.get_discord_webhooks(),
        "email_subscribers": db.get_email_subscribers(),
        "smtp_configured": db.get_smtp_config() is not None,
        "message": message,
        "error": error,
        "active_tab": "settings",
        "notif_log": notif_log,
        "notif_log_total": notif_log_total,
        "log_page": log_page,
        "log_per_page": log_per_page,
    }


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(
    request: Request,
    msg: str | None = None,
    log_page: int = Query(1, ge=1),
):
    """Notification settings page — list all webhooks + emails."""
    db = get_db()
    return templates.TemplateResponse(request, "settings.html", _settings_ctx(db, message=msg or "", log_page=log_page))


@app.post("/settings/discord/add", response_class=HTMLResponse)
async def add_discord_webhook(
    request: Request,
    name: str = Form(...),
    url: str = Form(...),
):
    """Add a new Discord webhook."""
    db = get_db()
    name, url = name.strip(), url.strip()
    if not url.startswith("https://discord.com/api/webhooks/"):
        return templates.TemplateResponse(request, "settings.html",
            _settings_ctx(db, error="URL invalide — doit commencer par https://discord.com/api/webhooks/"))
    try:
        db.add_discord_webhook(name or "Discord", url)
    except Exception:
        return templates.TemplateResponse(request, "settings.html",
            _settings_ctx(db, error="Ce webhook existe deja."))
    return RedirectResponse("/settings?msg=Webhook+Discord+ajoute!", status_code=303)


@app.post("/settings/discord/{wh_id}/delete")
async def delete_discord_webhook(wh_id: int):
    """Delete a Discord webhook."""
    get_db().delete_discord_webhook(wh_id)
    return RedirectResponse("/settings?msg=Webhook+supprime", status_code=303)


@app.post("/settings/discord/{wh_id}/toggle")
async def toggle_discord_webhook(wh_id: int):
    """Toggle a Discord webhook on/off."""
    db = get_db()
    webhooks = db.get_discord_webhooks()
    for wh in webhooks:
        if wh["id"] == wh_id:
            db.toggle_discord_webhook(wh_id, not wh["enabled"])
            break
    return RedirectResponse("/settings", status_code=303)


@app.post("/settings/discord/{wh_id}/rename", response_class=HTMLResponse)
async def rename_discord_webhook(wh_id: int, name: str = Form(...)):
    """Rename a Discord webhook."""
    get_db().rename_discord_webhook(wh_id, name.strip())
    return RedirectResponse("/settings?msg=Webhook+renomme", status_code=303)


def _build_test_alert(db) -> "Alert":
    """Build a fake 'Le Petit Prince' test Alert — clearly marked as TEST."""
    from resell_bot.core.models import Alert, Listing

    listing = Listing(
        title="[TEST] Le Petit Prince",
        price=3.49,
        url="https://www.momox-shop.fr/angebote?searchparam=9782070612758",
        platform="momox_shop",
        isbn="9782070612758",
        condition="très bon",
        seller="Momox",
        author="Antoine de Saint-Exupery",
        found_at=datetime.now(),
        image_url="https://images-eu.ssl-images-amazon.com/images/I/51H0JEQDFEL._SY291_BO1,204,203,200_QL40_FMwebp_.jpg",
    )
    return Alert(listing=listing, max_buy_price=12.0, savings=8.51)


@app.post("/settings/discord/{wh_id}/test", response_class=HTMLResponse)
async def test_discord_webhook(wh_id: int):
    """Send a realistic test alert to a specific Discord webhook."""
    db = get_db()
    webhooks = db.get_discord_webhooks()
    webhook_url = None
    for wh in webhooks:
        if wh["id"] == wh_id:
            webhook_url = wh["url"]
            break
    if not webhook_url:
        return HTMLResponse('<span style="color: var(--red);">Webhook introuvable</span>')

    from resell_bot.core.discord_notifier import send_discord_alert
    alert = _build_test_alert(db)
    ok = await send_discord_alert(webhook_url, alert, is_test=True)
    if ok:
        return HTMLResponse(f'<span style="color: var(--green);">Alerte test envoyee!</span>')
    return HTMLResponse('<span style="color: var(--red);">Echec webhook</span>')


@app.post("/settings/email/subscribe", response_class=HTMLResponse)
async def add_email_subscriber(
    request: Request,
    label: str = Form(...),
    email: str = Form(...),
):
    """Subscribe an email address to receive alerts."""
    db = get_db()
    label, email = label.strip(), email.strip()
    if not email or "@" not in email:
        return templates.TemplateResponse(request, "settings.html",
            _settings_ctx(db, error="Adresse email invalide."))
    try:
        db.add_email_subscriber(label or "Email", email)
    except Exception:
        return templates.TemplateResponse(request, "settings.html",
            _settings_ctx(db, error="Cet email est deja abonne."))
    return RedirectResponse("/settings?msg=Abonnement+email+ajoute!", status_code=303)


@app.post("/settings/email/{sub_id}/delete")
async def delete_email_subscriber(sub_id: int):
    """Remove an email subscriber."""
    get_db().delete_email_subscriber(sub_id)
    return RedirectResponse("/settings?msg=Abonne+supprime", status_code=303)


@app.post("/settings/email/{sub_id}/toggle")
async def toggle_email_subscriber(sub_id: int):
    """Toggle an email subscriber on/off."""
    db = get_db()
    subs = db.get_email_subscribers()
    for s in subs:
        if s["id"] == sub_id:
            db.toggle_email_subscriber(sub_id, not s["enabled"])
            break
    return RedirectResponse("/settings", status_code=303)


@app.post("/settings/email/{sub_id}/rename", response_class=HTMLResponse)
async def rename_email_subscriber(sub_id: int, label: str = Form(...)):
    """Rename an email subscriber."""
    get_db().rename_email_subscriber(sub_id, label.strip())
    return RedirectResponse("/settings?msg=Abonne+renomme", status_code=303)


@app.post("/settings/email/{sub_id}/test", response_class=HTMLResponse)
async def test_email_subscriber(sub_id: int):
    """Send a realistic test alert email to a specific subscriber."""
    db = get_db()
    smtp = db.get_smtp_config()
    if not smtp:
        return HTMLResponse('<span style="color: var(--red);">SMTP non configure — voir Admin</span>')

    subs = db.get_email_subscribers()
    sub = next((s for s in subs if s["id"] == sub_id), None)
    if not sub:
        return HTMLResponse('<span style="color: var(--red);">Abonne introuvable</span>')

    from resell_bot.core.email_notifier import send_test_alert_email
    alert = _build_test_alert(db)
    ok = send_test_alert_email(
        smtp["smtp_host"], smtp["smtp_port"],
        smtp["smtp_user"], smtp["smtp_password"],
        sub["email"], alert, bool(smtp["smtp_use_tls"]),
    )
    if ok:
        return HTMLResponse(f'<span style="color: var(--green);">Alerte test envoyee ({alert.listing.title[:30]})</span>')
    return HTMLResponse('<span style="color: var(--red);">Echec — verifiez la config SMTP dans Admin</span>')


# ── Admin ─────────────────────────────────────────────────────

@app.get("/admin", response_class=HTMLResponse)
async def admin_page(
    request: Request,
    msg: str | None = None,
):
    """Admin control panel."""
    db = get_db()
    from resell_bot.core.notifier import Notifier
    notifier = Notifier(db)
    notifier.reload_channels()
    scan_momox = db.get_scan_overview("momox_shop")
    stats = db.get_alert_stats()
    live = _scheduler.scan_status if _scheduler else {}
    # Admin needs overall running flag (any platform scanning)
    any_running = any(ps.get("running") for ps in live.values()) if live else False

    return templates.TemplateResponse(request, "admin.html", {
        "scan": scan_momox,
        "live": {"running": any_running},
        "platforms": [
            {"name": "Momox", "scan": scan_momox, "live": live.get("momox_shop", {})},
            {"name": "RecycLivre", "scan": db.get_scan_overview("recyclivre"), "live": live.get("recyclivre", {})},
        ],
        "alerts_total": stats.get("total", 0),
        "notif_channels": notifier.get_status_summary(),
        "smtp_config": db.get_smtp_config(),
        "message": msg or "",
        "active_tab": "admin",
    })


@app.post("/admin/smtp/save")
async def admin_smtp_save(
    smtp_host: str = Form(...),
    smtp_port: int = Form(587),
    smtp_user: str = Form(...),
    smtp_password: str = Form(...),
    smtp_use_tls: int = Form(1),
):
    """Save the single SMTP sender config (admin only)."""
    db = get_db()
    db.set_smtp_config(
        smtp_host=smtp_host.strip(),
        smtp_port=smtp_port,
        smtp_user=smtp_user.strip(),
        smtp_password=smtp_password.strip(),
        smtp_use_tls=bool(smtp_use_tls),
    )
    return RedirectResponse("/admin?msg=Config+SMTP+enregistree!", status_code=303)


@app.post("/admin/smtp/test", response_class=HTMLResponse)
async def admin_smtp_test():
    """Send a realistic test alert email to self (SMTP self-test)."""
    db = get_db()
    smtp = db.get_smtp_config()
    if not smtp:
        return HTMLResponse('<span style="color: var(--red);">SMTP non configure</span>')

    from resell_bot.core.email_notifier import send_test_alert_email
    alert = _build_test_alert(db)
    ok = send_test_alert_email(
        smtp["smtp_host"], smtp["smtp_port"],
        smtp["smtp_user"], smtp["smtp_password"],
        smtp["smtp_user"],  # send to self
        alert, bool(smtp["smtp_use_tls"]),
    )
    if ok:
        return HTMLResponse(f'<span style="color: var(--green);">Alerte test envoyee a {smtp["smtp_user"]}!</span>')
    return HTMLResponse('<span style="color: var(--red);">Echec — verifiez host/port/identifiants</span>')


@app.get("/admin/scan-info", response_class=HTMLResponse)
async def admin_scan_info(request: Request):
    """HTMX fragment: live scan stats for admin page."""
    live = _scheduler.scan_status if _scheduler else {}
    return HTMLResponse(f"""
    <div class="scan-stat">
        <div style="font-size: 1.4rem; font-weight: 700; color: var(--accent);">{live.get('cycle_count', 0)}</div>
        <div style="font-size: 0.7rem; color: var(--muted);">CYCLES</div>
    </div>
    <div class="scan-stat">
        <div style="font-size: 1.4rem; font-weight: 700;">{live.get('scanned_count', 0)} / {live.get('total_count', 0)}</div>
        <div style="font-size: 0.7rem; color: var(--muted);">ISBNs SCANNES</div>
    </div>
    <div class="scan-stat">
        <div style="font-size: 1.4rem; font-weight: 700; color: var(--green);">{live.get('deals_found', 0)}</div>
        <div style="font-size: 0.7rem; color: var(--muted);">DEALS CE CYCLE</div>
    </div>
    <div class="scan-stat">
        <div style="font-size: 1.4rem; font-weight: 700;">
            {'%.0fs' % live['last_cycle_duration'] if live.get('last_cycle_duration') else '—'}
        </div>
        <div style="font-size: 0.7rem; color: var(--muted);">DERNIER CYCLE</div>
    </div>
    """)


@app.post("/admin/scan/stop")
async def admin_scan_stop():
    """Stop the continuous scanner. Auto-restarts after 1h."""
    if _scheduler:
        _scheduler.stop_scan(auto_restart_hours=1.0)
    return RedirectResponse("/admin?msg=Scanner+arrete+(redemarrage+auto+dans+1h)", status_code=303)


@app.post("/admin/scan/start")
async def admin_scan_start():
    """Restart the continuous scanner in background."""
    if _scheduler:
        _scheduler.start_scan()
    return RedirectResponse("/admin?msg=Scanner+demarre", status_code=303)


@app.post("/admin/scan/once")
async def admin_scan_once():
    """Trigger a single manual scan."""
    if _scheduler:
        loop = _scheduler._get_loop()
        _scheduler._running = True
        loop.call_soon_threadsafe(loop.create_task, _scheduler.run_once())
    return RedirectResponse("/admin?msg=Scan+manuel+lance", status_code=303)


@app.post("/admin/clear-alerts")
async def admin_clear_alerts():
    """Delete all alerts."""
    db = get_db()
    db.conn.execute("DELETE FROM alerts")
    db.conn.commit()
    return RedirectResponse("/admin?msg=Alertes+supprimees", status_code=303)


# ── Buy Flow ─────────────────────────────────────────────────

@app.post("/buy/{alert_id}")
async def trigger_buy(alert_id: int):
    """Open product URL in user's browser and redirect back to dashboard."""
    db = get_db()
    alert = db.get_alert_by_id(alert_id)
    if not alert:
        return HTMLResponse("Alerte introuvable", status_code=404)

    await start_buy(
        alert_id=alert_id,
        product_url=alert["url"],
        title=alert["title"],
        price=alert["buy_price"],
        platform=alert.get("platform", "momox_shop"),
    )
    return RedirectResponse("/", status_code=303)


@app.get("/buy/{alert_id}/status", response_class=HTMLResponse)
async def buy_status_page(request: Request, alert_id: int):
    """Buy flow status page."""
    db = get_db()
    alert = db.get_alert_by_id(alert_id)
    job = get_job(alert_id)
    if not job or not alert:
        return HTMLResponse("Aucun achat en cours pour cette alerte", status_code=404)

    return templates.TemplateResponse(request, "buy_status.html", {
        "job": job.to_dict(),
        "alert": alert,
        "active_tab": "dashboard",
    })


@app.get("/buy/{alert_id}/poll")
async def buy_poll(alert_id: int):
    """HTMX polling: return current buy job state as JSON."""
    job = get_job(alert_id)
    if not job:
        return JSONResponse({"step": "not_found"}, status_code=404)
    return JSONResponse(job.to_dict())
