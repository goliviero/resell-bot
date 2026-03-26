# SWOT — resell-bot

> Mis à jour: 2026-03-26

## Strengths
- S1: Clean async architecture (curl_cffi + asyncio), Cloudflare bypass intégré
- S2: Momox Shop scraper fonctionnel (HTML parsing, ISBN→MPID conversion)
- S3: BDD CaL solide: 1380 ISBNs avec prix max d'achat
- S4: SQLite dedup empêche les alertes en double (cooldown 24h)
- S5: ISBN validation + normalisation (ISBN-10/13 conversion, text extraction)
- S6: Dashboard web (FastAPI + HTMX) avec workflow new→seen→bought/ignored
- S7: Architecture extensible: BaseScraper ABC, un fichier par plateforme
- S8: Multi-channel notifications: Telegram + Discord webhook + Email SMTP
- S9: Medimops JSON API (~80ms vs ~2s HTML) — game changer
- S10: Continuous parallel scan: ALL 1380 ISBNs every ~3 min (3 workers, ~10 req/s)
- S11: 94 tests passing
- S12: Live scan dashboard with progress tracking + daily digest at 08:00

## Weaknesses
- W1: Seul Momox Shop est implémenté (5 autres plateformes en stubs)
- W2: Pas de test E2E du scan complet (--once)
- W3: Rate limiting testé avec succès sur 1380 ISBNs, pas de ban
- W4: Pas d'auto-buy (clic manuel nécessaire)
- W5: No price history tracking yet
- W6: Single IP (no proxy rotation)

## Opportunities
- O1: Recyclivre = scraping facile, pas de Cloudflare sévère
- O2: Rakuten = pages structurées, Cloudflare bypass via curl_cffi
- O3: eBay Browse API = accès programmatique officiel (avec clé dev)
- O4: Auto-buy via Playwright pour sniping rapide
- O5: Étendre au-delà des livres (vinyles, jeux vidéo, BD)
- O6: Alertes push mobile via Telegram → réaction rapide
- O7: Medimops API may expose other useful endpoints
- O8: Increase workers to 5 + reduce delays → cycle ~1-2 min
- O9: VPS scaling (3 OVH VPS → cycle ~1 min for ~11€/month)

## Threats
- T1: Cloudflare/anti-bot évoluent → scrapers cassés
- T2: Ban IP si trop de requêtes (1380 ISBNs × N plateformes)
- T3: Structure HTML des sites change sans prévenir
- T4: 3D Secure bloque l'auto-buy
- T5: Concurrence d'autres bots/snipers sur les mêmes deals
- T6: Medimops API could be locked down/changed

## Scraping Feasibility par plateforme

| Plateforme | Cloudflare | Anti-bot | Approche | Risque ban | Faisabilité |
|------------|-----------|----------|----------|-----------|-------------|
| **Momox Shop** | Non (API) | Faible | Fait — API JSON (api.medimops.de) | Faible | **Fait** |
| **Recyclivre** | Non/léger | Faible | HTML parsing | Faible | **Facile** |
| **Rakuten** | Léger | Moyen | HTML parsing + headers FR | Moyen si > 100 req/min | **Moyen** |
| **FNAC** | Strict | Agressif | curl_cffi + parsing | Élevé | **Difficile** |
| **eBay** | Non (API) | API rate limit | Browse API officielle | Faible avec clé | **Moyen** |
| **Amazon** | Très strict | Très agressif | Quasi impossible sans proxy | Très élevé | **Très difficile** |

### Recommandation anti-ban
- API JSON (Medimops): 0.2-0.4s entre requêtes, 3 workers → ~10 req/s — safe
- HTML scraping (autres plateformes): 1-2s entre requêtes, 1 worker — conservateur
- UA rotation: 10 User-Agents différents
- Randomiser l'ordre des ISBNs à chaque cycle pour éviter les patterns détectables
- Proxy rotation si ban IP (futur P2)
