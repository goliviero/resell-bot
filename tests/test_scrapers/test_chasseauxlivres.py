"""Tests for the Chasse aux Livres scraper."""

import re
from datetime import datetime

import pytest

from resell_bot.scrapers.chasseauxlivres import ChasseAuxLivresScraper
from resell_bot.utils.http_client import HttpClient

# Sample HTML from the /rest/search-results API (one result row)
SAMPLE_ROW_HTML = """
<tr id="p1-0" data-indx=1000 data-relv=9882 data-pubd="20000101" data-pag="1011">
  <td class="cover-column">
    <div class="cover-column-img">
      <a href="/prix/274413449X/le-cycle-de-fondation-asimov-isaac?query=fondation%20asimov"
         title="Le cycle de Fondation">
        <img src="https://img.chasse-aux-livres.fr/v7/_zmx1_/51vwRC8HxxL.jpg?w=180" alt="Le cycle de Fondation"/>
      </a>
    </div>
  </td>
  <td class="results-book-details">
    <div class="title">
      <a href="/prix/274413449X/le-cycle-de-fondation-asimov-isaac?query=fondation%20asimov"
         title="Le cycle de Fondation">Le cycle de Fondation</a>
    </div>
    <div class="creator-list">
      <a href="/search?query=author%3AAsimov%20Isaac" class="creator blue-text">Asimov, Isaac</a>
    </div>
    <div class="book-details3">
      <div class="editor">
        <a href="/search?query=publisher%3AFrance%20Loisirs">France Loisirs /Omnibus</a>&nbsp;-&nbsp;2000
      </div>
      <div class="binding">Relié, 1011 pages</div>
      <div class="binding">ISBN&nbsp;: 9782744134494</div>
    </div>
  </td>
  <td>Comparer les prix</td>
</tr>
"""

SAMPLE_MULTI_ROWS = """
<tr id="p1-0" data-pag="320">
  <td class="cover-column"><div class="cover-column-img"><a href="/prix/2070360555/fondation-asimov-isaac"><img src="https://img.example.com/a.jpg"/></a></div></td>
  <td class="results-book-details">
    <div class="title"><a href="/prix/2070360555/fondation-asimov-isaac">Fondation</a></div>
    <div class="creator-list"><a class="creator">Asimov, Isaac</a></div>
    <div class="book-details3"><div class="binding">ISBN&nbsp;: 9782070360550</div></div>
  </td>
</tr>
<tr id="p1-1" data-pag="416">
  <td class="cover-column"><div class="cover-column-img"><a href="/prix/2070415708/fondation-et-empire"><img src="https://img.example.com/b.jpg"/></a></div></td>
  <td class="results-book-details">
    <div class="title"><a href="/prix/2070415708/fondation-et-empire">Fondation et Empire</a></div>
    <div class="creator-list"><a class="creator">Asimov, Isaac</a></div>
    <div class="book-details3"><div class="binding">ISBN&nbsp;: 9782070415700</div></div>
  </td>
</tr>
"""


class TestChasseAuxLivresParser:
    """Test HTML parsing without network calls."""

    def setup_method(self):
        # We don't actually make HTTP calls in these tests
        self.scraper = ChasseAuxLivresScraper(HttpClient())

    def test_parse_single_row(self):
        listings = self.scraper._parse_results(SAMPLE_ROW_HTML)
        assert len(listings) == 1

        listing = listings[0]
        assert listing.title == "Le cycle de Fondation"
        assert listing.author == "Asimov, Isaac"
        assert listing.isbn == "9782744134494"
        assert listing.pages == 1011
        assert listing.platform == "chasseauxlivres"
        assert "274413449X" in listing.url
        assert listing.image_url is not None

    def test_parse_multiple_rows(self):
        listings = self.scraper._parse_results(SAMPLE_MULTI_ROWS)
        assert len(listings) == 2
        assert listings[0].title == "Fondation"
        assert listings[1].title == "Fondation et Empire"

    def test_parse_isbn_from_text(self):
        listings = self.scraper._parse_results(SAMPLE_ROW_HTML)
        # ISBN should come from the text "ISBN : 9782744134494" rather than URL slug
        assert listings[0].isbn == "9782744134494"

    def test_parse_empty_html(self):
        listings = self.scraper._parse_results("")
        assert listings == []

    def test_parse_no_title(self):
        html = '<tr id="p1-0"><td></td><td class="results-book-details"><div>No title div</div></td></tr>'
        listings = self.scraper._parse_results(html)
        assert listings == []

    def test_listing_has_correct_platform(self):
        listings = self.scraper._parse_results(SAMPLE_ROW_HTML)
        assert all(l.platform == "chasseauxlivres" for l in listings)

    def test_listing_url_is_absolute(self):
        listings = self.scraper._parse_results(SAMPLE_ROW_HTML)
        assert listings[0].url.startswith("https://www.chasse-aux-livres.fr/")

    def test_found_at_is_recent(self):
        listings = self.scraper._parse_results(SAMPLE_ROW_HTML)
        # Should be within the last minute
        delta = datetime.now() - listings[0].found_at
        assert delta.total_seconds() < 60
