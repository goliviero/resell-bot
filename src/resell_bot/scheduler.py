"""Scan scheduler — parallel scanning with priority tiers (HOT/WARM/COLD)."""

import asyncio
import logging
from datetime import datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from resell_bot.core.database import Database
from resell_bot.core.models import Alert
from resell_bot.core import price_engine
from resell_bot.core.notifier import Notifier
from resell_bot.priority import refresh_priorities
from resell_bot.scrapers.base import BaseScraper
from resell_bot.scrapers.momox_api import MomoxApiScraper
from resell_bot.utils.http_client import HttpClient

logger = logging.getLogger(__name__)

# Default priority intervals (seconds)
DEFAULT_INTERVALS = {
    "hot": 120,      # 2 min
    "warm": 1200,    # 20 min
    "cold": 14400,   # 4 hours
}
DEFAULT_MAX_WORKERS = 3


class ScanScheduler:
    """Scans all reference ISBNs against sale platforms with priority tiers."""

    def __init__(
        self,
        settings: dict,
        db: Database,
        notifier: Notifier | None,
    ) -> None:
        self.settings = settings
        self.db = db
        self.notifier = notifier

        scan_cfg = settings.get("scan", {})
        self.delay_min = scan_cfg.get("delay_between_requests", {}).get("min_seconds", 0.5)
        self.delay_max = scan_cfg.get("delay_between_requests", {}).get("max_seconds", 1.5)
        self.max_workers = scan_cfg.get("max_concurrent_workers", DEFAULT_MAX_WORKERS)

        # Priority intervals
        priorities_cfg = scan_cfg.get("priorities", {})
        self.intervals = {
            tier: priorities_cfg.get(tier, {}).get("interval_seconds", DEFAULT_INTERVALS[tier])
            for tier in ("hot", "warm", "cold")
        }

        http_cfg = settings.get("http", {})
        self.http_client = HttpClient(
            user_agents=http_cfg.get("user_agents"),
            timeout=http_cfg.get("timeout_seconds", 15),
            max_retries=http_cfg.get("max_retries", 3),
            delay_min=self.delay_min,
            delay_max=self.delay_max,
        )

        # Use Medimops JSON API as primary scraper (fast, no Cloudflare)
        self.scrapers: list[BaseScraper] = [
            MomoxApiScraper(self.http_client),
        ]

        self.cooldown_hours = settings.get("dedup", {}).get("cooldown_hours", 24)
        self.semaphore = asyncio.Semaphore(self.max_workers)
        self.scheduler = AsyncIOScheduler()

        # Track last scan time per tier
        self._last_scan: dict[str, datetime] = {}
        # Live scan status for dashboard
        self.scan_status: dict = {
            "running": False,
            "current_tier": None,
            "scanned_count": 0,
            "total_count": 0,
            "deals_found": 0,
            "available_found": 0,
            "last_completed": None,
            "tier_last_scan": {},
            "tier_counts": {},
        }

    async def _scan_isbn(
        self,
        isbn: str,
        max_buy_price: float,
        scraper: BaseScraper,
    ) -> Alert | None:
        """Scan a single ISBN on a single platform. Returns Alert if deal found."""
        async with self.semaphore:
            try:
                listing = await scraper.get_offer(isbn)
            except Exception as e:
                logger.debug("%s error for %s: %s", scraper.platform_name, isbn, e)
                return None

            # Update availability tracking
            if listing:
                changed = self.db.upsert_availability(
                    isbn, scraper.platform_name, True, listing.price,
                )
                if changed:
                    logger.info("Status change: %s now AVAILABLE on %s at %.2f€",
                                isbn, scraper.platform_name, listing.price)
            else:
                self.db.upsert_availability(isbn, scraper.platform_name, False)
                return None

            # Check deal
            alert = price_engine.evaluate(listing, max_buy_price)
            if alert is None:
                return None

            # Save listing (dedup by URL)
            self.db.save_listing(listing)

            # Rate limit
            await self.http_client._rate_limit_delay()
            return alert

    async def _scan_tier(self, tier: str) -> list[Alert]:
        """Scan all ISBNs in a priority tier across all scrapers."""
        alerts: list[Alert] = []

        for scraper in self.scrapers:
            platform = scraper.platform_name

            # Get ISBNs for this tier
            isbns = self.db.get_isbns_by_priority(platform, tier)
            isbn_list = [
                (r["isbn"], r["max_buy_price"])
                for r in isbns
                if r.get("max_buy_price") is not None
            ]

            # Unchecked ISBNs: dispatch to the right tier based on value
            if tier in ("hot", "cold"):
                unchecked = self.db.get_unchecked_isbns(platform)
                for r in unchecked:
                    mbp = r.get("max_buy_price")
                    if mbp is None:
                        continue
                    # High-value unchecked → scan in HOT tier
                    if mbp >= 50.0 and tier == "hot":
                        isbn_list.append((r["isbn"], mbp))
                    # Low-value unchecked → scan in COLD tier
                    elif mbp < 50.0 and tier == "cold":
                        isbn_list.append((r["isbn"], mbp))

            if not isbn_list:
                continue

            logger.info(
                "Scanning %s tier: %d ISBNs on %s",
                tier.upper(), len(isbn_list), platform,
            )

            # Update live status
            self.scan_status["running"] = True
            self.scan_status["current_tier"] = tier
            self.scan_status["scanned_count"] = 0
            self.scan_status["total_count"] = len(isbn_list)
            self.scan_status["deals_found"] = 0
            self.scan_status["available_found"] = 0

            # Launch parallel scans with progress tracking
            completed = 0
            available = 0

            async def _tracked_scan(isbn: str, max_price: float) -> Alert | None:
                nonlocal completed, available
                result = await self._scan_isbn(isbn, max_price, scraper)
                completed += 1
                self.scan_status["scanned_count"] = completed
                if result is not None:
                    self.scan_status["deals_found"] += 1
                return result

            tasks = [
                _tracked_scan(isbn, max_price)
                for isbn, max_price in isbn_list
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for result in results:
                if isinstance(result, Alert):
                    alerts.append(result)
                elif isinstance(result, Exception):
                    logger.debug("Scan task error: %s", result)

            # Update tier tracking
            now = datetime.now().isoformat()
            self.scan_status["tier_last_scan"][tier] = now
            self.scan_status["tier_counts"][tier] = len(isbn_list)
            self.scan_status["running"] = False
            self.scan_status["current_tier"] = None
            self.scan_status["last_completed"] = now

        return alerts

    async def _process_alerts(self, alerts: list[Alert]) -> None:
        """Save alerts, send notifications."""
        # Reload notification settings from DB (user may have changed them via dashboard)
        if self.notifier and alerts:
            settings = self.db.get_all_notification_settings()
            self.notifier.configure_from_settings(settings)

        for alert in alerts:
            # Dedup check
            if self.db.was_recently_alerted(alert.listing.url, self.cooldown_hours):
                continue

            self.db.save_alert(alert)
            if self.notifier:
                await self.notifier.send_alert(alert)
            logger.info(
                "DEAL: %s — %.2f€ on %s (budget %.2f€, savings %.2f€)",
                alert.listing.title,
                alert.listing.price,
                alert.listing.platform,
                alert.max_buy_price,
                alert.savings,
            )

    async def run_scan(self) -> None:
        """Run a full scan cycle — checks each tier if its interval has elapsed."""
        now = datetime.now()

        for tier in ("hot", "warm", "cold"):
            last = self._last_scan.get(tier)
            interval = timedelta(seconds=self.intervals[tier])

            if last and (now - last) < interval:
                continue

            self._last_scan[tier] = now
            alerts = await self._scan_tier(tier)
            await self._process_alerts(alerts)

        # Refresh priorities after scan
        for scraper in self.scrapers:
            refresh_priorities(self.db, scraper.platform_name)

    async def run_once(self) -> None:
        """Run a single full scan of all ISBNs (ignores priority tiers)."""
        logger.info("Running single full scan...")

        for scraper in self.scrapers:
            platform = scraper.platform_name
            refs = self.db.get_all_reference_isbns()
            isbn_list = [
                (r["isbn"], r["max_buy_price"])
                for r in refs
                if r.get("max_buy_price") is not None
            ]

            logger.info("Full scan: %d ISBNs on %s with %d workers",
                        len(isbn_list), platform, self.max_workers)

            tasks = [
                self._scan_isbn(isbn, max_price, scraper)
                for isbn, max_price in isbn_list
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            alerts = [r for r in results if isinstance(r, Alert)]
            errors = sum(1 for r in results if isinstance(r, Exception))
            available = sum(1 for r in results if r is not None and not isinstance(r, Exception))

            logger.info(
                "Full scan complete: %d ISBNs, %d available, %d deals, %d errors",
                len(isbn_list), available, len(alerts), errors,
            )

            await self._process_alerts(alerts)
            refresh_priorities(self.db, platform)

    async def send_daily_digest(self) -> None:
        """Send daily recap of all currently available deals."""
        # Reload notification settings from DB before sending
        if self.notifier:
            settings = self.db.get_all_notification_settings()
            self.notifier.configure_from_settings(settings)

        deals = self.db.get_available_deals()
        if not deals:
            logger.info("Daily digest: no deals currently available")
            return

        logger.info("Daily digest: %d deals to send", len(deals))
        if self.notifier:
            await self.notifier.send_digest(deals)

    def start(self) -> None:
        """Start periodic scanning — runs every 30s, tier intervals control actual scanning."""
        self.scheduler.add_job(
            self.run_scan,
            "interval",
            seconds=30,
            id="priority_scan",
            name="Priority-based scan cycle",
        )
        # Daily digest at 8:00 AM
        self.scheduler.add_job(
            self.send_daily_digest,
            "cron",
            hour=8,
            minute=0,
            id="daily_digest",
            name="Daily deals digest",
        )
        self.scheduler.start()
        logger.info(
            "Scheduler started — HOT every %ds, WARM every %ds, COLD every %ds, %d workers, digest at 08:00",
            self.intervals["hot"], self.intervals["warm"], self.intervals["cold"],
            self.max_workers,
        )

    async def shutdown(self) -> None:
        """Clean shutdown."""
        self.scheduler.shutdown(wait=False)
        await self.http_client.close()
        self.db.close()
