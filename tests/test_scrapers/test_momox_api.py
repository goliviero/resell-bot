"""Tests for Momox API scraper (Medimops backend)."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from resell_bot.scrapers.momox_api import MomoxApiScraper, CONDITION_MAP


def _make_api_response(
    isbn="9782070360024",
    best_price=4.89,
    stock=10,
    variant_type="UsedVeryGood",
    name="L'Étranger",
    author="Albert Camus",
    mpid="M02070360024",
):
    """Build a mock Medimops API JSON response."""
    return {
        "data": {
            "products": [
                {
                    "id": "test-id",
                    "attributes": {
                        "ean": isbn,
                        "mpid": mpid,
                        "name": name,
                        "manufacturer": {"name": author},
                        "imageUrl": "https://example.com/img.jpg",
                        "webPath": f"/{mpid}.html",
                        "marketplaceData": [
                            {
                                "marketplaceId": "FRA",
                                "data": {
                                    "bestPrice": best_price,
                                    "stock": stock,
                                    "bestAvailableVariant": {
                                        "variantId": f"{mpid}{variant_type}",
                                        "variantType": variant_type,
                                    },
                                    "variants": [
                                        {
                                            "id": f"{mpid}{variant_type}",
                                            "type": variant_type,
                                            "stock": stock,
                                            "price": best_price,
                                        }
                                    ],
                                },
                            }
                        ],
                    },
                }
            ]
        }
    }


def _make_empty_response():
    return {"data": {"products": []}}


def _make_unavailable_response(isbn="9782070360024"):
    return {
        "data": {
            "products": [
                {
                    "id": "test-id",
                    "attributes": {
                        "ean": isbn,
                        "mpid": "M02070360024",
                        "name": "L'Étranger",
                        "manufacturer": {"name": "Albert Camus"},
                        "imageUrl": None,
                        "webPath": "/M02070360024.html",
                        "marketplaceData": [
                            {
                                "marketplaceId": "FRA",
                                "data": {
                                    "bestPrice": None,
                                    "stock": 0,
                                    "bestAvailableVariant": {},
                                    "variants": [],
                                },
                            }
                        ],
                    },
                }
            ]
        }
    }


class TestMomoxApiGetOffer:
    def _make_scraper(self, json_data, status_code=200):
        mock_resp = MagicMock()
        mock_resp.status_code = status_code
        mock_resp.json.return_value = json_data

        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        return MomoxApiScraper(mock_client)

    def test_available_book_returns_listing(self):
        scraper = self._make_scraper(_make_api_response(best_price=4.89, stock=10))
        listing = asyncio.run(scraper.get_offer("9782070360024"))

        assert listing is not None
        assert listing.price == 4.89
        assert listing.isbn == "9782070360024"
        assert listing.platform == "momox_shop"
        assert listing.seller == "Momox"
        assert listing.condition == "très bon"

    def test_unavailable_book_returns_none(self):
        scraper = self._make_scraper(_make_unavailable_response())
        listing = asyncio.run(scraper.get_offer("9782070360024"))

        assert listing is None

    def test_no_products_returns_none(self):
        scraper = self._make_scraper(_make_empty_response())
        listing = asyncio.run(scraper.get_offer("9999999999999"))

        assert listing is None

    def test_http_error_returns_none(self):
        scraper = self._make_scraper({}, status_code=500)
        listing = asyncio.run(scraper.get_offer("9782070360024"))

        assert listing is None

    def test_network_error_returns_none(self):
        mock_client = MagicMock()
        mock_client.get = AsyncMock(side_effect=Exception("connection refused"))
        scraper = MomoxApiScraper(mock_client)

        listing = asyncio.run(scraper.get_offer("9782070360024"))
        assert listing is None

    def test_title_and_author_extracted(self):
        scraper = self._make_scraper(
            _make_api_response(name="Le Petit Prince", author="Saint-Exupéry")
        )
        listing = asyncio.run(scraper.get_offer("9782070368228"))

        assert listing is not None
        assert listing.title == "Le Petit Prince"
        assert listing.author == "Saint-Exupéry"

    def test_all_conditions_mapped(self):
        for variant_type, expected_label in CONDITION_MAP.items():
            scraper = self._make_scraper(
                _make_api_response(variant_type=variant_type)
            )
            listing = asyncio.run(scraper.get_offer("9782070360024"))
            assert listing is not None
            assert listing.condition == expected_label, f"{variant_type} should map to {expected_label}"


class TestMomoxApiCheckAvailability:
    def _make_scraper(self, json_data, status_code=200):
        mock_resp = MagicMock()
        mock_resp.status_code = status_code
        mock_resp.json.return_value = json_data

        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        return MomoxApiScraper(mock_client)

    def test_available_returns_in_stock(self):
        scraper = self._make_scraper(_make_api_response(best_price=4.89, stock=10))
        result = asyncio.run(scraper.check_availability("9782070360024"))

        assert result is not None
        assert result["in_stock"] is True
        assert result["best_price"] == 4.89
        assert result["stock"] == 10

    def test_unavailable_returns_not_in_stock(self):
        scraper = self._make_scraper(_make_unavailable_response())
        result = asyncio.run(scraper.check_availability("9782070360024"))

        assert result is not None
        assert result["in_stock"] is False
        assert result["stock"] == 0

    def test_no_products_returns_not_in_stock(self):
        scraper = self._make_scraper(_make_empty_response())
        result = asyncio.run(scraper.check_availability("9999999999999"))

        assert result is not None
        assert result["in_stock"] is False


class TestMomoxApiPlatformName:
    def test_platform_name(self):
        scraper = MomoxApiScraper(MagicMock())
        assert scraper.platform_name == "momox_shop"
