"""Generate a mock database with 15 fictional books for development/testing.

Creates reference_prices (watchlist) and isbn_availability entries with a mix
of available, unavailable, and unchecked states. Some books are deals
(platform price < max_buy_price), some are not.

Usage:
    python scripts/seed_mock_db.py
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add project root to path so we can import resell_bot
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from resell_bot.core.database import Database
from resell_bot.core.models import Alert, AlertStatus, Listing, ReferencePrice

DB_PATH = PROJECT_ROOT / "data" / "resell_bot.db"

# 15 fictional books with realistic French/English classics data
MOCK_BOOKS = [
    # isbn, title, author, max_buy_price
    ("9782070368228", "Le Petit Prince", "Antoine de Saint-Exupéry", 8.50),
    ("9782070360024", "L'Étranger", "Albert Camus", 6.00),
    ("9782070411726", "Les Misérables T1", "Victor Hugo", 12.00),
    ("9782070409228", "Germinal", "Émile Zola", 7.50),
    ("9782070360550", "Le Rouge et le Noir", "Stendhal", 9.00),
    ("9782070367627", "Madame Bovary", "Gustave Flaubert", 7.00),
    ("9782070413119", "Les Fleurs du Mal", "Charles Baudelaire", 6.50),
    ("9782253004226", "1984", "George Orwell", 8.00),
    ("9782070368079", "Candide", "Voltaire", 5.50),
    ("9782070409341", "Le Comte de Monte-Cristo T1", "Alexandre Dumas", 11.00),
    ("9782253002017", "Le Seigneur des Anneaux T1", "J.R.R. Tolkien", 15.00),
    ("9782070364022", "Les Trois Mousquetaires", "Alexandre Dumas", 10.00),
    ("9782253001492", "Fahrenheit 451", "Ray Bradbury", 7.00),
    ("9782070411160", "Notre-Dame de Paris", "Victor Hugo", 9.50),
    ("9782070367177", "Bel-Ami", "Guy de Maupassant", 6.00),
]

# Momox availability simulation:
# - Some available with price BELOW max_buy_price (deals!)
# - Some available with price ABOVE max_buy_price (no deal)
# - Some unavailable
# - Some never checked (not in this dict at all)
# Format: isbn -> (status, last_price, priority)
AVAILABILITY = {
    # DEALS: platform price <= max_buy_price
    "9782070368228": ("available", 4.99, "hot"),     # Le Petit Prince: 4.99 < 8.50 -> deal
    "9782070360024": ("available", 3.49, "hot"),     # L'Étranger: 3.49 < 6.00 -> deal
    "9782253004226": ("available", 5.99, "hot"),     # 1984: 5.99 < 8.00 -> deal
    "9782070368079": ("available", 2.99, "warm"),    # Candide: 2.99 < 5.50 -> deal
    "9782070367177": ("available", 4.49, "warm"),    # Bel-Ami: 4.49 < 6.00 -> deal

    # NO DEAL: platform price > max_buy_price
    "9782070411726": ("available", 14.99, "warm"),   # Les Misérables: 14.99 > 12.00
    "9782070409228": ("available", 8.99, "cold"),    # Germinal: 8.99 > 7.50
    "9782070367627": ("available", 9.49, "cold"),    # Madame Bovary: 9.49 > 7.00

    # UNAVAILABLE
    "9782070360550": ("unavailable", None, "cold"),  # Le Rouge et le Noir
    "9782070413119": ("unavailable", None, "cold"),  # Les Fleurs du Mal
    "9782070409341": ("unavailable", None, "cold"),  # Monte-Cristo
    "9782253002017": ("unavailable", None, "warm"),  # Seigneur des Anneaux

    # NOT CHECKED (these 3 ISBNs are deliberately absent):
    # 9782070364022 - Les Trois Mousquetaires
    # 9782253001492 - Fahrenheit 451
    # 9782070411160 - Notre-Dame de Paris
}


def isbn13_to_isbn10(isbn13: str) -> str:
    """Convert ISBN-13 to ISBN-10 for Momox URL generation."""
    core = isbn13[3:12]
    total = sum(int(d) * (10 - i) for i, d in enumerate(core))
    check = (11 - total % 11) % 11
    return core + ("X" if check == 10 else str(check))


def main() -> None:
    print(f"Creating mock database at {DB_PATH}")
    print("-" * 60)

    db = Database(DB_PATH)
    now = datetime.now()

    # -- Insert reference prices (watchlist) --
    refs = []
    for isbn, title, author, max_buy_price in MOCK_BOOKS:
        ref = ReferencePrice(
            isbn=isbn,
            title=title,
            author=author,
            max_buy_price=max_buy_price,
            source="mock_seed",
            updated_at=now,
        )
        refs.append(ref)
    count = db.bulk_upsert_reference_prices(refs)
    print(f"Watchlist:     {count} reference prices inserted")

    # -- Insert isbn_availability entries --
    avail_count = 0
    for isbn, (status, price, priority) in AVAILABILITY.items():
        in_stock = status == "available"
        db.upsert_availability(isbn, "momox_shop", in_stock, price)
        db.update_priority(isbn, "momox_shop", priority)
        avail_count += 1
    print(f"Availability:  {avail_count} isbn_availability entries")

    # -- Insert listings + alerts for the deals --
    deals = 0
    no_deals = 0
    for isbn, title, author, max_buy_price in MOCK_BOOKS:
        if isbn not in AVAILABILITY:
            continue
        status, price, priority = AVAILABILITY[isbn]
        if status != "available" or price is None:
            continue

        isbn10 = isbn13_to_isbn10(isbn)
        momox_url = f"https://www.momox-shop.fr/M0{isbn10}.html"

        listing = Listing(
            title=title,
            price=price,
            url=momox_url,
            platform="momox_shop",
            isbn=isbn,
            condition="très bon",
            seller="Momox Shop",
            author=author,
            found_at=now - timedelta(hours=1),
            image_url=None,
        )
        db.save_listing(listing)

        is_deal = price <= max_buy_price
        if is_deal:
            savings = max_buy_price - price
            alert = Alert(
                listing=listing,
                max_buy_price=max_buy_price,
                savings=savings,
                status=AlertStatus.NEW,
            )
            db.save_alert(alert)
            deals += 1
        else:
            no_deals += 1

    print(f"Listings:      {deals + no_deals} Momox listings created")
    print(f"Alerts:        {deals} deals detected (price <= max_buy_price)")
    print(f"               {no_deals} above max price (no alert)")

    # -- Summary --
    unchecked = len(MOCK_BOOKS) - len(AVAILABILITY)
    unavailable = sum(1 for s, _, _ in AVAILABILITY.values() if s == "unavailable")
    available = sum(1 for s, _, _ in AVAILABILITY.values() if s == "available")

    print()
    print("=" * 60)
    print(f"SUMMARY")
    print(f"  Total books in watchlist:  {len(MOCK_BOOKS)}")
    print(f"  Available on Momox:        {available}")
    print(f"  Unavailable on Momox:      {unavailable}")
    print(f"  Never checked:             {unchecked}")
    print(f"  Deals (alerts created):    {deals}")
    print(f"  DB path:                   {DB_PATH}")
    print("=" * 60)

    db.close()


if __name__ == "__main__":
    main()
