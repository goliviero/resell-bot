"""Entry point for Resell Bot."""

import asyncio
import logging
import sys
import threading
from pathlib import Path

import uvicorn
import yaml

from resell_bot.core.database import Database
from resell_bot.core.notifier import Notifier
from resell_bot.scheduler import ScanScheduler

# Project root: two levels up from src/resell_bot/main.py
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def load_yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def start_dashboard(db: Database, scheduler=None, host: str = "127.0.0.1", port: int = 8000) -> None:
    """Start the web dashboard in a background thread."""
    from resell_bot.web.app import app, configure

    configure(db, scheduler)

    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level="warning",
    )
    server = uvicorn.Server(config)

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    logging.getLogger("resell_bot").info("Dashboard running at http://%s:%d", host, port)


def main() -> None:
    setup_logging()
    logger = logging.getLogger("resell_bot")

    # Load config
    settings_path = PROJECT_ROOT / "config" / "settings.yaml"
    if not settings_path.exists():
        logger.error("Settings not found: %s", settings_path)
        sys.exit(1)

    settings = load_yaml(settings_path)

    # Database
    db_path = PROJECT_ROOT / settings.get("database", {}).get("path", "data/resell_bot.db")
    db = Database(db_path)

    # Notifier — loads channels from DB tables
    notifier = Notifier(db)
    notifier.reload_channels()

    channels = notifier.get_status_summary()
    if channels:
        logger.info("Notifications enabled: %s", ", ".join(channels))
    else:
        logger.warning("No notification channels configured — use dashboard /settings to add")

    # Dashboard mode only
    if "--dashboard" in sys.argv:
        idx = sys.argv.index("--dashboard")
        port = int(sys.argv[idx + 1]) if len(sys.argv) > idx + 1 and sys.argv[idx + 1].isdigit() else 8000
        from resell_bot.web.app import app, configure
        configure(db)  # No scheduler in dashboard-only mode
        logger.info("Starting dashboard only on http://127.0.0.1:%d", port)
        uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")
        return

    # Scheduler (reads ISBNs from reference_prices table)
    scheduler = ScanScheduler(settings, db, notifier)

    # Single scan mode
    if "--once" in sys.argv:
        logger.info("Running single Momox scan (--once)")
        asyncio.run(scheduler.run_once())
        db.close()
        return

    # Continuous mode with dashboard
    start_dashboard(db, scheduler)
    logger.info("Starting Resell Bot in continuous mode")

    async def _run_continuous() -> None:
        scheduler.start()
        try:
            await scheduler.run_continuous()
        except asyncio.CancelledError:
            pass
        finally:
            await scheduler.shutdown()

    try:
        asyncio.run(_run_continuous())
    except KeyboardInterrupt:
        logger.info("Shutting down...")


if __name__ == "__main__":
    main()
