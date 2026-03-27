# CLAUDE.md — resell-bot

> Project-specific rules. Global rules in ~/.claude/CLAUDE.md apply unless overridden here.

## Summary

Bot Python de sniping de livres sous-cotés. Scanne les plateformes d'achat (Momox Shop, Recyclivre, Rakuten, FNAC, eBay, Amazon) pour trouver des livres en vente sous le prix max d'achat défini dans la watchlist CaL. Alerte via Telegram/Discord/Email + dashboard web. Scan continu parallèle : tous les 1380 ISBNs vérifiés toutes les ~3 min via l'API Medimops.

## Stack

- Python 3.12+, curl_cffi (Cloudflare bypass), BeautifulSoup4 + lxml, APScheduler, SQLite3
- Package: `src/resell_bot/` (setuptools, editable install)
- Tests: `python -m pytest tests/ -v`
- Run: `python -m resell_bot --once` (single scan) or `python -m resell_bot` (continuous)

## Architecture

- `core/models.py` — Listing, ReferencePrice, Alert dataclasses
- `core/database.py` — SQLite wrapper (no ORM)
- `core/notifier.py` — Multi-channel hub: Telegram + Discord + Email
- `core/price_engine.py` — Deal detection: listing price vs max buy price
- `core/buyer.py` — Auto-buy via webbrowser.open() + Tampermonkey userscript. BuyStep: PENDING/COMPLETED/FAILED. Momox uses #autobuy homepage relay to avoid redirect stripping.
- `scrapers/base.py` — ABC: `get_offer(isbn) -> Listing | None`
- `scrapers/momox_api.py` — Momox Shop via Medimops JSON API — PRIMARY
- `scrapers/momox.py` — Momox Shop HTML fallback — ARCHIVE
- `scrapers/recyclivre.py` — RecycLivre scraper (HTML, BeautifulSoup)
- `scrapers/{rakuten,fnac,ebay,amazon}.py` — Stubs
- `scheduler.py` — Per-platform independent scan loops. RecycLivre: 1 worker, 2-4s delay. Alert expiry: 2h.
- `tampermonkey_autobuy.user.js` — Userscript v1.10. Auto add-to-cart + checkout for RecycLivre and Momox Shop. @grant GM_info for sandbox isolation, @run-at document-start to capture params before React.
- `utils/http_client.py` — Shared async client (curl_cffi, retry, rate limit, UA rotation)
- `utils/isbn.py` — ISBN-10/13 validation + conversion
- `web/app.py` — FastAPI + HTMX dashboard

## Key Decisions

- CaL = watchlist tool, NOT scraped. CSV exported → imported via `scripts/import_cal_watchlist.py`
- Buy model: find books cheap on platforms → resell on Vinted/Leboncoin
- Alert when `platform_price ≤ max_buy_price` from watchlist
- curl_cffi for TLS fingerprint impersonation (bypasses Cloudflare)
- Momox Shop: product pages at `momox-shop.fr/{mpid}.html` (mpid from API)

## Config

- `config/settings.yaml` — timings, HTTP, database path, notifications
- `.env` — TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

## Quick Commands

```bash
python -m resell_bot --once        # Single scan
python -m resell_bot               # Continuous mode
python -m resell_bot --dashboard   # Dashboard only
python -m pytest tests/ -v         # 146 tests
python scripts/import_cal_watchlist.py docs/bdd_franck_26032026.csv  # Import CaL CSV
python scripts/setup_telegram.py   # Configure Telegram bot
```

## Activity Logging

- `docs/activity_log.jsonl` — append-only session log
- `docs/decisions.md` — DEC-XXX [ACTIVE], date, decision, rationale
- `scripts/activity_log.py` — symlink to dotfiles (DEC-002 dotfiles)

## Rules

- Never commit `.env`, `data/*.db`, `.venv/`
- One scraper per file, all inherit from `scrapers/base.py`
- All HTTP goes through `utils/http_client.py` (never raw curl_cffi)
- Prices in euros (float), ISBNs normalized to ISBN-13 via `utils/isbn.py`
