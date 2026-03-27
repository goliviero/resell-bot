"""Buy action — opens product URL in user's default browser.

Cloudflare blocks ALL Playwright/automation approaches (even with real Chrome),
so we simply open the URL in the user's existing browser. The user is already
logged in and can add to cart + checkout manually (2-3 clicks).
"""

import logging
import webbrowser
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class BuyStep(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


STEP_LABELS = {
    BuyStep.PENDING: "En attente",
    BuyStep.COMPLETED: "Page ouverte dans le navigateur",
    BuyStep.FAILED: "Echec",
}


@dataclass
class BuyJob:
    """Tracks the state of a purchase attempt."""

    alert_id: int
    product_url: str
    title: str
    price: float
    platform: str = "momox_shop"
    step: BuyStep = BuyStep.PENDING
    error: str | None = None
    steps_done: list[str] = field(default_factory=list)

    @property
    def platform_label(self) -> str:
        return {"momox_shop": "Momox", "recyclivre": "RecycLivre"}.get(
            self.platform, self.platform
        )

    def to_dict(self) -> dict:
        return {
            "alert_id": self.alert_id,
            "product_url": self.product_url,
            "title": self.title,
            "price": self.price,
            "platform": self.platform,
            "platform_label": self.platform_label,
            "step": self.step.value,
            "step_label": STEP_LABELS[self.step],
            "error": self.error,
            "steps_done": self.steps_done,
        }


# In-memory job tracker (single-user app)
_active_jobs: dict[int, BuyJob] = {}


def get_job(alert_id: int) -> BuyJob | None:
    return _active_jobs.get(alert_id)


def get_all_jobs() -> list[BuyJob]:
    return list(_active_jobs.values())


def set_scheduler(scheduler) -> None:
    """Kept for API compatibility."""
    pass


async def start_buy(
    alert_id: int,
    product_url: str,
    title: str,
    price: float,
    platform: str = "momox_shop",
) -> BuyJob:
    """Open the product page in the user's default browser."""
    job = BuyJob(
        alert_id=alert_id,
        product_url=product_url,
        title=title,
        price=price,
        platform=platform,
    )
    _active_jobs[alert_id] = job

    try:
        # Momox redirects product URLs (strips query params AND hash).
        # Strategy: open homepage with #autobuy=/path — script sets sessionStorage
        # there (no redirect on homepage), then navigates to product page.
        from urllib.parse import urlparse
        parsed = urlparse(product_url)
        if "momox-shop" in parsed.hostname:
            buy_url = f"{parsed.scheme}://{parsed.hostname}/#autobuy={parsed.path}"
        elif "recyclivre" in parsed.hostname:
            buy_url = f"{product_url}#autobuy"
        else:
            buy_url = f"{product_url}#autobuy"
        webbrowser.open(buy_url)
        job.step = BuyStep.COMPLETED
        job.steps_done.append(f"Page {job.platform_label} ouverte avec autobuy")
        logger.info("[Buyer] Opened %s in default browser (autobuy)", buy_url)
    except Exception as e:
        logger.exception("Failed to open browser for alert %d", alert_id)
        job.step = BuyStep.FAILED
        job.error = str(e)

    return job
