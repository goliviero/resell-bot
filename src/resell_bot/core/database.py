"""SQLite database for listings, alerts, reference prices, and dedup tracking."""

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from resell_bot.core.models import Alert, AlertStatus, Listing, ReferencePrice
from resell_bot.utils.crypto import decrypt, encrypt

DB_SCHEMA = """
CREATE TABLE IF NOT EXISTS listings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    price REAL NOT NULL,
    url TEXT NOT NULL UNIQUE,
    platform TEXT NOT NULL,
    isbn TEXT,
    condition TEXT,
    seller TEXT,
    author TEXT,
    found_at TEXT NOT NULL,
    image_url TEXT
);

CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_url TEXT NOT NULL,
    max_buy_price REAL NOT NULL,
    savings REAL NOT NULL,
    notified_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'new',
    FOREIGN KEY (listing_url) REFERENCES listings(url)
);

CREATE TABLE IF NOT EXISTS reference_prices (
    isbn TEXT PRIMARY KEY,
    title TEXT,
    author TEXT,
    url TEXT,
    max_buy_price REAL,
    source TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS isbn_availability (
    isbn TEXT NOT NULL,
    platform TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'unknown',
    last_price REAL,
    last_checked_at TEXT NOT NULL,
    last_changed_at TEXT,
    check_count INTEGER DEFAULT 0,
    times_available INTEGER DEFAULT 0,
    priority TEXT DEFAULT 'cold',
    PRIMARY KEY (isbn, platform)
);

CREATE TABLE IF NOT EXISTS notification_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS discord_webhooks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    url TEXT NOT NULL UNIQUE,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS email_configs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    label TEXT NOT NULL,
    email_to TEXT NOT NULL,
    smtp_host TEXT NOT NULL,
    smtp_port INTEGER NOT NULL DEFAULT 587,
    smtp_user TEXT NOT NULL,
    smtp_password TEXT NOT NULL,
    smtp_use_tls INTEGER NOT NULL DEFAULT 1,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_listings_isbn ON listings(isbn);
CREATE INDEX IF NOT EXISTS idx_listings_url ON listings(url);
CREATE INDEX IF NOT EXISTS idx_alerts_listing_url ON alerts(listing_url);
CREATE INDEX IF NOT EXISTS idx_alerts_status ON alerts(status);
CREATE INDEX IF NOT EXISTS idx_availability_priority ON isbn_availability(priority, platform);
"""

# Migrations for existing databases
MIGRATIONS = [
    "ALTER TABLE alerts ADD COLUMN status TEXT NOT NULL DEFAULT 'new'",
    "ALTER TABLE reference_prices ADD COLUMN title TEXT",
    "ALTER TABLE reference_prices ADD COLUMN author TEXT",
    "ALTER TABLE reference_prices ADD COLUMN url TEXT",
    "ALTER TABLE reference_prices ADD COLUMN max_buy_price REAL",
    "UPDATE reference_prices SET max_buy_price = min_buy_price WHERE max_buy_price IS NULL",
    "ALTER TABLE alerts ADD COLUMN max_buy_price REAL NOT NULL DEFAULT 0",
    "ALTER TABLE alerts ADD COLUMN savings REAL NOT NULL DEFAULT 0",
    "UPDATE alerts SET max_buy_price = buyback_price, savings = estimated_margin WHERE max_buy_price = 0 AND buyback_price IS NOT NULL",
]


