"""Priority scoring for ISBN scan scheduling.

Strategy: books with high VALUE (max_buy_price) are scanned most frequently,
regardless of whether they've been seen in stock before. A rare book worth 100€
that has never appeared is MORE important to scan often than a 5€ book seen
10 times. The goal is to never miss a high-value restock.

Tiers:
- HOT (2 min): high-value books (high max_buy_price), recently restocked, multi-restock
- WARM (20 min): moderate value, seen once before
- COLD (4 hours): low value AND never seen — unlikely to generate profit
"""

import logging
from datetime import datetime, timedelta

from resell_bot.core.database import Database

logger = logging.getLogger(__name__)

# Value-based thresholds (max_buy_price = what the book is worth to us)
HIGH_VALUE_THRESHOLD = 50.0     # max_buy_price >= 50€ → always HOT (rare/expensive books)
MEDIUM_VALUE_THRESHOLD = 20.0   # max_buy_price >= 20€ → at least WARM

# Margin-based thresholds (when we know the sale price)
HOT_MARGIN_THRESHOLD = 5.0     # margin >= 5€ → HOT
WARM_MARGIN_THRESHOLD = 2.0    # margin >= 2€ → WARM

# History-based thresholds
HOT_RESTOCK_COUNT = 2           # restocked >= 2 times → HOT (pattern of availability)
RECENTLY_AVAILABLE_HOURS = 48   # seen in stock within 48h → HOT


def compute_priority(
    status: str,
    last_price: float | None,
    max_buy_price: float | None,
    times_available: int,
    last_changed_at: str | None,
) -> str:
    """Determine the scan priority tier for an ISBN.

    Returns 'hot', 'warm', or 'cold'.

    Priority logic (first match wins):
    1. High-value book (max_buy_price >= 15€) → HOT always
    2. Restocked multiple times → HOT (proven pattern)
    3. Recently available → HOT (may come back)
    4. High margin when last seen → HOT
    5. Medium-value book (>= 8€) → WARM
    6. Moderate margin → WARM
    7. Seen available at least once → WARM
    8. Everything else → COLD
    """
    # High-value books are ALWAYS scanned frequently — these are the rare ones
    # that matter most and must never be missed
    if max_buy_price and max_buy_price >= HIGH_VALUE_THRESHOLD:
        return "hot"

    # Books that have restocked multiple times → proven availability pattern
    if times_available >= HOT_RESTOCK_COUNT:
        return "hot"

    # Books recently seen available → likely to come back
    if status == "available" and last_changed_at:
        try:
            changed = datetime.fromisoformat(last_changed_at)
            if datetime.now() - changed < timedelta(hours=RECENTLY_AVAILABLE_HOURS):
                return "hot"
        except ValueError:
            pass

    # Books with high margin potential (when we know the sale price)
    if max_buy_price and last_price and last_price > 0:
        margin = max_buy_price - last_price
        if margin >= HOT_MARGIN_THRESHOLD:
            return "hot"
        if margin >= WARM_MARGIN_THRESHOLD:
            return "warm"

    # Medium-value books → worth scanning regularly
    if max_buy_price and max_buy_price >= MEDIUM_VALUE_THRESHOLD:
        return "warm"

    # Books seen available at least once → something happens there
    if times_available >= 1:
        return "warm"

    # Low-value, never-seen books → scan infrequently
    return "cold"


def refresh_priorities(db: Database, platform: str) -> dict[str, int]:
    """Recompute priorities for all tracked ISBNs on a platform.

    Returns counts per tier: {'hot': N, 'warm': N, 'cold': N}.
    """
    rows = db.conn.execute(
        """SELECT ia.isbn, ia.status, ia.last_price, ia.times_available,
                  ia.last_changed_at, ia.priority,
                  rp.max_buy_price
           FROM isbn_availability ia
           JOIN reference_prices rp ON ia.isbn = rp.isbn
           WHERE ia.platform = ?""",
        (platform,),
    ).fetchall()

    counts: dict[str, int] = {"hot": 0, "warm": 0, "cold": 0}
    updates: list[tuple[str, str, str]] = []

    for row in rows:
        new_priority = compute_priority(
            status=row["status"],
            last_price=row["last_price"],
            max_buy_price=row["max_buy_price"],
            times_available=row["times_available"],
            last_changed_at=row["last_changed_at"],
        )
        counts[new_priority] = counts.get(new_priority, 0) + 1

        if new_priority != row["priority"]:
            updates.append((row["isbn"], platform, new_priority))

    if updates:
        db.bulk_update_priorities(updates)
        logger.info(
            "Priority refresh (%s): %d changes — hot=%d warm=%d cold=%d",
            platform, len(updates), counts["hot"], counts["warm"], counts["cold"],
        )

    return counts
