# SWOT — resell-bot

> Updated: 2026-03-28 (post senior-dev-analyze audit)

## Strengths
- S1: Clean async architecture (curl_cffi + asyncio), Cloudflare bypass via TLS fingerprint
- S2: Momox API scraper: ~80ms/req, JSON, no Cloudflare — 3 min cycle for 1380 ISBNs
- S3: RecycLivre scraper: HTML + limit=5 optimization, 3 workers, ~13 min cycle
- S4: BDD CaL: 1380 ISBNs avec prix max d'achat (competitive intelligence)
- S5: SQLite dedup: 96h cooldown URL + restock-only alerts (unavailable→available transition)
- S6: ISBN validation + normalisation (ISBN-10/13 conversion, text extraction)
- S7: Dashboard web (FastAPI + HTMX) — alerts, books, settings, live scan per-platform
- S8: Architecture extensible: BaseScraper ABC, one file per platform
- S9: Multi-channel notifications: Telegram + Discord webhook + Email (Fernet-encrypted SMTP)
- S10: Continuous parallel scan: Momox ~3min + RecycLivre ~15min, independent loops
- S11: 135 tests passing (dead code cleaned), 40% test-to-code ratio
- S12: Daily digest at 08:00 + instant alerts on deal detection
- S13: Git hooks enforce conventional commits + activity logging
- S14: Tampermonkey autobuy v2.1: step-based flow, 90s TTL, Momox homepage relay
- S15: Docker + docker-compose ready, GitHub Actions CI
- S16: Cross-platform best_price in books page (min Momox/RecycLivre)

## Weaknesses
- W1: database.py at 907 LoC — largest file, acceptable but nearing refactor threshold
- W2: Single IP, no proxy rotation — ban risk at scale
- W3: No E2E test of full scan cycle (--once mode)
- W4: Bare except in some routes (partially fixed, check remaining)
- W5: Auth bypass when DASHBOARD_PASS not set — OK local, risk on VPS
- W6: Session secret regenerated on restart (users logged out)
- W7: Rakuten blocked by DataDome (needs SIRET for vendor API or residential proxies)

## Opportunities
- O1: Ammareal scraper — zero protection, HTML propre, PrestaShop, faisable ~30min
- O2: Rakuten via compte vendeur (SIRET) — API XML sans DataDome
- O3: eBay Browse API — official free API with dev key
- O4: VPS deployment (scan 24/7, ~5€/mois OVH/Scaleway)
- O5: Price history tracking + trend charts
- O6: Proxy rotation for multi-platform scaling
- O7: Constructor.io API exploration (alternative Momox endpoint)

## Threats
- T1: Medimops API lockdown/rate limiting — single point of failure for Momox
- T2: Ban IP at higher volumes on HTML scrapers (RecycLivre, future platforms)
- T3: Cloudflare/DataDome evolution blocking curl_cffi
- T4: 3D Secure blocking auto-buy automation
- T5: Competition from other snipers on same deals (speed race)
- T6: CaL dispatching deals to other users before us

## Scraping Feasibility

| Platform | Protection | Approach | Ban Risk | Status |
|----------|-----------|----------|----------|--------|
| **Momox Shop** | Aucune (API) | API JSON Medimops | Faible | **Done** — 3min/cycle |
| **RecycLivre** | Aucune | HTML + limit=5 | Faible | **Done** — 15min/cycle |
| **Ammareal** | Aucune | HTML PrestaShop | Faible | **Ready** — ~30min |
| **Rakuten** | DataDome | API XML (SIRET requis) | Moyen | **Blocked** — SIRET needed |
| **eBay** | Rate limit | Browse API officielle | Faible | Backlog |
| **FNAC** | DataDome strict | curl_cffi + proxy | Eleve | Backlog |
| **Amazon** | Tres strict | PA-API (affiliate) | Tres eleve | Backlog |
| **Gibert** | DataDome | Bloque | Eleve | Backlog |
