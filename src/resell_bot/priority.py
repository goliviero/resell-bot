"""Priority scoring for ISBN scan scheduling.

Assigns ISBNs to HOT / WARM / COLD tiers based on:
- Recent availability (seen in stock recently → HOT)
- Margin potential (high margin → promotes tier)
- Restock history (restocked multiple times → HOT)
"""

import logging
from datetime import datetime, timedelta

from resell_bot.core.database import Database

logger = logging.getLogger(__name__)

# Thresholds
HOT_MARGIN_THRESHOLD = 5.0      # min margin (€) to qualify for HOT
WARM_MARGIN_THRESHOLD = 2.0     # min margin (€) to qualify for WARM
HOT_RESTOCK_COUNT = 2           # times_available >= this → HOT
RECENTLY_AVAILABLE_HOURS = 48   # seen in stock within N hours → HOT


def compute_priority(
    status: str,
    last_price: float | None,
    max_buy_price: float | None,
    times_available: int,
    last_changed_at: str | None,
) -> str:
    """Determine the scan priority tier for an ISBN.

    Returns 'hot', 'warm', or 'cold'.
    """
    # Books that have restocked multiple times are always HOT
    if times_available >= HOT_RESTOCK_COUNT:
        return "hot"

    # Books recently seen available → HOT
    if status == "available" and last_changed_at:
        try:
            changed = datetime.fromisoformat(last_changed_at)
            if datetime.now() - changed < timedelta(hours=RECENTLY_AVAILABLE_HOURS):
                return "hot"
        except ValueError:
            pass

    # Books with high margin potential → HOT
    if max_buy_price and last_price and last_price > 0:
        margin = max_buy_price - last_price
        if margin >= HOT_MARGIN_THRESHOLD:
            return "hot"
        if margin >= WARM_MARGIN_THRESHOLD:
            return "warm"

    # Books seen available at least once → WARM
    if times_available >= 1:
        return "warm"

    # Everything else → COLD
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
