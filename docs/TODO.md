# TODO — resell-bot

> Last updated: 2026-03-26

## Vision

Acheter des livres rares/sous-cotés sur des plateformes (Momox Shop, Rakuten, Recyclivre, FNAC, eBay, Amazon) puis les revendre sur Vinted/Leboncoin.
La BDD CaL (export CSV) contient les ISBNs à surveiller avec un prix max d'achat.
Le bot scanne les plateformes et alerte quand un livre est dispo sous le prix max.

## Done

| # | Task | Status |
|---|------|--------|
| 1 | Core infra: models, DB, notifier, ISBN utils, HTTP client | Done |
| 2 | curl_cffi pour bypass Cloudflare (Momox) | Done |
| 3 | Import CSV CaL → reference_prices (1380 ISBNs) | Done |
| 4 | Dashboard web (FastAPI + HTMX) | Done |
| 5 | Momox Shop scraper (momox-shop.fr, HTML parsing) | Done |
| 6 | Refactor complet: modèle achat (pas rachat) | Done |
| 7 | Medimops JSON API scraper (momox_api.py) — remplace HTML scraping, ~80ms/req | Done |
| 8 | Priority tiers HOT/WARM/COLD (superseded by #15) | Done |
| 9 | Parallel scanning (asyncio.Semaphore(3) + gather) | Done |
| 10 | isbn_availability tracking table | Done |
| 11 | Dashboard scan status panel (live progress) | Done |
| 12 | Livres tab avec availability indicators (green/red) + filters | Done |
| 13 | 94 tests passing | Done |
| 14 | Direct Momox links on alerts + fixed 404s | Done |
| 15 | Continuous parallel scan — all 1380 ISBNs every ~3 min (replaces tiers) | Done |
| 16 | Discord webhook + Email SMTP notifications (instant + daily digest 08:00) | Done |
| 17 | Settings page in dashboard (configure Discord/Email) | Done |

## In Progress

| # | Task | Status |
|---|------|--------|
| — | (nothing currently) | — |

## Backlog

| # | Task | Priority | Feasibility |
|---|------|----------|-------------|
| 18 | Increase workers to 5 + reduce delay → cycle ~1-2 min | P1 | Facile — config, tester absence de 429 |
| 19 | WebSocket push for instant alerts | P2 | Moyen — remplace HTMX polling |
| 20 | Fingerprint rotation (curl_cffi profiles) | P2 | Moyen — pool de TLS fingerprints |
| 21 | Constructor.io API exploration | P2 | À explorer — search API Momox/Medimops |
| 22 | Price history table + charts | P2 | Facile |
| 23 | Proton Drive sync for real DB backup | P2 | Facile — CLI rclone |
| 24 | Recyclivre scraper | P1 | Facile — pas de Cloudflare, pages produit simples |
| 25 | Rakuten scraper | P1 | Moyen — Cloudflare léger, pages produit structurées |
| 26 | FNAC scraper | P2 | Difficile — anti-bot agressif, Cloudflare strict |
| 27 | eBay scraper | P2 | Moyen — API Browse disponible (nécessite clé dev) |
| 28 | Amazon scraper | P3 | Très difficile — anti-bot très agressif, rate limiting sévère |
| 29 | Auto-buy Momox (Playwright) | P1 | Complexe — checkout multi-étapes, possible 3D Secure |
| 30 | VPS scaling (3 VPS OVH ~11€/m → cycle ~1 min) | P2 | Config réseau + déploiement |
| 31 | Proxy rotation | P2 | Nécessaire si ban IP |
| 32 | Étendre au-delà des livres (vinyles, jeux vidéo) | P3 | Même logique |
