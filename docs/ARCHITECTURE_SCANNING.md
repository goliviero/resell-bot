# Architecture du systeme de scan — resell-bot

> Documentation complete du systeme de scan : version vulgarisee puis technique.
> Derniere mise a jour : 2026-03-26.

---

## 1. Version Simple (non-technique)

### Ce que fait le bot

Le bot surveille **1380 ISBN de livres** issus d'un export CSV de Chasse aux Livres (CaL). Pour chaque livre, on connait le **prix max d'achat** — le seuil au-dessus duquel l'affaire n'est plus rentable pour la revente.

### Comment il verifie les prix

Le bot interroge Momox Shop (momox-shop.fr) via leur **API interne JSON** — celle que leur propre site web utilise en coulisses. C'est comme demander a un libraire : "Tu as ce livre en stock ? A combien ?" Sauf qu'au lieu d'aller physiquement au comptoir (charger la page HTML complete), on appelle directement le systeme informatique du magasin. Resultat : la reponse arrive en **~80 millisecondes** au lieu de ~2 secondes.

### Scan en boucle continue parallele

Le bot scanne les **1380 ISBN en boucle infinie** avec **3 workers paralleles**. Chaque worker fait une requete API, attend 0.2-0.4 secondes, puis passe au suivant. L'ordre des ISBN est melange a chaque cycle pour eviter les patterns detectables.

| Metrique | Valeur |
|----------|--------|
| Workers paralleles | 3 |
| Delai entre requetes | 0.2-0.4 secondes par worker |
| Debit effectif | ~10 requetes/seconde |
| Cycle complet (1380 ISBNs) | **~3 minutes** |
| Latence max de detection | **3 minutes** (pire cas = livre verifie juste avant le restock) |

La logique : avec une API JSON a ~80ms/requete et sans Cloudflare, on peut se permettre un debit plus agressif. 10 req/s est raisonnable pour une API backend. En scannant TOUS les ISBN a chaque cycle (pas de tiers), on ne rate aucun livre — meme les livres bon marche sont verifies toutes les 3 minutes.

### Quand une affaire est detectee

Quand un livre est **disponible** ET que son prix est **inferieur ou egal au prix max d'achat** de la watchlist :

1. **Alerte Telegram** envoyee instantanement avec le titre, prix, lien d'achat, et marge estimee
2. **Dashboard web** mis a jour avec la nouvelle alerte
3. Possibilite de cliquer "Acheter" directement depuis le dashboard

### Le dashboard

Le dashboard web (accessible en local) affiche :

- **Toutes les alertes** (bonnes affaires detectees), triees par date
- **Tous les livres** de la watchlist avec leur statut de disponibilite (vert = dispo, rouge = indisponible)
- **Progression du scan en temps reel** : cycle en cours, combien de livres scannes, combien de deals trouves

### Performance

Un cycle complet des **1380 ISBN prend environ 3 minutes** avec 3 workers paralleles — contre environ **80 minutes** avec l'ancienne methode de scraping HTML. C'est un gain de **x27** grace a l'API JSON + parallelisme.

---

## 2. Version Technique Detaillee

### Decouverte de l'API Medimops

Momox Shop (momox-shop.fr) est un frontend **Next.js**. En inspectant le code source du site, on trouve les variables d'environnement exposees cote client :

```
NEXT_PUBLIC_BACKEND_API_URL = "https://api.medimops.de/v1"
NEXT_PUBLIC_MARKETPLACE = "fra"
```

L'endpoint de recherche :

```
GET https://api.medimops.de/v1/search?q={ISBN13}&marketplace_id=fra
```

**Reponse JSON** (structure simplifiee) :

```json
{
  "data": {
    "products": [{
      "attributes": {
        "name": "Titre du livre",
        "mpid": "M0xxxxxxxxx",
        "manufacturer": {"name": "Auteur"},
        "imageUrl": "https://...",
        "marketplaceData": [{
          "marketplaceId": "FRA",
          "data": {
            "bestPrice": 4.99,
            "stock": 3,
            "bestAvailableVariant": {
              "variantType": "UsedVeryGood",
              "price": 4.99
            },
            "variants": [...]
          }
        }]
      }
    }]
  }
}
```

**Caracteristiques de l'API :**

