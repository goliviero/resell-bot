"""FastAPI dashboard for resell-bot — alert viewer + buy actions."""

from pathlib import Path

from fastapi import FastAPI, Form, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from resell_bot.core.buyer import BuyStep, get_all_jobs, get_job, start_buy
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

    scan_overview = db.get_scan_overview("momox_shop")
    live_status = _scheduler.scan_status if _scheduler else {}

    return templates.TemplateResponse(request, "dashboard.html", {
        "alerts": alerts,
        "new_alerts": new_alerts,
        "stats": stats,
        "current_status": status,
        "page": page,
        "per_page": per_page,
        "scan": scan_overview,
        "live": live_status,
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
    """HTMX: return live scan status panel."""
    db = get_db()
    scan_overview = db.get_scan_overview("momox_shop")
    live_status = _scheduler.scan_status if _scheduler else {}
    return templates.TemplateResponse(request, "partials/scan_status.html", {
        "scan": scan_overview,
        "live": live_status,
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


# ── Settings ──────────────────────────────────────────────

def _settings_ctx(db, message: str = "", error: str = "") -> dict:
    """Build template context for the settings page."""
    return {
        "discord_webhooks": db.get_discord_webhooks(),
        "email_configs": db.get_email_configs(),
        "message": message,
        "error": error,
        "active_tab": "settings",
    }


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request, msg: str | None = None):
    """Notification settings page — list all webhooks + emails."""
    db = get_db()
    return templates.TemplateResponse(request, "settings.html", _settings_ctx(db, message=msg or ""))


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
    # Read current state, flip it
    webhooks = db.get_discord_webhooks()
    for wh in webhooks:
        if wh["id"] == wh_id:
            db.toggle_discord_webhook(wh_id, not wh["enabled"])
            break
    return RedirectResponse("/settings", status_code=303)


@app.post("/settings/discord/{wh_id}/test", response_class=HTMLResponse)
async def test_discord_webhook(wh_id: int):
    """Send a test message to a specific Discord webhook."""
    db = get_db()
    webhooks = db.get_discord_webhooks()
    webhook_url = None
    for wh in webhooks:
        if wh["id"] == wh_id:
            webhook_url = wh["url"]
            break
    if not webhook_url:
        return HTMLResponse('<span style="color: var(--red);">Webhook introuvable</span>')

    import httpx
    payload = {"content": "Test resell-bot — Discord OK!"}
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(webhook_url, json=payload, timeout=10)
            if resp.status_code in (200, 204):
                return HTMLResponse('<span style="color: var(--green);">Envoye!</span>')
            return HTMLResponse(f'<span style="color: var(--red);">Erreur {resp.status_code}</span>')
    except Exception as e:
        return HTMLResponse(f'<span style="color: var(--red);">{e}</span>')


@app.post("/settings/email/add", response_class=HTMLResponse)
async def add_email_config(
    request: Request,
    label: str = Form(...),
    email_to: str = Form(...),
    smtp_host: str = Form(...),
    smtp_port: int = Form(587),
    smtp_user: str = Form(...),
    smtp_password: str = Form(...),
):
    """Add a new email notification config."""
    db = get_db()
    db.add_email_config(
        label=label.strip() or "Email",
        email_to=email_to.strip(),
        smtp_host=smtp_host.strip(),
        smtp_port=smtp_port,
        smtp_user=smtp_user.strip(),
        smtp_password=smtp_password.strip(),
    )
    return RedirectResponse("/settings?msg=Config+email+ajoutee!", status_code=303)


@app.post("/settings/email/{config_id}/delete")
async def delete_email_config(config_id: int):
    """Delete an email config."""
    get_db().delete_email_config(config_id)
    return RedirectResponse("/settings?msg=Config+email+supprimee", status_code=303)


@app.post("/settings/email/{config_id}/toggle")
async def toggle_email_config(config_id: int):
    """Toggle an email config on/off."""
    db = get_db()
    configs = db.get_email_configs()
    for ec in configs:
        if ec["id"] == config_id:
            db.toggle_email_config(config_id, not ec["enabled"])
            break
    return RedirectResponse("/settings", status_code=303)


# ── Admin ─────────────────────────────────────────────────────

@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request, msg: str | None = None):
    """Admin control panel."""
    db = get_db()
    from resell_bot.core.notifier import Notifier
    notifier = Notifier(db)
    notifier.reload_channels()
    scan_overview = db.get_scan_overview("momox_shop")
    stats = db.get_alert_stats()
    live_status = _scheduler.scan_status if _scheduler else {}
    return templates.TemplateResponse(request, "admin.html", {
        "scan": scan_overview,
        "live": live_status,
        "alerts_total": stats.get("total", 0),
        "notif_channels": notifier.get_status_summary(),
        "message": msg or "",
        "active_tab": "admin",
    })


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
    """Stop the continuous scanner."""
    if _scheduler:
        _scheduler._running = False
    return RedirectResponse("/admin?msg=Scanner+arrete", status_code=303)


@app.post("/admin/scan/start")
async def admin_scan_start():
    """Restart the continuous scanner in background."""
    if _scheduler and not _scheduler._running:
        import asyncio
        _scheduler._running = True
        asyncio.get_event_loop().create_task(_scheduler.run_continuous())
    return RedirectResponse("/admin?msg=Scanner+demarre", status_code=303)


@app.post("/admin/scan/once")
async def admin_scan_once():
    """Trigger a single manual scan."""
    if _scheduler:
        import asyncio
        _scheduler._running = True
        asyncio.get_event_loop().create_task(_scheduler.run_once())
    return RedirectResponse("/admin?msg=Scan+manuel+lance", status_code=303)


@app.post("/admin/clear-alerts")
async def admin_clear_alerts():
    """Delete all alerts."""
    db = get_db()
    db.conn.execute("DELETE FROM alerts")
    db.conn.commit()
    return RedirectResponse("/admin?msg=Alertes+supprimees", status_code=303)


# ── Buy Flow ─────────────────────────────────────────────────

@app.post("/buy/{alert_id}", response_class=HTMLResponse)
async def trigger_buy(request: Request, alert_id: int):
    """Start the automated purchase flow for an alert."""
    db = get_db()
    alert = db.get_alert_by_id(alert_id)
    if not alert:
        return HTMLResponse("Alerte introuvable", status_code=404)

    existing = get_job(alert_id)
    if existing and existing.step not in (BuyStep.COMPLETED, BuyStep.FAILED):
        # Already running — redirect to status page
        return templates.TemplateResponse(request, "buy_status.html", {
            "job": existing.to_dict(),
            "alert": alert,
            "active_tab": "dashboard",
        })

    job = await start_buy(
        alert_id=alert_id,
        product_url=alert["url"],
        title=alert["title"],
        price=alert["buy_price"],
    )
    return templates.TemplateResponse(request, "buy_status.html", {
        "job": job.to_dict(),
        "alert": alert,
        "active_tab": "dashboard",
    })


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
