"""Scraper for chasse-aux-livres.fr — book price aggregator.

Flow:
1. GET /search?query=X&catalog=fr → extract data-hash from #hash-cont
2. GET /rest/search-results?h={hash}&p=1&l=1&duih= → JSON with HTML in 'd' key
3. Parse <tr> rows: title, author, ISBN, URL, image, page count
4. For price details, follow /prix/{id}/ links (loaded via separate API)

Note: CaL is an aggregator — it shows where to BUY, not buyback prices.
Buyback prices come from Momox/Recyclivre scrapers (future phases).
"""

import logging
import re
from datetime import datetime

from bs4 import BeautifulSoup

from resell_bot.core.models import Listing
from resell_bot.scrapers.base import BaseScraper
from resell_bot.utils.http_client import HttpClient

logger = logging.getLogger(__name__)

BASE_URL = "https://www.chasse-aux-livres.fr"


class ChasseAuxLivresScraper(BaseScraper):
    """Scraper for chasse-aux-livres.fr search results."""

    def __init__(self, http_client: HttpClient) -> None:
        self.client = http_client

    @property
    def platform_name(self) -> str:
        return "chasseauxlivres"

    async def _get_search_hash(self, query: str) -> str | None:
        """Load the search page and extract the query hash for the API."""
        resp = await self.client.get(
            f"{BASE_URL}/search",
            params={"query": query, "catalog": "fr"},
        )
        if resp.status_code != 200:
            logger.warning("Search page returned %d", resp.status_code)
            return None

        match = re.search(r'data-hash="([a-f0-9]+)"', resp.text)
        if not match:
            logger.warning("Could not find data-hash in search page")
            return None
        return match.group(1)

    async def _fetch_results(self, query_hash: str) -> str | None:
        """Call the REST API to get search results HTML."""
        try:
            data = await self.client.get_json(
                f"{BASE_URL}/rest/search-results",
                params={"h": query_hash, "p": "1", "l": "1", "duih": ""},
                extra_headers={"Referer": f"{BASE_URL}/search"},
            )
            return data.get("d")
        except Exception as e:
            logger.warning("Failed to fetch search results: %s", e)
            return None

    def _parse_results(self, html: str) -> list[Listing]:
        """Parse book listings from the search results HTML table rows."""
        soup = BeautifulSoup(html, "lxml")
        rows = soup.find_all("tr", id=re.compile(r"^p\d+-\d+$"))
        listings: list[Listing] = []

        for row in rows:
            try:
                listing = self._parse_row(row)
                if listing:
                    listings.append(listing)
            except Exception as e:
                logger.debug("Failed to parse row: %s", e)
                continue

        return listings

    def _parse_row(self, row: BeautifulSoup) -> Listing | None:
        """Extract a single Listing from a <tr> row."""
        # Title + URL from the first link in .title
        title_div = row.find("div", class_="title")
        if not title_div:
            return None
        title_link = title_div.find("a")
        if not title_link:
            return None

        title = title_link.get_text(strip=True)
        relative_url = title_link.get("href", "")
        url = f"{BASE_URL}{relative_url}" if relative_url.startswith("/") else relative_url

        # ISBN from URL pattern /prix/{isbn}/...
        isbn_match = re.search(r"/prix/(\w+)/", relative_url)
        raw_isbn = isbn_match.group(1) if isbn_match else None

        # Author
        author_tag = row.find("a", class_="creator")
        author = author_tag.get_text(strip=True) if author_tag else None

        # Publisher + year
        publisher = None
        editor_div = row.find("div", class_="editor")
        if editor_div:
            publisher = editor_div.get_text(strip=True)

        # Image
        img = row.find("img")
        image_url = img.get("src") or img.get("data-src") if img else None

        # Page count from data attribute
        pages_raw = row.get("data-pag")
        pages = int(pages_raw) if pages_raw and pages_raw.isdigit() else None

        # ISBN from text (more reliable than URL slug)
        isbn_from_text = None
        binding_divs = row.find_all("div", class_="binding")
        for div in binding_divs:
            text = div.get_text()
            isbn_match_text = re.search(r"978[\d-]{10,16}", text)
            if isbn_match_text:
                isbn_from_text = re.sub(r"[^0-9]", "", isbn_match_text.group())
                break

        isbn = isbn_from_text or raw_isbn

        # CaL is an aggregator — individual prices aren't in search results.
        # We set price=0.0 as a placeholder; the real comparison happens
        # when we cross-reference with buyback scrapers.
        return Listing(
            title=title,
            price=0.0,
            url=url,
            platform=self.platform_name,
            isbn=isbn,
            condition=None,
            seller=None,
            author=author,
            found_at=datetime.now(),
            image_url=image_url,
            publisher=publisher,
            pages=pages,
        )

    async def search(self, query: str) -> list[Listing]:
        """Search for books by keyword."""
        query_hash = await self._get_search_hash(query)
        if not query_hash:
            return []

        await self.client._rate_limit_delay()

        html = await self._fetch_results(query_hash)
        if not html:
            return []

        listings = self._parse_results(html)
        logger.info("ChasseAuxLivres: %d results for '%s'", len(listings), query)
        return listings

    async def get_price(self, isbn: str) -> float | None:
        """CaL doesn't have a single price — it's an aggregator.

        For now, returns None. In a future version, we could scrape
        the /prix/{isbn}/ page to get the cheapest offer across stores.
        """
        return None
