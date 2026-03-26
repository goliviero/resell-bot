# Decision Log — resell-bot

> Format: ## DEC-XXX — Title [STATUS]

---

## DEC-001 — Async httpx over requests/aiohttp [ACTIVE]

**Date:** 2026-03-26
**Decision:** Use httpx with async for all HTTP requests.
**Rationale:** httpx supports HTTP/2, async natively, and has a cleaner API than aiohttp. No need for requests since everything is async. Single client instance with retry/backoff/rate-limit in `utils/http_client.py`.

---

## DEC-002 — SQLite over ORM [ACTIVE]

**Date:** 2026-03-26
**Decision:** Use sqlite3 stdlib directly, no SQLAlchemy/ORM.
**Rationale:** Simple schema (listings + alerts + dedup). ORM adds complexity for zero benefit here. Raw SQL is readable and the schema fits in 20 lines.

---

## DEC-003 — CaL as discovery, not pricing [ACTIVE]

**Date:** 2026-03-26
**Decision:** Chasse aux Livres is used for book discovery only (search by keyword/ISBN → get book metadata). Pricing comes from buyback scrapers (Momox, Recyclivre).
**Rationale:** CaL loads individual prices via JS-driven AJAX (`/rest/listing-offers`), protected by session. Scraping prices would require browser automation. CaL's value is as an aggregator of book editions/ISBNs.

---

## DEC-004 — Telegram raw API over wrapper libs [ACTIVE]

**Date:** 2026-03-26
**Decision:** Send Telegram notifications via httpx POST to Bot API directly. No python-telegram-bot or other wrapper.
**Rationale:** We only need `sendMessage`. Adding a 5000-line wrapper lib for one API call is waste. httpx is already a dependency.

---

## DEC-005 — Phase-based scraper rollout [ACTIVE]

**Date:** 2026-03-26
**Decision:** Implement scrapers one at a time, each in its own phase/conversation. CaL first (discovery), then Momox + Recyclivre (buyback), then Rakuten + FNAC (marketplace).
**Rationale:** Each site has different structure/API. Exploring + coding + testing one at a time is more reliable than trying all at once. Stubs are in place for future phases.
