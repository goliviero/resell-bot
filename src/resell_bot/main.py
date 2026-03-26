"""Entry point for Resell Bot."""

import asyncio
import logging
import os
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

from resell_bot.core.database import Database
from resell_bot.core.notifier import Notifier
from resell_bot.scheduler import ScanScheduler

load_dotenv()

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


def main() -> None:
    setup_logging()
    logger = logging.getLogger("resell_bot")

    # Load config
    settings_path = PROJECT_ROOT / "config" / "settings.yaml"
    watchlist_path = PROJECT_ROOT / "config" / "watchlists" / "livres.yaml"

    if not settings_path.exists():
        logger.error("Settings not found: %s", settings_path)
        sys.exit(1)
    if not watchlist_path.exists():
        logger.error("Watchlist not found: %s", watchlist_path)
        sys.exit(1)

    settings = load_yaml(settings_path)
    watchlist = load_yaml(watchlist_path)

    # Database
    db_path = PROJECT_ROOT / settings.get("database", {}).get("path", "data/resell_bot.db")
    db = Database(db_path)

    # Telegram notifier (optional — works without it)
    notifier = None
    tg_cfg = settings.get("notifications", {}).get("telegram", {})
    if tg_cfg.get("enabled"):
        bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        chat_id = os.getenv("TELEGRAM_CHAT_ID")
        if bot_token and chat_id:
            notifier = Notifier(bot_token, chat_id)
            logger.info("Telegram notifications enabled")
        else:
            logger.warning("Telegram enabled but TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set in .env")

    # Scheduler
    scheduler = ScanScheduler(settings, watchlist, db, notifier)

    # Check CLI args
    if "--once" in sys.argv:
        logger.info("Running single scan (--once)")
        asyncio.run(scheduler.run_once())
        scheduler.db.close()
        return

    # Continuous mode
    logger.info("Starting Resell Bot in continuous mode")
    scheduler.start()

    # Run first scan immediately
    loop = asyncio.new_event_loop()
    try:
        loop.create_task(scheduler.run_scan())
        loop.run_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        loop.run_until_complete(scheduler.shutdown())
        loop.close()


if __name__ == "__main__":
    main()