- **~80ms** par requete (contre ~2s pour le scraping HTML)
- **~500 bytes** de reponse (contre ~200KB pour une page HTML complete)
- **Pas de challenge Cloudflare** (contrairement a momox-shop.fr qui est protege)
- Fonctionne avec `curl_cffi` (impersonation Chrome) — le header `Accept: application/json` est important
- Pas d'authentification requise, pas de token API

### Architecture des fichiers

```
src/resell_bot/
├── scrapers/
│   ├── base.py          # ABC: get_offer(isbn) -> Listing | None
│   ├── momox_api.py     # MomoxApiScraper — API JSON Medimops (ACTIF)
│   └── momox.py         # MomoxShopScraper — ancien scraping HTML (ARCHIVE)
├── scheduler.py         # ScanScheduler — boucle continue parallele (Semaphore)
├── core/
│   ├── database.py      # SQLite — table isbn_availability pour le tracking
│   ├── notifier.py      # Hub multi-canal: Telegram + Discord + Email
│   └── models.py        # Listing, Alert dataclasses
└── web/
    └── app.py           # FastAPI + HTMX — endpoint /scan-status (auto-refresh 5s)
```

### `scrapers/momox_api.py` — MomoxApiScraper

Deux methodes principales :

- **`get_offer(isbn) -> Listing | None`** : appel API complet, construit un objet `Listing` avec titre, prix, URL, condition, auteur, image. Utilisee pour le scan de deals.
- **`check_availability(isbn) -> dict | None`** : verification legere, retourne `{isbn, in_stock, best_price, stock, condition}` sans construire de `Listing`. Utilisee pour les checks rapides.

Les conditions Momox sont mappees :

```python
CONDITION_MAP = {
    "UsedLikeNew": "comme neuf",
    "UsedVeryGood": "tres bon",
    "UsedGood": "bon",
    "UsedAcceptable": "acceptable",
    "New": "neuf",
    "LibriNew": "neuf",
}
```

### `scheduler.py` — ScanScheduler

Le scheduler fonctionne en **boucle continue parallele** :

1. `run_continuous()` tourne en boucle infinie, cycle apres cycle
2. A chaque cycle : recupere tous les ISBN de `reference_prices`, melange l'ordre
3. Lance les scans via `asyncio.create_task()` — **`asyncio.Semaphore(3)`** limite a 3 requetes API simultanees
4. Chaque worker : appel API → mise a jour `isbn_availability` → verification deal → sauvegarde alerte si applicable
5. `asyncio.Lock` protege les ecritures d'alertes (DB + notifications) entre workers concurrents

```python
# Config par defaut (config/settings.yaml)
max_workers = 3          # Workers paralleles
delay_min = 0.2          # Delai entre requetes par worker
delay_max = 0.4          # ~10 req/s effectif
```

Le statut de scan en direct est expose via `self.scan_status` (dict) et consomme par le dashboard via l'endpoint `/scan-status`.

### `core/database.py` — Table isbn_availability

```sql
CREATE TABLE isbn_availability (
    isbn TEXT NOT NULL,
    platform TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'unknown',   -- 'available' | 'unavailable' | 'unknown'
    last_price REAL,
    last_checked_at TEXT NOT NULL,
    last_changed_at TEXT,                     -- timestamp du dernier changement de statut
    check_count INTEGER DEFAULT 0,
    times_available INTEGER DEFAULT 0,        -- combien de fois passe en 'available'
    priority TEXT DEFAULT 'cold',             -- 'hot' | 'warm' | 'cold'
    PRIMARY KEY (isbn, platform)
);
```

Methodes cles :

- `upsert_availability()` : met a jour le statut et incremente `times_available` si le livre passe de indisponible a disponible. Retourne `True` si le statut a change.
- `get_all_reference_isbns()` : recupere tous les ISBN de la watchlist avec leur `max_buy_price`.
- `get_books_with_prices()` : jointure complete reference_prices + isbn_availability + listings pour l'affichage dashboard.

> Note : la colonne `priority` dans `isbn_availability` est un vestige du systeme de tiers (DEC-008, supersede par DEC-011). Le scan continu ignore cette colonne.

### Format d'URL Momox Shop

L'API retourne un champ `webPath` dans la reponse, mais cette URL donne **404 sur momox-shop.fr**. Le format correct est :

