"""Scan scheduler — continuous parallel loop scanning all ISBNs.

Strategy: scan every ISBN at the same frequency in an infinite loop.
Uses asyncio.Semaphore for parallel workers on the Medimops JSON API
(~80ms/req, no Cloudflare). 3 workers × 0.3s delay = ~10 req/s peak.
Full cycle ~3 min for 1380 ISBNs with 1 IP.
"""

import asyncio
import logging
import random
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from resell_bot.core.database import Database
from resell_bot.core.models import Alert
from resell_bot.core import price_engine
from resell_bot.core.notifier import Notifier
from resell_bot.scrapers.base import BaseScraper
from resell_bot.scrapers.momox_api import MomoxApiScraper
from resell_bot.utils.http_client import HttpClient

logger = logging.getLogger(__name__)


class ScanScheduler:
    """Scans all reference ISBNs in a continuous parallel loop."""

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
        self.delay_min = scan_cfg.get("delay_between_requests", {}).get("min_seconds", 0.2)
        self.delay_max = scan_cfg.get("delay_between_requests", {}).get("max_seconds", 0.4)
        self.max_workers = scan_cfg.get("max_workers", 3)

        http_cfg = settings.get("http", {})
        self.http_client = HttpClient(
            user_agents=http_cfg.get("user_agents"),
            timeout=http_cfg.get("timeout_seconds", 15),
            max_retries=http_cfg.get("max_retries", 3),
            delay_min=self.delay_min,
            delay_max=self.delay_max,
        )

        self.scrapers: list[BaseScraper] = [
            MomoxApiScraper(self.http_client),
        ]

        self.cooldown_hours = settings.get("dedup", {}).get("cooldown_hours", 24)
        self.scheduler = AsyncIOScheduler()
        self._running = False
        self._semaphore = asyncio.Semaphore(self.max_workers)
        self._alert_lock = asyncio.Lock()

        # Live scan status for dashboard
        self.scan_status: dict = {
            "running": False,
            "scanned_count": 0,
            "total_count": 0,
            "cycle_count": 0,
            "deals_found": 0,
            "available_found": 0,
            "cycle_start": None,
            "last_completed": None,
            "last_cycle_duration": None,
        }

    async def _scan_single(
        self,
        isbn: str,
        max_buy_price: float,
        scraper: BaseScraper,
    ) -> Alert | None:
        """Scan one ISBN. Returns Alert if deal found."""
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
                logger.info("RESTOCK: %s now AVAILABLE on %s at %.2f€",
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
        return alert

    async def _process_alert(self, alert: Alert) -> None:
        """Save alert, send notifications immediately. Thread-safe via lock."""
        async with self._alert_lock:
            if self.db.was_recently_alerted(alert.listing.url, self.cooldown_hours):
                return

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

    async def _scan_worker(
        self,
        isbn: str,
        max_price: float,
        scraper: BaseScraper,
        counters: dict,
    ) -> None:
        """Scan one ISBN within a semaphore-controlled worker."""
        async with self._semaphore:
            if not self._running:
                return

            alert = await self._scan_single(isbn, max_price, scraper)

            if alert:
                counters["deals"] += 1
                counters["available"] += 1
                await self._process_alert(alert)
            else:
                row = self.db.conn.execute(
                    "SELECT status FROM isbn_availability WHERE isbn=? AND platform=?",
                    (isbn, scraper.platform_name),
                ).fetchone()
                if row and row["status"] == "available":
                    counters["available"] += 1

            counters["scanned"] += 1
            self.scan_status["scanned_count"] = counters["scanned"]
            self.scan_status["deals_found"] = counters["deals"]
            self.scan_status["available_found"] = counters["available"]

            # Rate limit per worker
            delay = random.uniform(self.delay_min, self.delay_max)
            await asyncio.sleep(delay)

    async def run_continuous(self) -> None:
        """Main loop: scan all ISBNs with parallel workers, forever.

        Uses asyncio.Semaphore to limit concurrent requests.
        3 workers × 0.3s delay on Medimops JSON API = ~10 req/s peak.
        Randomize order each cycle to avoid detectable patterns.
        """
        self._running = True
        logger.info(
            "Starting continuous scan loop (%d parallel workers, %.1f-%.1fs delay)",
            self.max_workers, self.delay_min, self.delay_max,
        )

        while self._running:
            for scraper in self.scrapers:
                # Build full ISBN list each cycle (picks up DB changes)
                refs = self.db.get_all_reference_isbns()
                isbn_list = [
                    (r["isbn"], r["max_buy_price"])
                    for r in refs
                    if r.get("max_buy_price") is not None
                ]

                random.shuffle(isbn_list)

                total = len(isbn_list)
                cycle_start = datetime.now()
                self.scan_status.update({
                    "running": True,
                    "scanned_count": 0,
                    "total_count": total,
                    "deals_found": 0,
                    "available_found": 0,
                    "cycle_start": cycle_start.isoformat(),
                })

                logger.info(
                    "Cycle %d: scanning %d ISBNs on %s (%d workers)",
                    self.scan_status["cycle_count"] + 1, total,
                    scraper.platform_name, self.max_workers,
                )

                counters = {"scanned": 0, "deals": 0, "available": 0}

                # Launch all workers — semaphore limits concurrency
                tasks = [
                    asyncio.create_task(
                        self._scan_worker(isbn, max_price, scraper, counters)
                    )
                    for isbn, max_price in isbn_list
                ]
                await asyncio.gather(*tasks, return_exceptions=True)

                # Cycle complete
                cycle_end = datetime.now()
                duration = (cycle_end - cycle_start).total_seconds()
                self.scan_status.update({
                    "cycle_count": self.scan_status["cycle_count"] + 1,
                    "last_completed": cycle_end.isoformat(),
                    "last_cycle_duration": duration,
                })

                logger.info(
                    "Cycle %d complete: %d ISBNs in %.0fs (%.1f min), %d available, %d deals",
                    self.scan_status["cycle_count"], total, duration, duration / 60,
                    counters["available"], counters["deals"],
                )

    async def run_once(self) -> None:
        """Run a single full scan (for --once mode) with parallel workers."""
        logger.info("Running single full scan (%d workers)...", self.max_workers)

        for scraper in self.scrapers:
            refs = self.db.get_all_reference_isbns()
            isbn_list = [
                (r["isbn"], r["max_buy_price"])
                for r in refs
                if r.get("max_buy_price") is not None
            ]

            logger.info("Full scan: %d ISBNs on %s", len(isbn_list), scraper.platform_name)

            counters = {"scanned": 0, "deals": 0, "available": 0}

            tasks = [
                asyncio.create_task(
                    self._scan_worker(isbn, max_price, scraper, counters)
                )
                for isbn, max_price in isbn_list
            ]
            await asyncio.gather(*tasks, return_exceptions=True)

            logger.info(
                "Full scan complete: %d ISBNs, %d available, %d deals",
                len(isbn_list), counters["available"], counters["deals"],
            )

    async def send_daily_digest(self) -> None:
        """Send daily recap of all currently available deals."""
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
        """Start the daily digest scheduler (continuous scan runs separately)."""
        self.scheduler.add_job(
            self.send_daily_digest,
            "cron",
            hour=8,
            minute=0,
            id="daily_digest",
            name="Daily deals digest",
        )
        self.scheduler.start()
        avg_delay = (self.delay_min + self.delay_max) / 2
        effective_rps = self.max_workers / avg_delay
        n_isbns = len(self.db.get_all_reference_isbns())
        estimated_cycle = n_isbns * avg_delay / self.max_workers
        logger.info(
            "Scheduler started — %d workers, ~%.0f req/s, estimated cycle %.0fs (%.1f min), digest at 08:00",
            self.max_workers, effective_rps, estimated_cycle, estimated_cycle / 60,
        )

    async def shutdown(self) -> None:
        """Clean shutdown."""
        self._running = False
        self.scan_status["running"] = False
        self.scheduler.shutdown(wait=False)
        await self.http_client.close()
        self.db.close()
