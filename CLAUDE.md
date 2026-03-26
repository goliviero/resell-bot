# CLAUDE.md — resell-bot

> Project-specific rules. Global rules in ~/.claude/CLAUDE.md apply unless overridden here.

## Summary

Bot Python de sniping de livres sous-cotés. Scanne les plateformes d'achat (Momox Shop, Recyclivre, Rakuten, FNAC, eBay, Amazon) pour trouver des livres en vente sous le prix max d'achat défini dans la watchlist CaL. Alerte via Telegram + dashboard web.

## Stack

- Python 3.12+, curl_cffi (Cloudflare bypass), BeautifulSoup4 + lxml, APScheduler, SQLite3
- Package: `src/resell_bot/` (setuptools, editable install)
- Tests: `python -m pytest tests/ -v`
- Run: `python -m resell_bot --once` (single scan) or `python -m resell_bot` (continuous)

## Architecture

- `core/models.py` — Listing, ReferencePrice, Alert dataclasses
- `core/database.py` — SQLite wrapper (no ORM)
- `core/notifier.py` — Telegram via raw Bot API (httpx)
- `core/price_engine.py` — Deal detection: listing price vs max buy price
- `scrapers/base.py` — ABC: `get_offer(isbn) -> Listing | None`
- `scrapers/momox.py` — Momox Shop (momox-shop.fr) — IMPLEMENTED
- `scrapers/{rakuten,recyclivre,fnac,ebay,amazon}.py` — Stubs
- `utils/http_client.py` — Shared async client (curl_cffi, retry, rate limit, UA rotation)
- `utils/isbn.py` — ISBN-10/13 validation + conversion
- `web/app.py` — FastAPI + HTMX dashboard

## Key Decisions

- CaL = watchlist tool, NOT scraped. CSV exported → imported via `scripts/import_cal_watchlist.py`
- Buy model: find books cheap on platforms → resell on Vinted/Leboncoin
- Alert when `platform_price ≤ max_buy_price` from watchlist
- curl_cffi for TLS fingerprint impersonation (bypasses Cloudflare)
- Momox Shop: product pages at `momox-shop.fr/M0{isbn10}.html`

## Config

- `config/settings.yaml` — timings, HTTP, database path, notifications
- `.env` — TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

## Quick Commands

```bash
python -m resell_bot --once        # Single scan
python -m resell_bot               # Continuous mode
python -m resell_bot --dashboard   # Dashboard only
python -m pytest tests/ -v         # 68 tests
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
