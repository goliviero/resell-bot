"""Scan scheduler — continuous parallel loop scanning all ISBNs.

Strategy: scan every ISBN at the same frequency in an infinite loop.
Multi-platform: Momox (JSON API, fast) + RecycLivre (HTML, slower).
Each platform has its own rate limits and worker concurrency.
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
from resell_bot.scrapers.recyclivre import RecyclivreScraper
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
        # Momox: fast JSON API, aggressive rate limits OK
        self.http_client = HttpClient(
            user_agents=http_cfg.get("user_agents"),
            timeout=http_cfg.get("timeout_seconds", 15),
            max_retries=http_cfg.get("max_retries", 3),
            delay_min=self.delay_min,
            delay_max=self.delay_max,
        )

        # RecycLivre: HTML scraping, slow rate (2-4s delay, 1 worker)
        # ~0.3 req/s — conservative to avoid Cloudflare challenges
        self.http_client_recyclivre = HttpClient(
            user_agents=http_cfg.get("user_agents"),
            timeout=http_cfg.get("timeout_seconds", 15),
            max_retries=http_cfg.get("max_retries", 2),
            delay_min=2.0,
            delay_max=4.0,
        )

        self.scrapers: list[BaseScraper] = [
            MomoxApiScraper(self.http_client),
            RecyclivreScraper(self.http_client_recyclivre),
        ]

        self.cooldown_hours = settings.get("dedup", {}).get("cooldown_hours", 24)
        self.scheduler = AsyncIOScheduler()
        self._running = False
        self._scan_task: asyncio.Task | None = None
        self._auto_restart_task: asyncio.Task | None = None
        self._loop: asyncio.AbstractEventLoop | None = None  # main event loop ref
        # Per-platform concurrency limits
        self._semaphores: dict[str, asyncio.Semaphore] = {
            "momox_shop": asyncio.Semaphore(self.max_workers),
            "recyclivre": asyncio.Semaphore(1),
        }
        self._alert_lock = asyncio.Lock()

        # Live scan status for dashboard — per-platform
        _empty_status = {
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
        self.scan_status: dict = {
            "momox_shop": {**_empty_status},
            "recyclivre": {**_empty_status},
        }
        # Convenience — overall running flag
        self._global_running_flag = False

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
            # Always save listing when available (for URL tracking in books page)
            self.db.save_listing(listing)
            if changed:
                logger.info("RESTOCK: %s now AVAILABLE on %s at %.2f€",
                            isbn, scraper.platform_name, listing.price)
        else:
            self.db.upsert_availability(isbn, scraper.platform_name, False)
            return None

        # Only alert on restock (unavailable → available transition).
        # If the book was already known as available, skip — no repeat notifications.
        if not changed:
            return None

        # Check deal
        alert = price_engine.evaluate(listing, max_buy_price)
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
        """Scan one ISBN within a per-platform semaphore-controlled worker."""
        sem = self._semaphores.get(scraper.platform_name, asyncio.Semaphore(2))
        async with sem:
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
            pstatus = self.scan_status[scraper.platform_name]
            pstatus["scanned_count"] = counters["scanned"]
            pstatus["deals_found"] = counters["deals"]
            pstatus["available_found"] = counters["available"]

            # Rate limit per worker — use scraper's client delays
            if hasattr(scraper, 'client') and hasattr(scraper.client, 'delay_min'):
                delay = random.uniform(scraper.client.delay_min, scraper.client.delay_max)
            else:
                delay = random.uniform(self.delay_min, self.delay_max)
            await asyncio.sleep(delay)

    async def _platform_loop(self, scraper: BaseScraper) -> None:
        """Independent scan loop for one platform. Runs forever until stopped."""
        pname = scraper.platform_name
        pstatus = self.scan_status[pname]

        while self._running:
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
            pstatus.update({
                "running": True,
                "scanned_count": 0,
                "total_count": total,
                "deals_found": 0,
                "available_found": 0,
                "cycle_start": cycle_start.isoformat(),
            })

            logger.info(
                "[%s] Cycle %d: scanning %d ISBNs",
                pname, pstatus["cycle_count"] + 1, total,
            )

            counters = {"scanned": 0, "deals": 0, "available": 0}

            # Launch all workers — per-platform semaphore limits concurrency
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
            pstatus.update({
                "running": False,
                "cycle_count": pstatus["cycle_count"] + 1,
                "last_completed": cycle_end.isoformat(),
                "last_cycle_duration": duration,
            })

            logger.info(
                "[%s] Cycle %d complete: %d ISBNs in %.0fs (%.1f min), %d available, %d deals",
                pname, pstatus["cycle_count"], total, duration, duration / 60,
                counters["available"], counters["deals"],
            )

            # Auto-expire unavailable alerts older than 3h (once per full round)
            if pname == "momox_shop":
                self.db.expire_unavailable_alerts(hours=2)

        pstatus["running"] = False

    async def run_continuous(self) -> None:
        """Launch all platform scan loops in parallel.

        Each platform runs independently with its own concurrency and rate limits.
        Momox (~3 min/cycle) is NOT blocked by RecycLivre (~17 min/cycle).
        """
        self._running = True
        logger.info(
            "Starting parallel scan: %s",
            ", ".join(f"{s.platform_name}" for s in self.scrapers),
        )

        try:
            # One task per platform — fully independent
            platform_tasks = [
                asyncio.create_task(self._platform_loop(scraper))
                for scraper in self.scrapers
            ]
            await asyncio.gather(*platform_tasks, return_exceptions=True)
        except asyncio.CancelledError:
            logger.info("Scan loop cancelled")
        finally:
            self._running = False
            for ps in self.scan_status.values():
                ps["running"] = False
            logger.info("Scan loop stopped")

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

    def _get_loop(self) -> asyncio.AbstractEventLoop:
        """Get the main event loop (may be called from another thread)."""
        if self._loop is not None:
            return self._loop
        return asyncio.get_running_loop()

    def start_scan(self) -> None:
        """Start the continuous scan loop as a background task.

        Thread-safe: can be called from the web thread (uvicorn) or main thread.
        """
        if self._scan_task and not self._scan_task.done():
            return  # Already running
        # Cancel any pending auto-restart
        if self._auto_restart_task and not self._auto_restart_task.done():
            self._auto_restart_task.cancel()
            self._auto_restart_task = None

        loop = self._get_loop()

        def _create_task() -> None:
            self._scan_task = loop.create_task(self.run_continuous())
            logger.info("Scan task started")

        if loop.is_running() and loop != getattr(asyncio, '_running_loop', None):
            loop.call_soon_threadsafe(_create_task)
        else:
            _create_task()

    def stop_scan(self, auto_restart_hours: float = 1.0) -> None:
        """Stop the scan loop. Auto-restarts after auto_restart_hours.

        Pass auto_restart_hours=0 to disable auto-restart (buyer handles restart).
        Thread-safe: can be called from the web thread (uvicorn) or main thread.
        """
        self._running = False
        for ps in self.scan_status.values():
            ps["running"] = False
        if self._scan_task and not self._scan_task.done():
            self._scan_task.cancel()
        self._scan_task = None

        # Skip auto-restart when explicitly 0 (buyer will restart manually)
        if auto_restart_hours <= 0:
            logger.info("Scan stopped — no auto-restart (buyer mode)")
            return

        logger.info("Scan stopped — auto-restart in %.0f min", auto_restart_hours * 60)

        loop = self._get_loop()

        def _schedule_restart() -> None:
            self._auto_restart_task = loop.create_task(
                self._auto_restart(auto_restart_hours)
            )

        if loop.is_running() and loop != getattr(asyncio, '_running_loop', None):
            loop.call_soon_threadsafe(_schedule_restart)
        else:
            _schedule_restart()

    async def _auto_restart(self, hours: float) -> None:
        """Wait then auto-restart the scan loop."""
        try:
            await asyncio.sleep(hours * 3600)
            logger.info("Auto-restarting scan after %.0f min pause", hours * 60)
            self.start_scan()
        except asyncio.CancelledError:
            pass  # Cancelled because user manually restarted

    async def send_daily_digest(self) -> None:
        """Send daily recap of active deals to Discord only."""
        if not self.notifier:
            return

        deals = self.db.get_available_deals()
        if not deals:
            logger.info("Daily digest: no deals currently available")
            return

        logger.info("Daily digest: %d deals to send", len(deals))
        await self.notifier.send_daily_digest(deals)

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
        await self.http_client_recyclivre.close()
        self.db.close()
