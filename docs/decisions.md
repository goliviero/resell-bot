# Decision Log — resell-bot

> Format: ## DEC-XXX — Title [STATUS]

---

## DEC-001 — curl_cffi over httpx for HTTP client [ACTIVE]

**Date:** 2026-03-26
**Decision:** Use curl_cffi (not httpx) as the primary HTTP client.
**Rationale:** Momox (and likely other platforms) use Cloudflare bot protection. httpx gets 403'd. curl_cffi impersonates real browser TLS fingerprints, bypassing Cloudflare without a headless browser. httpx is still used for Telegram API calls (no Cloudflare there).

---

## DEC-002 — SQLite over ORM [ACTIVE]

**Date:** 2026-03-26
**Decision:** Use sqlite3 stdlib directly, no SQLAlchemy/ORM.
**Rationale:** Simple schema (listings + alerts + reference_prices). ORM adds complexity for zero benefit here. Raw SQL is readable and the schema fits in 20 lines.

---

## DEC-003 — CaL as reference DB, not scraped [ACTIVE]

**Date:** 2026-03-26
**Decision:** CaL (Chasse aux Livres) is NOT scraped. It's used as a tool to maintain an Excel/CSV watchlist of ISBNs + max buy prices. The CSV is exported from CaL and imported into the bot's SQLite DB via `scripts/import_cal_watchlist.py`.
**Rationale:** CaL doesn't show prices directly (JS-loaded). Its value is as a watchlist management tool the user and his brother already use.

---

## DEC-004 — Telegram raw API over wrapper libs [ACTIVE]

**Date:** 2026-03-26
**Decision:** Send Telegram notifications via httpx POST to Bot API directly. No python-telegram-bot or other wrapper.
**Rationale:** We only need `sendMessage`. Adding a 5000-line wrapper lib for one API call is waste.

---

## DEC-005 — Platform-first scraper rollout [ACTIVE]

**Date:** 2026-03-26
**Decision:** Focus on BUY platforms in order of scraping feasibility: Momox Shop (done) → Recyclivre → Rakuten → FNAC → eBay → Amazon. NOT in order of market size.
**Rationale:** No point targeting Amazon first if it's impossible to scrape. Start with easy wins, validate the model, then tackle harder platforms.

---

## DEC-006 — Buy model, not buyback [ACTIVE]

**Date:** 2026-03-26
**Decision:** The bot finds books to BUY (cheap, on platforms) for RESALE (on Vinted/Leboncoin). It does NOT track buyback prices (what Momox would pay for YOUR books). Alert triggers when `platform_sale_price ≤ max_buy_price_from_watchlist`.
**Rationale:** The user and his brother buy rare/underpriced books on platforms and resell them manually at much higher prices. The profit margin is implicit — they know the resale value from experience.

---

## DEC-007 — Medimops JSON API over HTML scraping for Momox [ACTIVE]

**Date:** 2026-03-26
**Decision:** Use `api.medimops.de/v1/search?q={isbn}&marketplace_id=fra` as primary Momox scraper instead of HTML scraping momox-shop.fr product pages.
**Rationale:** The Medimops API returns shop sale prices, stock, condition as JSON (~80ms per request vs ~2s for HTML). No Cloudflare challenge. 1380 ISBNs scanned in 1m50s vs ~80min with HTML scraping. HTML scraper (momox.py) kept as fallback. The old `api.momox.fr` buyback API is irrelevant (it returns buyback prices, not sale prices).

---

## DEC-008 — Priority tiers HOT/WARM/COLD for scan scheduling [ACTIVE]

**Date:** 2026-03-26
**Decision:** ISBNs are classified into priority tiers: HOT (scan every 2 min), WARM (every 20 min), COLD (every 4 hours). Priorities auto-computed based on availability history, margin potential, and restock frequency.
**Rationale:** Scanning all 1380 ISBNs at the same frequency wastes time on books that are never available. First scan: 25 books available (HOT), 1355 never seen (COLD). HOT tier scans in ~3s, giving near-real-time alerting for the books that matter.

---

## DEC-009 — Mock DB for development, real DB excluded from git [ACTIVE]

**Date:** 2026-03-26
**Decision:** The real watchlist DB (bdd_franck_*.csv and data/*.db) is excluded from git. A mock DB of 15 classic books is provided via scripts/seed_mock_db.py for development. The real DB is synced via Proton Drive.
**Rationale:** The brother's 1380-ISBN watchlist contains competitive intelligence (which books are profitable). Leaking it on GitHub would help competitors. Mock DB allows anyone to test the bot without the real data.

---

## DEC-010 — HTMX polling for scan status over WebSocket [ACTIVE]

**Date:** 2026-03-26
**Decision:** Dashboard scan status uses HTMX polling (every 5s) instead of WebSocket push.
**Rationale:** HTMX is already in the stack, zero additional dependency. 5s polling is acceptable for monitoring (not for trading). WebSocket could be added later if sub-second dashboard updates are needed.
