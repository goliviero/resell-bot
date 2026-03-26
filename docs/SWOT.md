# SWOT — resell-bot

## Strengths
- S1: Clean async architecture (httpx + asyncio), single shared HTTP client
- S2: Working CaL scraper with real API integration (REST endpoint, not HTML scraping)
- S3: Solid price engine with configurable thresholds (min margin, max buy price, shipping cost)
- S4: SQLite dedup prevents duplicate alerts (cooldown-based)
- S5: ISBN validation + normalization (ISBN-10/13 conversion, text extraction)
- S6: 44 passing tests (scraper parsing, price engine, ISBN, database)
- S7: Config-driven (YAML settings + watchlists, .env for secrets)
- S8: Zero wrapper libs — Telegram via raw API, no ORM

## Weaknesses
- W1: Only 1/5 scrapers implemented (CaL discovery only, no buyback pricing)
- W2: CaL prices not scraped (JS-loaded, would need browser automation)
- W3: Rate limiting not battle-tested on real sustained scanning
- W4: No price history / trend detection yet
- W5: No error recovery / persistence of scan state between restarts

## Opportunities
- O1: Momox has a known pricing endpoint by ISBN — Phase 2 priority
- O2: Recyclivre buyback pricing — Phase 3
- O3: Arbitrage mode (cross-platform price comparison)
- O4: Daily digest Telegram message with best opportunities
- O5: Price history in SQLite for trend detection (price drops)
- O6: Extend beyond books (vinyls, jeux video — same resell logic)

## Threats
- T1: Platform HTML/API changes break scrapers (CSS selectors, endpoint URLs)
- T2: IP rate-limiting or bans on sustained scraping
- T3: CaL query hash mechanism could change
- T4: Anti-bot measures (Cloudflare, captcha) on future platforms (FNAC, Rakuten)

## Backlog (prioritized)

| Priority | Item | Status |
|----------|------|--------|
| P0 | Phase 2: Momox buyback scraper | Planned |
| P0 | Phase 3: Recyclivre buyback scraper | Planned |
| P1 | Phase 4: Rakuten marketplace scraper | Planned |
| P1 | Phase 5: FNAC marketplace scraper | Planned |
| P2 | Phase 6: Arbitrage mode + price history + daily digest | Planned |
