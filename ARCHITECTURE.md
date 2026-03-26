# Architecture — resell-bot

## Tree

```
resell-bot/
├── CLAUDE.md                       # Project rules for Claude Code
├── ARCHITECTURE.md                 # This file
├── README.md                       # Setup + usage guide
├── pyproject.toml                  # Dependencies (httpx, bs4, lxml, apscheduler, pyyaml)
├── .env.example                    # TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
├── .gitignore
├── config/
│   ├── settings.yaml               # Scan interval, HTTP config, dedup cooldown
│   └── watchlists/
│       └── livres.yaml             # Keywords, ISBNs, price filters
├── src/resell_bot/
│   ├── __init__.py
│   ├── __main__.py                 # python -m resell_bot entry
│   ├── main.py                     # CLI entry, config loading, startup
│   ├── scheduler.py                # APScheduler orchestration, scan loop
│   ├── core/
│   │   ├── models.py               # Listing, PriceCheck, Alert dataclasses
│   │   ├── database.py             # SQLite storage + dedup (no ORM)
│   │   ├── notifier.py             # Telegram Bot API via httpx
│   │   └── price_engine.py         # Margin calculation, deal detection
│   ├── scrapers/
│   │   ├── base.py                 # ABC: search(query), get_price(isbn)
│   │   ├── chasseauxlivres.py      # Phase 1 — book discovery via REST API
│   │   ├── momox.py                # Phase 2 — buyback pricing (stub)
│   │   ├── recyclivre.py           # Phase 3 — buyback pricing (stub)
│   │   ├── rakuten.py              # Phase 4 — marketplace (stub)
│   │   └── fnac.py                 # Phase 5 — marketplace (stub)
│   └── utils/
│       ├── http_client.py          # Async httpx client: retry, backoff, UA rotation, rate limit
│       └── isbn.py                 # ISBN-10/13 validation, conversion, text extraction
├── tests/
│   ├── test_database.py            # 5 tests — save, dedup, query
│   ├── test_isbn.py                # 14 tests — validation, conversion, extraction
│   ├── test_price_engine.py        # 8 tests — margin, thresholds, platform selection
│   └── test_scrapers/
│       └── test_chasseauxlivres.py # 8 tests — HTML parsing, edge cases
├── scripts/
│   ├── setup_telegram.py           # Interactive Telegram bot setup helper
│   └── activity_log.py             # Symlink → dotfiles/scripts/activity_log.py
└── docs/
    ├── decisions.md                # DEC-001..005
    ├── SWOT.md                     # Strengths, weaknesses, opportunities, threats
    ├── TODO.md                     # Phase backlog
    └── activity_log.jsonl          # Session activity log
```

## Data Flow

```
1. main.py loads config (settings.yaml + watchlists/livres.yaml + .env)
2. scheduler.py creates APScheduler job → run_scan() every N minutes
3. run_scan() iterates keywords/ISBNs from watchlist:
   a. Discovery scrapers (CaL) → search(query) → list[Listing]
   b. For each Listing with ISBN:
      - Check dedup (database.was_recently_alerted)
      - Save listing to SQLite
      - Query buyback scrapers (Momox, Recyclivre) → get_price(isbn)
      - price_engine.evaluate(listing, buyback_prices) → Alert | None
   c. For each Alert:
      - notifier.send_alert() → Telegram message
      - database.save_alert() → dedup tracking
```

## Key Design Decisions

- **DEC-001**: httpx async for all HTTP (HTTP/2 support, single client)
- **DEC-002**: SQLite stdlib, no ORM (simple schema)
- **DEC-003**: CaL = discovery only (prices are JS-loaded, not scraped)
- **DEC-004**: Telegram via raw Bot API (no wrapper lib)
- **DEC-005**: Phase-based scraper rollout (one site at a time)

## Stack

- Python 3.12+, stdlib only for core logic
- httpx (async HTTP/2), BeautifulSoup4 + lxml (parsing), APScheduler
- SQLite3 (storage), pyyaml (config), python-dotenv (secrets)
- 44 tests via pytest + pytest-asyncio
