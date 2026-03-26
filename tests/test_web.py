"""Tests for the web dashboard."""

from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

import httpx
import pytest

from resell_bot.core.database import Database
from resell_bot.core.models import Alert, AlertStatus, Listing, ReferencePrice
from resell_bot.web.app import app, configure


def _make_listing(url: str = "https://example.com/book/1") -> Listing:
    return Listing(
        title="Fondation",
        price=5.0,
        url=url,
        platform="momox_shop",
        isbn="9782070360550",
        condition="bon",
        seller="Momox",
        author="Isaac Asimov",
        found_at=datetime.now(),
        image_url="https://example.com/img.jpg",
    )


@pytest.fixture
def db():
    tmpdir = TemporaryDirectory()
    database = Database(Path(tmpdir.name) / "test.db")
    configure(database)
    yield database
    database.close()
    tmpdir.cleanup()


@pytest.fixture
def client(db):
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


@pytest.fixture
def seeded_db(db):
    """DB with 2 alerts: one new, one bought."""
    listing1 = _make_listing("https://a.com/1")
    listing2 = _make_listing("https://a.com/2")
    db.save_listing(listing1)
    db.save_listing(listing2)
    a1 = Alert(listing=listing1, max_buy_price=15.0, savings=10.0)
    a2 = Alert(listing=listing2, max_buy_price=12.0, savings=7.0)
    db.save_alert(a1)
    id2 = db.save_alert(a2)
    db.update_alert_status(id2, AlertStatus.BOUGHT)
    return db


class TestDashboard:
    @pytest.mark.asyncio
    async def test_dashboard_empty(self, client):
        resp = await client.get("/")
        assert resp.status_code == 200
        assert "Aucune alerte" in resp.text

    @pytest.mark.asyncio
    async def test_dashboard_with_alerts(self, client, seeded_db):
        resp = await client.get("/")
        assert resp.status_code == 200
        assert "Fondation" in resp.text
        assert "momox_shop" in resp.text

    @pytest.mark.asyncio
    async def test_dashboard_filter_by_status(self, client, seeded_db):
        resp = await client.get("/?status=new")
        assert resp.status_code == 200
        assert "badge-new" in resp.text

    @pytest.mark.asyncio
    async def test_alert_detail(self, client, seeded_db):
        resp = await client.get("/alert/1")
        assert resp.status_code == 200
        assert "Fondation" in resp.text
        assert "Asimov" in resp.text

    @pytest.mark.asyncio
    async def test_alert_detail_not_found(self, client):
        resp = await client.get("/alert/999")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_status_to_bought(self, client, seeded_db):
        resp = await client.post("/alert/1/status/bought")
        assert resp.status_code == 200
        assert "badge-bought" in resp.text

    @pytest.mark.asyncio
    async def test_update_status_to_ignored(self, client, seeded_db):
        resp = await client.post("/alert/1/status/ignored")
        assert resp.status_code == 200
        assert "badge-ignored" in resp.text

    @pytest.mark.asyncio
    async def test_update_status_invalid(self, client, seeded_db):
        resp = await client.post("/alert/1/status/invalid_status")
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_stats_endpoint(self, client, seeded_db):
        resp = await client.get("/stats")
        assert resp.status_code == 200
        assert "Nouvelles" in resp.text


class TestBooksPage:
    @pytest.mark.asyncio
    async def test_books_empty(self, client):
        resp = await client.get("/books")
        assert resp.status_code == 200
        assert "Aucun livre dans la watchlist" in resp.text

    @pytest.mark.asyncio
    async def test_books_with_data(self, client, db):
        ref = ReferencePrice(
            isbn="9782070360550",
            max_buy_price=15.0,
            source="cal_import",
            title="Fondation",
            author="Isaac Asimov",
        )
        db.upsert_reference_price(ref)
        # Add a momox listing for this ISBN
        listing = Listing(
            title="Fondation",
            price=5.0,
            url="https://momox-shop.fr/M01234567890.html",
            platform="momox_shop",
            isbn="9782070360550",
            condition="bon",
            seller="Momox",
            author="Isaac Asimov",
            found_at=datetime.now(),
        )
        db.save_listing(listing)
        # Add availability record (books page now reads from isbn_availability)
        db.upsert_availability("9782070360550", "momox_shop", True, 5.0)

        resp = await client.get("/books")
        assert resp.status_code == 200
        assert "Fondation" in resp.text
        assert "5.00" in resp.text
        assert "15.00" in resp.text
        assert "+10.00" in resp.text

    @pytest.mark.asyncio
    async def test_books_search(self, client, db):
        ref = ReferencePrice(
            isbn="9782070360550",
            max_buy_price=15.0,
            source="cal_import",
            title="Fondation",
            author="Isaac Asimov",
        )
        db.upsert_reference_price(ref)

        resp = await client.get("/books?q=Fondation")
        assert resp.status_code == 200
        assert "Fondation" in resp.text

        resp = await client.get("/books?q=introuvable")
        assert resp.status_code == 200
        assert "Aucun livre" in resp.text

    @pytest.mark.asyncio
    async def test_books_no_momox_price(self, client, db):
        """Book in watchlist but never scanned on Momox."""
        ref = ReferencePrice(
            isbn="9782070360550",
            max_buy_price=15.0,
            source="cal_import",
            title="Fondation",
            author="Isaac Asimov",
        )
        db.upsert_reference_price(ref)

        resp = await client.get("/books")
        assert resp.status_code == 200
        assert "Fondation" in resp.text
