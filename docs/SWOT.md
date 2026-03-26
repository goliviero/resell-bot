# SWOT — resell-bot

> Updated: 2026-03-26 (post-audit + remediation)

## Strengths
- S1: Clean async architecture (curl_cffi + asyncio), Cloudflare bypass
- S2: Momox API scraper: ~80ms/req, JSON, no Cloudflare — primary scanner
- S3: BDD CaL: 1380 ISBNs avec prix max d'achat (competitive intelligence)
- S4: SQLite dedup (24h cooldown) + isbn_availability tracking
- S5: ISBN validation + normalisation (ISBN-10/13 conversion, text extraction)
- S6: Dashboard web (FastAPI + HTMX) — alerts, books, settings, live scan
- S7: Architecture extensible: BaseScraper ABC, one file per platform
- S8: Multi-channel notifications: Telegram + Discord webhook + Email SMTP
- S9: Continuous parallel scan: ALL 1380 ISBNs every ~3 min (3 workers, ~10 req/s)
- S10: 124 tests passing, 48% test-to-code ratio
- S11: Daily digest at 08:00 + instant alerts on deal detection
- S12: Git hooks enforce conventional commits + activity logging
- S13: Auto-buy prototype (buyer.py, Playwright flow)
- S14: 2,582 lines of production code — lean, focused codebase

## Weaknesses
- W1: Only Momox implemented (5 platform stubs consolidated in _stubs.py)
- W2: ~~No tests for scheduler/notifier~~ → **FIXED**: 30 new tests (12 scheduler + 18 notifier)
- W3: ~~No lockfile~~ → **FIXED**: requirements.txt with 47 pinned deps
- W4: database.py at 561 lines — largest file, acceptable for single-module SQLite wrapper
- W5: priority.py is dead code (11 tests for unused module, DEC-008 superseded)
- W6: Single IP, no proxy rotation
- W7: ~~No CI/CD~~ → **FIXED**: GitHub Actions CI (.github/workflows/ci.yml)
- W8: No E2E test of full scan cycle (--once mode)

## Opportunities
- O1: Recyclivre scraper — easy, no Cloudflare, HTML parsing
- O2: Rakuten scraper — medium, structured pages
- O3: eBay Browse API — official free API with dev key
- O4: Auto-buy completion (buyer.py WIP → production)
- O5: Increase workers to 5 + reduce delays → cycle ~1-2 min
- O6: VPS scaling (3 OVH VPS ~11€/m → cycle ~1 min)
- O7: Price history tracking + trend charts
- O8: Constructor.io API exploration (alternative Momox endpoint)
- O9: ~~GitHub Actions CI~~ → **Done**

## Threats
- T1: Medimops API lockdown/rate limiting — single point of failure
- T2: Ban IP at higher volumes (multi-platform scaling)
- T3: Cloudflare/anti-bot evolution on new platforms
- T4: 3D Secure blocking auto-buy automation
- T5: Competition from other snipers on same deals (speed race)
- T6: CaL dispatching deals to other users before us

## Scraping Feasibility

| Platform | Cloudflare | Anti-bot | Approach | Ban Risk | Status |
|----------|-----------|----------|----------|----------|--------|
| **Momox Shop** | Non (API) | Faible | API JSON (api.medimops.de) | Faible | **Done** |
| **Recyclivre** | Non/léger | Faible | HTML parsing | Faible | **Easy** |
| **Rakuten** | Léger | Moyen | HTML + headers FR | Moyen | **Medium** |
| **eBay** | Non (API) | Rate limit | Browse API officielle | Faible | **Medium** |
| **FNAC** | Strict | Agressif | curl_cffi + DataDome | Élevé | **Hard** |
| **Amazon** | Très strict | Très agressif | PA-API (affiliate) | Très élevé | **Very Hard** |

### Anti-ban strategy
- API JSON (Medimops): 0.2-0.4s delay, 3 workers → ~10 req/s — safe
- HTML scraping (future): 1-2s delay, 1 worker — conservative
- UA rotation: 10 User-Agents, randomized order each cycle
- Proxy rotation if IP banned (future P2)
