# Resell Bot

Bot de detection de bonnes affaires sur les sites de vente/rachat de livres.

Scan des plateformes complementaires a vTools : Chasse aux Livres, Momox, Recyclivre, Rakuten, FNAC Marketplace. Detecte les livres sous-cotes (prix d'achat < prix de revente - marge minimum) et envoie une notification Telegram instantanee.

## Setup

```bash
# Clone
git clone git@github.com:goliviero/resell-bot.git
cd resell-bot

# Virtualenv
python -m venv .venv
source .venv/Scripts/activate  # Windows Git Bash
# source .venv/bin/activate    # Linux/Mac

# Install
pip install -e ".[dev]"

# Configure
cp .env.example .env
# Edit .env with your Telegram bot token + chat_id
# See: python scripts/setup_telegram.py
```

## Usage

```bash
# Single scan (test mode)
python -m resell_bot --once

# Continuous mode (scans every N minutes, configured in settings.yaml)
python -m resell_bot

# Also works with:
python src/resell_bot/main.py --once
```

## Telegram Setup

1. Create a bot via [@BotFather](https://t.me/BotFather) on Telegram
2. Send a message to your new bot
3. Run `python scripts/setup_telegram.py` and paste your token
4. Copy the output to your `.env` file

## Configuration

- `config/settings.yaml` — scan frequency, HTTP settings, delays, dedup cooldown
- `config/watchlists/livres.yaml` — keywords, ISBNs, price filters, platform selection

## Tests

```bash
python -m pytest tests/ -v
```

## Architecture

```
resell-bot/
├── config/
│   ├── settings.yaml           # Global config
│   └── watchlists/livres.yaml  # Search terms + filters
├── src/resell_bot/
│   ├── main.py                 # Entry point
│   ├── scheduler.py            # APScheduler orchestration
│   ├── core/
│   │   ├── models.py           # Listing, PriceCheck, Alert
│   │   ├── database.py         # SQLite storage + dedup
│   │   ├── notifier.py         # Telegram Bot API
│   │   └── price_engine.py     # Margin calculation
│   ├── scrapers/
│   │   ├── base.py             # ABC interface
│   │   ├── chasseauxlivres.py  # Phase 1 (implemented)
│   │   ├── momox.py            # Phase 2 (stub)
│   │   ├── recyclivre.py       # Phase 3 (stub)
│   │   ├── rakuten.py          # Phase 4 (stub)
│   │   └── fnac.py             # Phase 5 (stub)
│   └── utils/
│       ├── http_client.py      # Async httpx + retry + rate limit
│       └── isbn.py             # ISBN-10/13 validation
├── tests/
├── scripts/setup_telegram.py
└── pyproject.toml
```

## Phases

| Phase | Scraper | Status |
|-------|---------|--------|
| 1 | Chasse aux Livres (discovery) | Done |
| 2 | Momox (buyback pricing) | Stub |
| 3 | Recyclivre (buyback pricing) | Stub |
| 4 | Rakuten (marketplace) | Stub |
| 5 | FNAC Marketplace | Stub |
| 6 | Arbitrage mode + price history + daily digest | Planned |

## Stack

- Python 3.12+, httpx (async), BeautifulSoup4 + lxml, APScheduler, SQLite3
- Zero wrapper libs: Telegram via raw Bot API, no ORM
- stdlib only for core logic (dataclasses, sqlite3, pathlib)
