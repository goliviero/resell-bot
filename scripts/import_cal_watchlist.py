"""Import CaL watchlist CSV/TSV into the reference_prices table.

Usage:
    python scripts/import_cal_watchlist.py docs/bdd_franck_26032026.csv

Expected columns (tab-separated):
    Id, EAN, Catalogue, Titre, Auteur, Editeur, Format, Pages, Année,
    Etat souhaité, Prix souhaité, Prix éditeur, Date de création,
    Commentaire, Url, Liste, Id Liste

Key mapping:
    EAN          → isbn (reference_prices.isbn)
    Prix souhaité → max_buy_price (max price you're willing to pay)
    source       = "cal_import"
"""

import argparse
import csv
import logging
import sys
from datetime import datetime
from pathlib import Path

# Allow running from repo root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from resell_bot.core.database import Database
from resell_bot.core.models import ReferencePrice

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = Path("data/resell_bot.db")


def parse_price(raw: str) -> float | None:
    """Parse a price string like '15,00' or '15.00' to float."""
    if not raw or not raw.strip():
        return None
    cleaned = raw.strip().replace(",", ".").replace("\xa0", "")
    try:
        return float(cleaned)
    except ValueError:
        return None


def import_csv(csv_path: Path, db: Database) -> dict:
    """Import a CaL watchlist CSV/TSV into reference_prices.

    Returns stats dict with counts.
    """
    stats = {"total": 0, "imported": 0, "skipped_no_ean": 0, "skipped_no_price": 0}

    with csv_path.open(encoding="utf-8-sig") as f:
        # Detect delimiter: try tab first (CaL export default), fallback to comma
        sample = f.readline()
        f.seek(0)
        delimiter = "\t" if "\t" in sample else (";" if ";" in sample else ",")
        reader = csv.DictReader(f, delimiter=delimiter)

        refs: list[ReferencePrice] = []

        for row in reader:
            stats["total"] += 1

            ean = (row.get("EAN") or "").strip()
            if not ean:
                stats["skipped_no_ean"] += 1
                continue

            prix_souhaite = parse_price(row.get("Prix souhaité", ""))
            if prix_souhaite is None:
                stats["skipped_no_price"] += 1
                continue

            titre = (row.get("Titre") or "").strip()
            auteur = (row.get("Auteur") or "").strip()
            url = (row.get("Url") or "").strip()

            refs.append(ReferencePrice(
                isbn=ean,
                max_buy_price=prix_souhaite,
                source="cal_import",
                updated_at=datetime.now(),
                title=titre or None,
                author=auteur or None,
                url=url or None,
            ))

        if refs:
            count = db.bulk_upsert_reference_prices(refs)
            stats["imported"] = count

    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Import CaL watchlist into resell-bot DB")
    parser.add_argument("csv_file", type=Path, help="Path to CaL CSV/TSV export")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="Database path")
    args = parser.parse_args()

    if not args.csv_file.exists():
        logger.error("File not found: %s", args.csv_file)
        sys.exit(1)

    db = Database(args.db)
    try:
        stats = import_csv(args.csv_file, db)
        logger.info(
            "Import done: %d total, %d imported, %d skipped (no EAN), %d skipped (no price)",
            stats["total"],
            stats["imported"],
            stats["skipped_no_ean"],
            stats["skipped_no_price"],
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
