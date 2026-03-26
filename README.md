# Resell Bot

Bot de sniping de livres sous-cotes. Scanne Momox Shop via l'API Medimops (~80ms/req) pour trouver des livres en vente sous le prix max d'achat de la watchlist CaL (1380 ISBNs). Alerte instantanee via Telegram, Discord, Email + dashboard web. Cycle complet toutes les ~3 minutes.

## Setup

```bash
git clone git@github.com:goliviero/resell-bot.git
cd resell-bot

python -m venv .venv
source .venv/Scripts/activate  # Windows Git Bash
# source .venv/bin/activate    # Linux/Mac

pip install -e ".[dev]"

cp .env.example .env
# Edit .env with your Telegram bot token + chat_id
# See: python scripts/setup_telegram.py
```

## Usage

```bash
python -m resell_bot               # Continuous mode (~3 min cycle, 3 workers)
python -m resell_bot --once        # Single scan
python -m resell_bot --dashboard   # Dashboard only (http://127.0.0.1:8000)
python -m pytest tests/ -v         # 94 tests
```

## Notifications

- **Telegram** — configured via `.env` (TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)
- **Discord** — webhook URL via dashboard settings page
- **Email** — SMTP config via dashboard settings page
- **Daily digest** at 08:00 with all available deals

Setup Telegram: `python scripts/setup_telegram.py`

## Configuration

- `config/settings.yaml` — scan workers, delays, HTTP, database path, dedup cooldown
- `.env` — TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

## Architecture

```
src/resell_bot/
├── main.py                     # CLI entry, config loading, startup
├── scheduler.py                # Continuous parallel scan loop (Semaphore)
├── core/
│   ├── models.py               # Listing, Alert, ReferencePrice dataclasses
│   ├── database.py             # SQLite storage + dedup (no ORM)
│   ├── notifier.py             # Multi-channel hub: Telegram + Discord + Email
│   ├── price_engine.py         # Deal detection (price vs budget)
│   ├── buyer.py                # Auto-buy orchestration (Playwright, WIP)
│   ├── discord_notifier.py     # Discord webhook sender
│   └── email_notifier.py       # SMTP email sender
├── scrapers/
│   ├── base.py                 # ABC: get_offer(isbn) -> Listing | None
│   ├── momox_api.py            # PRIMARY — Medimops JSON API (~80ms/req)
│   ├── momox.py                # HTML fallback (archive)
│   └── {recyclivre,rakuten,fnac,ebay,amazon}.py  # Stubs
├── utils/
│   ├── http_client.py          # curl_cffi async: retry, backoff, UA rotation
│   └── isbn.py                 # ISBN-10/13 validation + conversion
└── web/
    ├── app.py                  # FastAPI + HTMX dashboard
    └── templates/              # Jinja2 (dark mode)
```

## Scrapers

| Platform | Status | Approach |
|----------|--------|----------|
| **Momox Shop** | Done | Medimops JSON API (api.medimops.de) |
| Recyclivre | Stub | HTML parsing (easy) |
| Rakuten | Stub | HTML + headers (medium) |
| eBay | Stub | Browse API (medium) |
| FNAC | Stub | curl_cffi + DataDome (hard) |
| Amazon | Stub | PA-API (very hard) |

## Stack

- Python 3.12+, curl_cffi (Cloudflare bypass), BeautifulSoup4 + lxml, APScheduler
- FastAPI + Jinja2 + HTMX (dashboard), SQLite3 (storage)
- 94 tests via pytest + pytest-asyncio