```
https://www.momox-shop.fr/{mpid}.html
```

Ou `mpid` vient de `attributes.mpid` dans la reponse API (format : `M0` + ISBN-10).

En fallback pour la recherche manuelle :

```
https://www.momox-shop.fr/recherche/{isbn}
```

### Strategie de Rate Limiting

| Parametre | Valeur | Source |
|-----------|--------|--------|
| Workers paralleles | 3 | `asyncio.Semaphore(3)` |
| Delai entre requetes (par worker) | 0.2 - 0.4 secondes | `config/settings.yaml` |
| Debit effectif | ~10 req/s | 3 workers / 0.3s avg |
| Cycle complet | ~3 min | 1380 ISBN / 10 req/s |
| Requetes par cycle | 1380 | Tous les ISBN a chaque cycle |

A ~10 req/s, **aucun ban IP observe**. L'API Medimops est un backend JSON concu pour le trafic programmatique — pas de Cloudflare, pas de rate limiting agressif pour ces volumes.

### DISTINCTION IMPORTANTE

Il existe **deux API Momox completement differentes** :

| API | URL | Ce qu'elle retourne | Usage |
|-----|-----|---------------------|-------|
| **Medimops Search** | `api.medimops.de/v1/search` | Prix de VENTE sur momox-shop.fr (ce que tu PAIES pour acheter) | **C'EST CELLE QU'ON UTILISE** |
| **Momox Offer** | `api.momox.de/v4/media/offer` | Prix de RACHAT par Momox (ce que Momox te paie) | **COMPLETEMENT HORS-SUJET, NE JAMAIS UTILISER** |

Notre modele est l'achat sur les plateformes pour revendre sur Vinted/Leboncoin. On cherche des livres **pas chers a acheter**, pas des livres a vendre a Momox.

### Flux de donnees complet

```
1. CaL CSV ──→ import_cal_watchlist.py ──→ reference_prices (1380 ISBN + max buy price)
                                                    │
2. run_continuous() ── boucle infinie               │
         │                                          │
         ▼                                          │
3. get_all_reference_isbns() ◄── reference_prices ──┘
   + shuffle (ordre aleatoire)
         │
         ▼
4. Scan parallele (Semaphore(3), 3 workers) :
   _scan_worker(isbn) ──→ MomoxApiScraper.get_offer(isbn) ──→ api.medimops.de/v1/search
         │
         ▼
5. Resultat :
   ├── Disponible → upsert_availability(isbn, True, price)
   │                  └── Si price <= max_buy_price → save_alert() → Telegram/Discord/Email
   └── Indisponible → upsert_availability(isbn, False)
         │
         ▼
6. Cycle complet (~3 min) → recommence immediatement
         │
         ▼
7. Dashboard (/scan-status) ──→ HTMX poll toutes les 5s ──→ affichage en temps reel
```

---

## 3. Comment Chasse aux Livres (CaL) fait

### Infrastructure probable de CaL

Chasse aux Livres surveille **des millions d'ISBN** sur **6+ plateformes** (Amazon, Fnac, Rakuten, Momox, Recyclivre, eBay, etc.). Voici l'infrastructure probable qu'ils utilisent :

### Serveurs et proxies

- **Cluster de VPS** (probablement OVH ou Scaleway, infrastructure francaise) avec un scraper dedie par plateforme
- **Pool de proxies residentiels** (BrightData, SmartProxy, ou similaire) coutant **plusieurs centaines d'euros par mois** — indispensable pour Amazon, Fnac, et tout site avec anti-bot agressif
- **Adresses IP multiples** pour eviter les bans : les proxies residentiels simulent des connexions depuis des box internet de particuliers, beaucoup plus difficiles a bloquer que des IP de datacenter

### Strategies techniques

- **APIs legeres quand elles existent** : Constructor.io pour la recherche Momox, eBay Browse API (officielle et gratuite), endpoints internes decouverts par reverse engineering des frontends
- **Scan differentiel** : CaL n'alerte que sur les **changements d'etat** (un livre qui passe de indisponible a disponible), pas a chaque verification. Cela reduit enormement le bruit
- **Tiers de priorite similaires aux notres** mais a une echelle bien plus large — probablement des dizaines de milliers de livres en tier "chaud"
- **Files d'attente distribuees** (Redis, RabbitMQ, ou Celery) pour coordonner les scrapers entre les differentes machines
- **Rotation de fingerprints** : variation des User-Agents, TLS fingerprints, et profils de navigation pour eviter la detection

