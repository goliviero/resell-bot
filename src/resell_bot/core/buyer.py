"""Automated Momox Shop purchase flow using Playwright.

Steps:
1. Add item to cart
2. Go to checkout
3. Fill shipping info (pre-configured)
4. Reach payment page (pause for manual 3D Secure)
"""

import asyncio
import logging
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class BuyStep(str, Enum):
    """Purchase flow steps."""

    PENDING = "pending"
    OPENING = "opening"
    ADDING_TO_CART = "adding_to_cart"
    CART_CONFIRMED = "cart_confirmed"
    CHECKOUT = "checkout"
    SHIPPING = "shipping"
    PAYMENT = "payment"
    WAITING_3DS = "waiting_3ds"
    COMPLETED = "completed"
    FAILED = "failed"


STEP_LABELS = {
    BuyStep.PENDING: "En attente",
    BuyStep.OPENING: "Ouverture de la page...",
    BuyStep.ADDING_TO_CART: "Ajout au panier...",
    BuyStep.CART_CONFIRMED: "Article dans le panier",
    BuyStep.CHECKOUT: "Passage en caisse...",
    BuyStep.SHIPPING: "Remplissage livraison...",
    BuyStep.PAYMENT: "Page de paiement atteinte",
    BuyStep.WAITING_3DS: "En attente de validation 3D Secure...",
    BuyStep.COMPLETED: "Achat termine !",
    BuyStep.FAILED: "Echec",
}


@dataclass
class BuyJob:
    """Tracks the state of a purchase attempt."""

    alert_id: int
    product_url: str
    title: str
    price: float
    step: BuyStep = BuyStep.PENDING
    error: str | None = None
    steps_done: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "alert_id": self.alert_id,
            "product_url": self.product_url,
            "title": self.title,
            "price": self.price,
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


async def start_buy(alert_id: int, product_url: str, title: str, price: float) -> BuyJob:
    """Start the automated purchase flow for a Momox product."""
    job = BuyJob(
        alert_id=alert_id,
        product_url=product_url,
        title=title,
        price=price,
    )
    _active_jobs[alert_id] = job

    # Run the purchase flow in background
    asyncio.create_task(_run_buy_flow(job))
    return job


async def _run_buy_flow(job: BuyJob) -> None:
    """Execute the Momox purchase flow with Playwright."""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        job.step = BuyStep.FAILED
        job.error = "Playwright not installed. Run: pip install playwright && playwright install chromium"
        return

    try:
        job.step = BuyStep.OPENING
        job.steps_done.append("Lancement du navigateur")

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False)
            context = await browser.new_context(
                locale="fr-FR",
                viewport={"width": 1280, "height": 900},
            )
            page = await context.new_page()

            # Step 1: Open product page
            logger.info("Opening %s", job.product_url)
            await page.goto(job.product_url, wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)
            job.steps_done.append(f"Page produit ouverte: {job.title}")

            # Step 2: Add to cart
            job.step = BuyStep.ADDING_TO_CART
            add_btn = page.locator('button:has-text("Ajouter au panier"), button:has-text("In den Warenkorb"), [data-testid="add-to-cart"]')
            if await add_btn.count() > 0:
                await add_btn.first.click()
                await page.wait_for_timeout(3000)
                job.step = BuyStep.CART_CONFIRMED
                job.steps_done.append("Article ajoute au panier")
            else:
                # Try alternate selectors for Momox Shop FR
                cart_btn = page.locator('.product-detail-buy button, .btn-buy, [class*="addToCart"]')
                if await cart_btn.count() > 0:
                    await cart_btn.first.click()
                    await page.wait_for_timeout(3000)
                    job.step = BuyStep.CART_CONFIRMED
                    job.steps_done.append("Article ajoute au panier")
                else:
                    job.step = BuyStep.CART_CONFIRMED
                    job.steps_done.append("Bouton panier non trouve — page ouverte pour achat manuel")

            # Step 3: Go to checkout
            job.step = BuyStep.CHECKOUT
            await page.goto("https://www.momox-shop.fr/checkout", wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)
            job.steps_done.append("Page checkout ouverte")

            # Step 4: Wait for manual payment / 3D Secure
            job.step = BuyStep.WAITING_3DS
            job.steps_done.append("En attente — complete l'achat dans le navigateur ouvert")

            # Keep browser open for manual completion (5 minutes timeout)
            for _ in range(300):
                if page.is_closed():
                    break
                current_url = page.url
                if "confirmation" in current_url or "success" in current_url or "thank" in current_url:
                    job.step = BuyStep.COMPLETED
                    job.steps_done.append("Achat confirme !")
                    break
                await asyncio.sleep(1)

            if job.step != BuyStep.COMPLETED:
                job.step = BuyStep.PAYMENT
                job.steps_done.append("Navigateur ferme (timeout 5 min)")

            await browser.close()

    except Exception as e:
        logger.exception("Buy flow failed for alert %d", job.alert_id)
        job.step = BuyStep.FAILED
        job.error = str(e)
