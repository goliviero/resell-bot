# Architecture — resell-bot

## Tree

```
resell-bot/
├── CLAUDE.md                       # Project rules for Claude Code
├── ARCHITECTURE.md                 # This file
├── README.md                       # Setup + usage guide
├── pyproject.toml                  # Dependencies
├── .env.example                    # TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
├── .gitignore
├── config/
│   └── settings.yaml               # Scan interval, HTTP config, dedup cooldown
├── src/resell_bot/
│   ├── __init__.py
│   ├── __main__.py                 # python -m resell_bot entry
│   ├── main.py                     # CLI entry, config loading, startup
│   ├── scheduler.py                # APScheduler orchestration, scan loop
│   ├── priority.py                 # Priority tier management (HOT/WARM/COLD)
│   ├── core/
│   │   ├── models.py               # Listing, ReferencePrice, Alert
│   │   ├── database.py             # SQLite storage + dedup (no ORM)
│   │   ├── notifier.py             # Telegram Bot API via httpx
│   │   └── price_engine.py         # Deal detection (price vs budget)
│   ├── scrapers/
│   │   ├── base.py                 # ABC: get_offer(isbn) -> Listing | None
│   │   ├── momox.py                # Momox Shop — HTML fallback
│   │   ├── momox_api.py            # Momox Shop — PRIMARY (Medimops JSON API)
│   │   ├── recyclivre.py           # Recyclivre — stub (P1)
│   │   ├── rakuten.py              # Rakuten — stub (P1)
│   │   ├── fnac.py                 # FNAC — stub (P2)
│   │   ├── ebay.py                 # eBay — stub (P2)
│   │   └── amazon.py               # Amazon — stub (P3)
│   ├── utils/
│   │   ├── http_client.py          # curl_cffi async: retry, backoff, UA rotation, Cloudflare bypass
│   │   └── isbn.py                 # ISBN-10/13 validation, conversion, text extraction
│   └── web/
│       ├── app.py                  # FastAPI dashboard
│       └── templates/              # Jinja2 + HTMX (dark mode)
│           └── partials/
│               └── scan_status.html  # Live scan progress panel
├── tests/
│   ├── test_database.py            # 16 tests
│   ├── test_isbn.py                # 14 tests
│   ├── test_price_engine.py        # 5 tests
│   ├── test_priority.py            # Priority tier tests
│   ├── test_web.py                 # 9 tests
│   └── test_scrapers/
│       ├── test_momox.py           # 14 tests
│       └── test_momox_api.py       # Medimops API tests
├── scripts/
│   ├── import_cal_watchlist.py     # CaL CSV → reference_prices
│   ├── seed_mock_db.py            # Mock DB (15 classic books) for development
│   └── setup_telegram.py          # Interactive Telegram bot setup
└── docs/
    ├── decisions.md                # DEC-001..010
    ├── SWOT.md                     # Strategic analysis + scraping feasibility
    ├── TODO.md                     # Task backlog
    ├── bdd_franck_26032026.csv     # Reference CaL export (1380 ISBNs)
    └── activity_log.jsonl          # Session activity log
```

## Data Flow

```
1. CaL CSV export → import_cal_watchlist.py → reference_prices table (1380 ISBNs + max buy prices)
2. Scheduler runs every 30s, checks tier intervals (HOT 2min, WARM 20min, COLD 4h)
3. For overdue tier: parallel scan via Semaphore(3) using Medimops JSON API
4. Each scan: API call → update isbn_availability → check deal → alert
5. Priority auto-refresh after each cycle
6. Dashboard: alerts + books with availability + live scan progress
```

## Key Design Decisions

- **DEC-001**: curl_cffi for HTTP (TLS fingerprint impersonation bypasses Cloudflare)
- **DEC-002**: SQLite stdlib, no ORM (simple schema)
- **DEC-003**: CaL = CSV watchlist, not scraped
- **DEC-004**: Telegram via raw Bot API (no wrapper lib)
- **DEC-005**: Platform rollout by scraping feasibility (easy → hard)
- **DEC-006**: Buy model (find cheap books to resell), not buyback model
- **DEC-007**: Medimops JSON API over HTML scraping for Momox (~80ms vs ~2s)
- **DEC-008**: Priority tiers HOT/WARM/COLD for scan scheduling

## Stack

- Python 3.12+, curl_cffi, BeautifulSoup4 + lxml, APScheduler
- FastAPI + Jinja2 + HTMX (dashboard)
- SQLite3 (storage), pyyaml (config), python-dotenv (secrets)
- 92 tests via pytest + pytest-asyncio