### Notre avantage competitif

Pour nos 1380 ISBN sur Momox, **on bat CaL en vitesse** :

| | CaL | resell-bot |
|--|-----|------------|
| ISBN surveilles | Millions | 1380 |
| Plateformes | 6+ | 1 (Momox, pour l'instant) |
| Frequence scan (chaque ISBN) | Probablement 15-60 min | **~3 min** (cycle complet) |
| Infrastructure | Cluster multi-serveurs | Un seul PC, 1 IP |
| Debit API | Inconnu | ~10 req/s |

CaL doit repartir ses ressources sur des millions d'ISBN et plusieurs plateformes. Nous, on concentre tout sur 1380 ISBN avec un cycle complet toutes les ~3 minutes. **Chaque ISBN est verifie toutes les 3 minutes** — CaL ne peut probablement pas faire mieux sur sa watchlist Momox vu le nombre d'ISBN qu'ils gerent.

**Avantage CaL** : couverture (beaucoup de plateformes, beaucoup d'ISBN).
**Notre avantage** : vitesse de reaction sur notre watchlist specifique — ~3 min vs probablement 15-60 min chez CaL.

---

## 4. Ameliorations possibles pour reduire la latence

### 1. Augmenter les workers paralleles a 5 (au lieu de 3)

`asyncio.Semaphore(5)` au lieu de `Semaphore(3)`. L'API encaisse bien. Cycle passerait de ~3 min a ~2 min. A tester en surveillant les eventuels 429.

### 2. Reduire les delais a 0.1-0.2s (au lieu de 0.2-0.4s)

Avec 5 workers et 0.15s de delai moyen, on atteindrait ~33 req/s. Cycle ~40 secondes. Agressif mais l'API Medimops n'a pas montre de rate limiting.

### 3. WebSocket push au lieu du polling HTMX

Actuellement le dashboard poll `/scan-status` toutes les 5 secondes. Avec un WebSocket, l'alerte apparaitrait **instantanement** dans le dashboard des qu'elle est detectee, sans aucun delai de polling.

### 4. Notifications multi-canal

Deja implementees : Telegram, Discord (webhook), Email (SMTP). Les alertes sont envoyees instantanement a la detection. La latence principale vient du cycle de scan (~3 min), pas de l'envoi.

### 5. Rotation de fingerprints

Alterner les profils d'impersonation `curl_cffi` entre les requetes :

```python
# Au lieu d'un seul profil
PROFILES = ["chrome124", "firefox144", "safari18_0"]
```

Cela reduit le risque de detection par pattern — meme si on n'a pas observe de ban pour l'instant, c'est une mesure preventive.

### 6. API Constructor.io

Momox utilise Constructor.io pour sa recherche (visible dans les attributs `data-cnstrc-*` du HTML). Si on peut extraire la cle API publique, c'est un **autre endpoint JSON rapide** — potentiellement plus stable que l'API Medimops, et avec des donnees complementaires.

### 7. Connection pooling HTTP/2

Reutiliser les connexions TCP vers `api.medimops.de` au lieu d'un nouveau handshake TCP par requete. `curl_cffi` supporte HTTP/2 — il faut s'assurer que la session `AsyncSession` est bien reutilisee entre les requetes (c'est deja le cas dans notre implementation, mais on peut optimiser le keepalive).

### 8. Scheduling predictif

Apprendre les patterns de restockage de Momox. Par exemple, si Momox restocke principalement a 9h du matin les jours ouvrables, on peut scanner plus agressivement pendant ces fenetres et reduire la frequence la nuit.

### 9. Scan differentiel

Ne traiter que les livres dont le statut a **reellement change**. Si l'API retourne le meme prix et stock qu'au dernier check, on peut skipper le traitement de deal et la mise a jour en base, ce qui reduit la charge I/O.

### 10. Scan multi-plateforme parallele

Quand d'autres scrapers seront implementes, scanner **toutes les plateformes simultanement** par ISBN plutot que sequentiellement. Pour un ISBN donne, les appels Momox + Recyclivre + Rakuten sont independants et peuvent tourner en parallele.

---

## 5. Plan pour les autres sites

### Recyclivre (Priorite 1 — Facile)

| | Detail |
|--|--------|
| **Site** | recyclivre.com |
| **Protection** | Minimale, pas de Cloudflare agressif |
| **Approche** | Scraping HTML avec `curl_cffi`, recherche par ISBN |
| **Temps de reponse** | ~200ms par requete |
| **Complexite** | Faible — pages HTML simples, structure stable |
| **Timeline** | ~1 jour d'implementation |

Recyclivre vend des livres d'occasion a prix fixe. Le site est leger, peu protege, et la structure HTML est simple. C'est la prochaine plateforme a implementer.

### Rakuten France (Priorite 1 — Moyen)

| | Detail |
|--|--------|
| **Site** | fr.shopping.rakuten.com |
| **Protection** | Cloudflare leger |
| **Approche** | Inspecter les requetes XHR du frontend pour trouver un endpoint JSON. Fallback : scraping HTML |
| **Temps de reponse** | ~500ms par requete |
| **Complexite** | Moyenne — marketplace avec vendeurs multiples, prix variables |
| **Timeline** | ~2 jours |

Rakuten est une marketplace : plusieurs vendeurs proposent le meme livre a des prix differents. Il faudra extraire le prix le plus bas parmi les offres d'occasion.

### FNAC (Priorite 2 — Difficile)

| | Detail |
|--|--------|
| **Site** | fnac.com |
| **Protection** | Cloudflare agressif + DataDome (anti-bot specialise) |
| **Approche** | `curl_cffi` avec fingerprinting soigne + recherche d'endpoints API internes |
| **Temps de reponse** | Variable, risque de CAPTCHA |
| **Complexite** | Elevee — double protection anti-bot, detection comportementale |
| **Timeline** | 3-5 jours, possiblement non viable sans proxies |

La FNAC utilise DataDome en plus de Cloudflare, ce qui en fait l'un des sites les plus difficiles a scraper en France. Sans pool de proxies residentiels, le risque de ban est eleve. A evaluer si le volume de deals FNAC justifie l'investissement.

### eBay (Priorite 2 — Moyen)

| | Detail |
|--|--------|
| **Site** | ebay.fr |
| **Protection** | Aucune via l'API officielle |
| **Approche** | API officielle **Browse API** (developer.ebay.com, gratuite). Recherche par GTIN (= ISBN-13) |
| **Quota** | 5000 requetes/jour = ~3.6 scans complets des 1380 ISBN par jour |
| **Complexite** | Moyenne — inscription developpeur + OAuth, mais API bien documentee |
| **Timeline** | ~2 jours (inscription + implementation) |

L'avantage d'eBay est l'API officielle gratuite. L'inconvenient : le quota de 5000 requetes/jour limite la frequence de scan. On ne pourra pas scanner eBay aussi souvent que Momox, mais ca reste suffisant pour detecter les bonnes affaires en occasion a prix fixe ("Achat immediat").

### Amazon (Priorite 3 — Tres difficile)

| | Detail |
|--|--------|
| **Site** | amazon.fr |
| **Protection** | Tres agressive — anti-bot sophistique, CAPTCHA, device fingerprinting |
| **Approche** | Product Advertising API (PA-API) — necessite un compte affilie approuve avec un historique de ventes |
| **Temps de reponse** | N/A sans acces API |
| **Complexite** | Tres elevee |
| **Timeline** | Inconnue, deprioritise |

Amazon est le site le plus difficile a scraper. Le scraping direct est quasi-impossible sans proxies residentiels couteux. La PA-API est la seule voie viable, mais elle requiert un compte affilie Amazon approuve (Amazon Associates) avec un historique de ventes — ce qui prend du temps a obtenir.

**Verdict** : Amazon est deprioritise. Les bonnes affaires sur livres d'occasion chez Amazon sont rares (leur algorithme de pricing est agressif), et le cout d'implementation ne se justifie pas a ce stade.

---

> *Ce document decrit l'etat du systeme au 2026-03-26. Les valeurs (nombre d'ISBN, latences, debit) sont basees sur les mesures reelles avec l'export CaL de Franck. Le systeme utilise un scan continu parallele (pas de tiers de priorite).*
