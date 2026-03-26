"""FastAPI dashboard for resell-bot — alert viewer + buy actions."""

from pathlib import Path

from fastapi import FastAPI, Form, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from resell_bot.core.buyer import BuyStep, get_all_jobs, get_job, start_buy
from resell_bot.core.database import Database
from resell_bot.core.models import AlertStatus

TEMPLATES_DIR = Path(__file__).parent / "templates"

app = FastAPI(title="resell-bot dashboard")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

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

    scan_overview = db.get_scan_overview("momox_shop")
    live_status = _scheduler.scan_status if _scheduler else {}

    return templates.TemplateResponse(request, "dashboard.html", {
        "alerts": alerts,
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


# ── Settings ──────────────────────────────────────────────

@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request, saved: str | None = None):
    """Notification settings page."""
    db = get_db()
    settings = db.get_all_notification_settings()
    return templates.TemplateResponse(request, "settings.html", {
        "settings": settings,
        "saved": saved == "1",
        "active_tab": "settings",
    })


@app.post("/settings", response_class=HTMLResponse)
async def save_settings(
    request: Request,
    discord_webhook_url: str = Form(""),
    email_to: str = Form(""),
    smtp_host: str = Form(""),
    smtp_port: str = Form("587"),
    smtp_user: str = Form(""),
    smtp_password: str = Form(""),
):
    """Save notification settings."""
    db = get_db()

    fields = {
        "discord_webhook_url": discord_webhook_url.strip(),
        "email_to": email_to.strip(),
        "smtp_host": smtp_host.strip(),
        "smtp_port": smtp_port.strip(),
        "smtp_user": smtp_user.strip(),
        "smtp_password": smtp_password.strip(),
    }

    for key, value in fields.items():
        if value:
            db.set_notification_setting(key, value)
        else:
            db.delete_notification_setting(key)

    return RedirectResponse("/settings?saved=1", status_code=303)


@app.post("/settings/test-discord", response_class=HTMLResponse)
async def test_discord(request: Request):
    """Send a test message to Discord webhook."""
    db = get_db()
    webhook_url = db.get_notification_setting("discord_webhook_url")
    if not webhook_url:
        return HTMLResponse('<span style="color: var(--red);">Webhook non configure</span>')

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
