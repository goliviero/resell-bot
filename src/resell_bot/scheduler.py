"""Scan scheduler — orchestrates periodic scraping runs."""

import asyncio
import logging
from pathlib import Path

import yaml
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from resell_bot.core.database import Database
from resell_bot.core.models import Alert
from resell_bot.core.notifier import Notifier
from resell_bot.core.price_engine import PriceEngine, PriceEngineConfig
from resell_bot.scrapers.base import BaseScraper
from resell_bot.scrapers.chasseauxlivres import ChasseAuxLivresScraper
from resell_bot.scrapers.momox import MomoxScraper
from resell_bot.scrapers.recyclivre import RecyclivreScraper
from resell_bot.utils.http_client import HttpClient

logger = logging.getLogger(__name__)


class ScanScheduler:
    """Manages periodic scan jobs across all configured scrapers."""

    def __init__(
        self,
        settings: dict,
        watchlist: dict,
        db: Database,
        notifier: Notifier | None,
    ) -> None:
        self.settings = settings
        self.watchlist = watchlist
        self.db = db
        self.notifier = notifier

        scan_cfg = settings.get("scan", {})
        self.interval = scan_cfg.get("interval_minutes", 5)
        self.delay_min = scan_cfg.get("delay_between_requests", {}).get("min_seconds", 2)
        self.delay_max = scan_cfg.get("delay_between_requests", {}).get("max_seconds", 5)

        http_cfg = settings.get("http", {})
        self.http_client = HttpClient(
            user_agents=http_cfg.get("user_agents"),
            timeout=http_cfg.get("timeout_seconds", 15),
            max_retries=http_cfg.get("max_retries", 3),
            delay_min=self.delay_min,
            delay_max=self.delay_max,
        )

        # Price engine config from watchlist filters
        filters = watchlist.get("filters", {})
        self.engine = PriceEngine(
            PriceEngineConfig(
                min_margin=filters.get("min_margin", 3.0),
                max_buy_price=filters.get("max_buy_price", 15.0),
            )
        )

        self.cooldown_hours = settings.get("dedup", {}).get("cooldown_hours", 24)

        # Discovery scrapers (where to find books to buy)
        self.discovery_scrapers: list[BaseScraper] = [
            ChasseAuxLivresScraper(self.http_client),
        ]

        # Buyback scrapers (where to check resale prices)
        self.buyback_scrapers: list[BaseScraper] = [
            MomoxScraper(),
            RecyclivreScraper(),
        ]

        self.scheduler = AsyncIOScheduler()

    async def run_scan(self) -> None:
        """Execute one full scan cycle."""
        keywords = self.watchlist.get("keywords", [])
        isbns = self.watchlist.get("isbns", [])
        logger.info("Starting scan: %d keywords, %d ISBNs", len(keywords), len(isbns))

        alerts: list[Alert] = []

        # Search by keywords
        for query in keywords:
            for scraper in self.discovery_scrapers:
                try:
                    listings = await scraper.search(query)
                    for listing in listings:
                        alert = await self._evaluate_listing(listing)
                        if alert:
                            alerts.append(alert)
                except Exception as e:
                    logger.error("Scraper %s failed on '%s': %s", scraper.platform_name, query, e)

                await self.http_client._rate_limit_delay()

        # Search by ISBN
        for isbn in isbns:
            for scraper in self.discovery_scrapers:
                try:
                    listings = await scraper.search(isbn)
                    for listing in listings:
                        alert = await self._evaluate_listing(listing)
                        if alert:
                            alerts.append(alert)
                except Exception as e:
                    logger.error("Scraper %s failed on ISBN %s: %s", scraper.platform_name, isbn, e)

                await self.http_client._rate_limit_delay()

        # Send notifications
        for alert in alerts:
            if self.notifier:
                await self.notifier.send_alert(alert)
            self.db.save_alert(alert)

        logger.info("Scan complete: %d alerts generated", len(alerts))

    async def _evaluate_listing(self, listing) -> Alert | None:
        """Check if a listing is a good deal by querying buyback prices."""
        if not listing.isbn:
            return None

        # Dedup check
        if self.db.was_recently_alerted(listing.url, self.cooldown_hours):
            return None

        # Save listing
        self.db.save_listing(listing)

        # Get buyback prices from all buyback scrapers
        buyback_prices: dict[str, float] = {}
        for scraper in self.buyback_scrapers:
            try:
                price = await scraper.get_price(listing.isbn)
                if price is not None and price > 0:
                    buyback_prices[scraper.platform_name] = price
            except Exception as e:
                logger.debug("Buyback check failed on %s: %s", scraper.platform_name, e)

        if not buyback_prices:
            return None

        return self.engine.evaluate(listing, buyback_prices)

    def start(self) -> None:
        """Start the scheduler with periodic scan jobs."""
        self.scheduler.add_job(
            self.run_scan,
            "interval",
            minutes=self.interval,
            id="main_scan",
            name="Book scan cycle",
        )
        self.scheduler.start()
        logger.info("Scheduler started, scanning every %d minutes", self.interval)

    async def run_once(self) -> None:
        """Run a single scan (useful for testing / CLI)."""
        await self.run_scan()

    async def shutdown(self) -> None:
        """Clean shutdown."""
        self.scheduler.shutdown(wait=False)
        await self.http_client.close()
        self.db.close()