class Database:
    """Thin wrapper around sqlite3 for resell-bot storage."""

    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()
        self._run_migrations()

    def _init_schema(self) -> None:
        self.conn.executescript(DB_SCHEMA)
        self.conn.commit()

    def _run_migrations(self) -> None:
        for sql in MIGRATIONS:
            try:
                self.conn.execute(sql)
                self.conn.commit()
            except sqlite3.OperationalError:
                pass  # column already exists

    # ── Listings ──────────────────────────────────────────────

    def save_listing(self, listing: Listing) -> bool:
        """Insert a listing. Returns True if new, False if duplicate (same URL)."""
        try:
            self.conn.execute(
                """INSERT INTO listings
                   (title, price, url, platform, isbn, condition, seller, author, found_at, image_url)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    listing.title,
                    listing.price,
                    listing.url,
                    listing.platform,
                    listing.isbn,
                    listing.condition,
                    listing.seller,
                    listing.author,
                    listing.found_at.isoformat(),
                    listing.image_url,
                ),
            )
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def get_listings_by_isbn(self, isbn: str) -> list[dict]:
        """Retrieve all listings for a given ISBN."""
        rows = self.conn.execute(
            "SELECT * FROM listings WHERE isbn = ? ORDER BY price ASC",
            (isbn,),
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Alerts ────────────────────────────────────────────────

    def save_alert(self, alert: Alert) -> int:
        """Record a sent alert. Returns the new alert ID."""
        cursor = self.conn.execute(
            """INSERT INTO alerts
               (listing_url, max_buy_price, savings, notified_at, status)
               VALUES (?, ?, ?, ?, ?)""",
            (
                alert.listing.url,
                alert.max_buy_price,
                alert.savings,
                datetime.now().isoformat(),
                alert.status.value,
            ),
        )
        self.conn.commit()
        return cursor.lastrowid  # type: ignore[return-value]

    def was_recently_alerted(self, url: str, cooldown_hours: int = 24) -> bool:
        """Check if we already sent an alert for this URL within the cooldown."""
        cutoff = (datetime.now() - timedelta(hours=cooldown_hours)).isoformat()
        row = self.conn.execute(
            "SELECT 1 FROM alerts WHERE listing_url = ? AND notified_at > ?",
            (url, cutoff),
        ).fetchone()
        return row is not None

    def get_alerts(
        self,
        status: AlertStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        """Get alerts with listing info + live availability, newest first."""
        query = """
            SELECT a.id, a.max_buy_price, a.savings,
                   a.notified_at, a.status,
                   l.title, l.price AS buy_price, l.url, l.platform, l.isbn,
                   l.author, l.image_url, l.condition,
                   ia.status AS live_availability
            FROM alerts a
            JOIN listings l ON a.listing_url = l.url
            LEFT JOIN isbn_availability ia ON l.isbn = ia.isbn AND l.platform = ia.platform
        """
        params: list = []
        if status is not None:
            query += " WHERE a.status = ?"
            params.append(status.value)
        query += " ORDER BY a.notified_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        rows = self.conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def get_alert_by_id(self, alert_id: int) -> dict | None:
        """Get a single alert with listing info + live availability."""
        row = self.conn.execute(
            """SELECT a.id, a.max_buy_price, a.savings,
                      a.notified_at, a.status,
                      l.title, l.price AS buy_price, l.url, l.platform, l.isbn,
                      l.author, l.image_url, l.condition,
                      ia.status AS live_availability
               FROM alerts a
               JOIN listings l ON a.listing_url = l.url
               LEFT JOIN isbn_availability ia ON l.isbn = ia.isbn AND l.platform = ia.platform
               WHERE a.id = ?""",
            (alert_id,),
        ).fetchone()
        return dict(row) if row else None

    def update_alert_status(self, alert_id: int, status: AlertStatus) -> bool:
        """Update the status of an alert. Returns True if found."""
        cursor = self.conn.execute(
            "UPDATE alerts SET status = ? WHERE id = ?",
            (status.value, alert_id),
        )
        self.conn.commit()
        return cursor.rowcount > 0

    def mark_all_new_as_seen(self) -> int:
        """Mark all NEW alerts as SEEN. Returns number of alerts updated."""
        cursor = self.conn.execute(
            "UPDATE alerts SET status = ? WHERE status = ?",
            (AlertStatus.SEEN.value, AlertStatus.NEW.value),
        )
        self.conn.commit()
        return cursor.rowcount

    def get_alert_stats(self) -> dict:
        """Count alerts by status."""
        rows = self.conn.execute(
            "SELECT status, COUNT(*) as count FROM alerts GROUP BY status"
        ).fetchall()
        stats = {s.value: 0 for s in AlertStatus}
        for row in rows:
            stats[row["status"]] = row["count"]
        stats["total"] = sum(stats.values())
        return stats

    # ── Reference Prices (Watchlist) ─────────────────────────

    def upsert_reference_price(self, ref: ReferencePrice) -> None:
        """Insert or update a reference price for an ISBN."""
        self.conn.execute(
            """INSERT INTO reference_prices (isbn, title, author, url, max_buy_price, source, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(isbn) DO UPDATE SET
                   title = COALESCE(excluded.title, title),
                   author = COALESCE(excluded.author, author),
                   url = COALESCE(excluded.url, url),
                   max_buy_price = COALESCE(excluded.max_buy_price, max_buy_price),
                   source = excluded.source,
                   updated_at = excluded.updated_at""",
            (
                ref.isbn,
                ref.title,
                ref.author,
                ref.url,
                ref.max_buy_price,
                ref.source,
                (ref.updated_at or datetime.now()).isoformat(),
            ),
        )
        self.conn.commit()

    def get_all_reference_isbns(self) -> list[dict]:
        """Get all reference ISBNs for scanning."""
        rows = self.conn.execute(
            "SELECT * FROM reference_prices ORDER BY updated_at ASC"
        ).fetchall()
        return [dict(r) for r in rows]

    def get_reference_price(self, isbn: str) -> dict | None:
        """Get reference price for an ISBN."""
        row = self.conn.execute(
            "SELECT * FROM reference_prices WHERE isbn = ?",
            (isbn,),
        ).fetchone()
        return dict(row) if row else None

    def bulk_upsert_reference_prices(self, refs: list[ReferencePrice]) -> int:
        """Bulk insert/update reference prices. Returns count inserted."""
        now = datetime.now().isoformat()
        data = [
            (r.isbn, r.title, r.author, r.url, r.max_buy_price, r.source,
             (r.updated_at or now) if r.updated_at else now)
            for r in refs
        ]
        self.conn.executemany(
            """INSERT INTO reference_prices (isbn, title, author, url, max_buy_price, source, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(isbn) DO UPDATE SET
                   title = COALESCE(excluded.title, title),
                   author = COALESCE(excluded.author, author),
                   url = COALESCE(excluded.url, url),
                   max_buy_price = COALESCE(excluded.max_buy_price, max_buy_price),
                   source = excluded.source,
                   updated_at = excluded.updated_at""",
            data,
        )
        self.conn.commit()
        return len(data)

    # ── ISBN Availability Tracking ─────────────────────────────

    def upsert_availability(
        self,
        isbn: str,
        platform: str,
        in_stock: bool,
        price: float | None = None,
    ) -> bool:
        """Update availability tracking. Returns True if status changed."""
        now = datetime.now().isoformat()
        new_status = "available" if in_stock else "unavailable"

        existing = self.conn.execute(
            "SELECT status, times_available FROM isbn_availability WHERE isbn = ? AND platform = ?",
            (isbn, platform),
        ).fetchone()

        if existing:
            old_status = existing["status"]
            changed = old_status != new_status
            times_avail = existing["times_available"] + (1 if in_stock and changed else 0)
            self.conn.execute(
                """UPDATE isbn_availability
                   SET status = ?, last_price = ?, last_checked_at = ?,
                       last_changed_at = CASE WHEN ? THEN ? ELSE last_changed_at END,
                       check_count = check_count + 1,
                       times_available = ?
                   WHERE isbn = ? AND platform = ?""",
                (new_status, price, now, changed, now, times_avail, isbn, platform),
            )
        else:
            changed = True
            self.conn.execute(
                """INSERT INTO isbn_availability
                   (isbn, platform, status, last_price, last_checked_at, last_changed_at, check_count, times_available, priority)
                   VALUES (?, ?, ?, ?, ?, ?, 1, ?, 'cold')""",
                (isbn, platform, new_status, price, now, now, 1 if in_stock else 0),
            )
        self.conn.commit()
        return changed

    def get_isbns_by_priority(self, platform: str, priority: str) -> list[dict]:
        """Get ISBNs for a given priority tier."""
        rows = self.conn.execute(
            """SELECT ia.isbn, ia.status, ia.last_price, ia.last_checked_at,
                      ia.times_available, ia.priority,
                      rp.max_buy_price, rp.title, rp.author
               FROM isbn_availability ia
               JOIN reference_prices rp ON ia.isbn = rp.isbn
               WHERE ia.platform = ? AND ia.priority = ?
               ORDER BY ia.last_checked_at ASC""",
            (platform, priority),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_unchecked_isbns(self, platform: str) -> list[dict]:
        """Get watchlist ISBNs that have never been checked on this platform."""
        rows = self.conn.execute(
            """SELECT rp.isbn, rp.max_buy_price, rp.title, rp.author
               FROM reference_prices rp
               LEFT JOIN isbn_availability ia ON rp.isbn = ia.isbn AND ia.platform = ?
               WHERE ia.isbn IS NULL AND rp.max_buy_price IS NOT NULL""",
            (platform,),
        ).fetchall()
        return [dict(r) for r in rows]

    def update_priority(self, isbn: str, platform: str, priority: str) -> None:
        """Set the priority tier for an ISBN."""
        self.conn.execute(
            "UPDATE isbn_availability SET priority = ? WHERE isbn = ? AND platform = ?",
            (priority, isbn, platform),
        )
        self.conn.commit()

    def bulk_update_priorities(self, updates: list[tuple[str, str, str]]) -> None:
        """Batch update priorities. Each tuple: (isbn, platform, priority)."""
        self.conn.executemany(
            "UPDATE isbn_availability SET priority = ? WHERE isbn = ? AND platform = ?",
            [(p, i, pl) for i, pl, p in updates],
        )
        self.conn.commit()

    def get_availability_stats(self, platform: str) -> dict:
        """Count ISBNs by priority and status for a platform."""
        rows = self.conn.execute(
            """SELECT priority, status, COUNT(*) as cnt
               FROM isbn_availability WHERE platform = ?
               GROUP BY priority, status""",
            (platform,),
        ).fetchall()
        stats: dict = {"hot": 0, "warm": 0, "cold": 0, "available": 0, "unavailable": 0}
        for row in rows:
            stats[row["priority"]] = stats.get(row["priority"], 0) + row["cnt"]
            stats[row["status"]] = stats.get(row["status"], 0) + row["cnt"]
        return stats

    # ── Books overview ────────────────────────────────────────

    def get_books_with_prices(
        self,
        search: str | None = None,
        sort: str = "title",
        limit: int = 50,
        offset: int = 0,
        availability_filter: str | None = None,
    ) -> list[dict]:
        """Get all watchlist books with Momox availability and prices.

        Joins reference_prices with isbn_availability for real-time status,
        and with listings for deal info.
        """
        query = """
            SELECT rp.isbn, rp.title, rp.author, rp.max_buy_price, rp.url AS cal_url,
                   ia.status AS momox_status, ia.last_price AS momox_price,
                   ia.last_checked_at, ia.priority, ia.times_available,
                   ml.url AS momox_url, ml.condition, ml.found_at
            FROM reference_prices rp
            LEFT JOIN isbn_availability ia ON rp.isbn = ia.isbn AND ia.platform = 'momox_shop'
            LEFT JOIN (
                SELECT isbn, url, condition, found_at,
                       ROW_NUMBER() OVER (PARTITION BY isbn ORDER BY price ASC) AS rn
                FROM listings
                WHERE platform = 'momox_shop'
            ) ml ON rp.isbn = ml.isbn AND ml.rn = 1
        """
        conditions: list[str] = []
        params: list = []
        if search:
            conditions.append("(rp.title LIKE ? OR rp.author LIKE ? OR rp.isbn LIKE ?)")
            like = f"%{search}%"
            params.extend([like, like, like])
        if availability_filter == "available":
            conditions.append("ia.status = 'available'")
        elif availability_filter == "unavailable":
            conditions.append("ia.status = 'unavailable' OR ia.status IS NULL")
        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        # Default: deals first (momox_price <= max_buy_price), then by margin desc
        sort_map = {
            "deals": "CASE WHEN ia.last_price IS NOT NULL AND ia.last_price <= rp.max_buy_price THEN 0 ELSE 1 END ASC, (rp.max_buy_price - ia.last_price) DESC",
            "title": "rp.title ASC",
            "price_asc": "ia.last_price ASC",
            "price_desc": "ia.last_price DESC",
            "margin": "(rp.max_buy_price - ia.last_price) DESC",
            "available": "CASE WHEN ia.status = 'available' THEN 0 WHEN ia.status = 'unavailable' THEN 1 ELSE 2 END ASC, rp.title ASC",
        }
        query += f" ORDER BY {sort_map.get(sort, sort_map['deals'])} LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        rows = self.conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def count_books(self, search: str | None = None, availability_filter: str | None = None) -> int:
        """Count total watchlist books (for pagination)."""
        query = "SELECT COUNT(*) AS cnt FROM reference_prices rp"
        conditions: list[str] = []
        params: list = []
        if availability_filter:
            query += " LEFT JOIN isbn_availability ia ON rp.isbn = ia.isbn AND ia.platform = 'momox_shop'"
            if availability_filter == "available":
                conditions.append("ia.status = 'available'")
            elif availability_filter == "unavailable":
                conditions.append("ia.status = 'unavailable' OR ia.status IS NULL")
        if search:
            conditions.append("(rp.title LIKE ? OR rp.author LIKE ? OR rp.isbn LIKE ?)")
            like = f"%{search}%"
            params.extend([like, like, like])
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        row = self.conn.execute(query, params).fetchone()
        return row["cnt"]

    def get_scan_overview(self, platform: str = "momox_shop") -> dict:
        """Get scan overview: total checked, available, last scan time per tier."""
        row = self.conn.execute(
            """SELECT COUNT(*) AS total_checked,
                      SUM(CASE WHEN status = 'available' THEN 1 ELSE 0 END) AS available,
                      SUM(CASE WHEN status = 'unavailable' THEN 1 ELSE 0 END) AS unavailable,
                      MAX(last_checked_at) AS last_scan_at
               FROM isbn_availability WHERE platform = ?""",
            (platform,),
        ).fetchone()
        total_watchlist = self.conn.execute("SELECT COUNT(*) AS cnt FROM reference_prices").fetchone()["cnt"]

        tiers = self.conn.execute(
            """SELECT priority, COUNT(*) AS cnt,
                      MIN(last_checked_at) AS oldest_check,
                      MAX(last_checked_at) AS newest_check
               FROM isbn_availability WHERE platform = ?
               GROUP BY priority""",
            (platform,),
        ).fetchall()
        tier_info = {}
        for t in tiers:
            tier_info[t["priority"]] = {
                "count": t["cnt"],
                "oldest_check": t["oldest_check"],
                "newest_check": t["newest_check"],
            }
        unchecked = self.conn.execute(
            """SELECT COUNT(*) AS cnt FROM reference_prices rp
               LEFT JOIN isbn_availability ia ON rp.isbn = ia.isbn AND ia.platform = ?
               WHERE ia.isbn IS NULL""",
            (platform,),
        ).fetchone()["cnt"]

        return {
            "total_watchlist": total_watchlist,
            "total_checked": row["total_checked"] or 0,
            "available": row["available"] or 0,
            "unavailable": row["unavailable"] or 0,
            "unchecked": unchecked,
            "last_scan_at": row["last_scan_at"],
            "tiers": tier_info,
        }

    # ── Notification Settings ──────────────────────────────────

    def get_notification_setting(self, key: str) -> str | None:
        """Get a single notification setting value."""
        row = self.conn.execute(
            "SELECT value FROM notification_settings WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else None

    def get_all_notification_settings(self) -> dict[str, str]:
        """Get all notification settings as a dict."""
        rows = self.conn.execute("SELECT key, value FROM notification_settings").fetchall()
        return {r["key"]: r["value"] for r in rows}

    def set_notification_setting(self, key: str, value: str) -> None:
        """Set a notification setting."""
        now = datetime.now().isoformat()
        self.conn.execute(
            """INSERT INTO notification_settings (key, value, updated_at)
               VALUES (?, ?, ?)
               ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at""",
            (key, value, now),
        )
        self.conn.commit()

    def delete_notification_setting(self, key: str) -> None:
        """Remove a notification setting."""
        self.conn.execute("DELETE FROM notification_settings WHERE key = ?", (key,))
        self.conn.commit()

    def get_available_deals(self) -> list[dict]:
        """Get all currently available books that are deals (price <= max_buy_price).

        Used for daily digest.
        """
        rows = self.conn.execute(
            """SELECT rp.isbn, rp.title, rp.author, rp.max_buy_price,
                      ia.last_price AS momox_price, ia.status,
                      (rp.max_buy_price - ia.last_price) AS savings
               FROM reference_prices rp
               JOIN isbn_availability ia ON rp.isbn = ia.isbn AND ia.platform = 'momox_shop'
               WHERE ia.status = 'available'
                 AND ia.last_price IS NOT NULL
                 AND ia.last_price <= rp.max_buy_price
               ORDER BY savings DESC"""
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Discord Webhooks ─────────────────────────────────────

    def add_discord_webhook(self, name: str, url: str) -> int:
        """Add a Discord webhook. Returns its ID."""
        now = datetime.now().isoformat()
        cursor = self.conn.execute(
            "INSERT INTO discord_webhooks (name, url, enabled, created_at) VALUES (?, ?, 1, ?)",
            (name, url, now),
        )
        self.conn.commit()
        return cursor.lastrowid  # type: ignore[return-value]

    def get_discord_webhooks(self, enabled_only: bool = False) -> list[dict]:
        """Get all Discord webhooks."""
        query = "SELECT * FROM discord_webhooks"
        if enabled_only:
            query += " WHERE enabled = 1"
        query += " ORDER BY created_at DESC"
        rows = self.conn.execute(query).fetchall()
        return [dict(r) for r in rows]

    def delete_discord_webhook(self, webhook_id: int) -> bool:
        """Delete a Discord webhook. Returns True if found."""
        cursor = self.conn.execute("DELETE FROM discord_webhooks WHERE id = ?", (webhook_id,))
        self.conn.commit()
        return cursor.rowcount > 0

    def toggle_discord_webhook(self, webhook_id: int, enabled: bool) -> bool:
        """Enable or disable a Discord webhook."""
        cursor = self.conn.execute(
            "UPDATE discord_webhooks SET enabled = ? WHERE id = ?", (int(enabled), webhook_id),
        )
        self.conn.commit()
        return cursor.rowcount > 0

    # ── Email Configs ────────────────────────────────────────

    def add_email_config(
        self, label: str, email_to: str, smtp_host: str, smtp_port: int,
        smtp_user: str, smtp_password: str, smtp_use_tls: bool = True,
    ) -> int:
        """Add an email notification config. Password is encrypted at rest."""
        now = datetime.now().isoformat()
        cursor = self.conn.execute(
            """INSERT INTO email_configs
               (label, email_to, smtp_host, smtp_port, smtp_user, smtp_password, smtp_use_tls, enabled, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)""",
            (label, email_to, smtp_host, smtp_port, smtp_user, encrypt(smtp_password), int(smtp_use_tls), now),
        )
        self.conn.commit()
        return cursor.lastrowid  # type: ignore[return-value]

    def get_email_configs(self, enabled_only: bool = False) -> list[dict]:
        """Get all email configs. Passwords are decrypted transparently."""
        query = "SELECT * FROM email_configs"
        if enabled_only:
            query += " WHERE enabled = 1"
        query += " ORDER BY created_at DESC"
        rows = self.conn.execute(query).fetchall()
        configs = [dict(r) for r in rows]
        for c in configs:
            c["smtp_password"] = decrypt(c["smtp_password"])
        return configs

    def delete_email_config(self, config_id: int) -> bool:
        """Delete an email config. Returns True if found."""
        cursor = self.conn.execute("DELETE FROM email_configs WHERE id = ?", (config_id,))
        self.conn.commit()
        return cursor.rowcount > 0

    def toggle_email_config(self, config_id: int, enabled: bool) -> bool:
        """Enable or disable an email config."""
        cursor = self.conn.execute(
            "UPDATE email_configs SET enabled = ? WHERE id = ?", (int(enabled), config_id),
        )
        self.conn.commit()
        return cursor.rowcount > 0

    # ── Cleanup ───────────────────────────────────────────────

    def close(self) -> None:
        self.conn.close()
