# CLAUDE.md — resell-bot

> Project-specific rules. Global rules in ~/.claude/CLAUDE.md apply unless overridden here.

## Summary

Bot Python de detection de bonnes affaires livres. Scan 5 plateformes (CaL, Momox, Recyclivre, Rakuten, FNAC), detecte les sous-cotes, notifie via Telegram.

## Stack

- Python 3.12+, httpx async, BeautifulSoup4 + lxml, APScheduler, SQLite3
- Package: `src/resell_bot/` (setuptools, editable install)
- Tests: `python -m pytest tests/ -v`
- Run: `python -m resell_bot --once` (single scan) or `python -m resell_bot` (continuous)

## Architecture

- `core/models.py` — Listing, PriceCheck, Alert dataclasses
- `core/database.py` — SQLite wrapper (no ORM)
- `core/notifier.py` — Telegram via raw Bot API (httpx)
- `core/price_engine.py` — Margin calculation + deal detection
- `scrapers/base.py` — ABC: `search(query)`, `get_price(isbn)`
- `scrapers/*.py` — One per platform, only chasseauxlivres.py implemented
- `utils/http_client.py` — Shared async client (retry, rate limit, UA rotation)
- `utils/isbn.py` — ISBN-10/13 validation + conversion

## Key Decisions

- CaL API: uses `/rest/search-results?h={hash}` (hash from search page)
- CaL returns HTML fragments in JSON — parsed with BeautifulSoup
- Prices on CaL are loaded separately (JS-driven) — CaL used for discovery only
- Buyback prices come from Momox/Recyclivre (Phase 2-3)
- No headless browser — all scraping via direct HTTP requests

## Config

- `config/settings.yaml` — timings, HTTP, database path, notifications
- `config/watchlists/livres.yaml` — search terms, ISBNs, filters
- `.env` — TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
