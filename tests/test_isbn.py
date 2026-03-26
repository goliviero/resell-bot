"""Tests for ISBN validation and conversion."""

from resell_bot.utils.isbn import (
    clean_isbn,
    extract_isbn_from_text,
    is_valid_isbn10,
    is_valid_isbn13,
    isbn10_to_isbn13,
    isbn13_to_isbn10,
    normalize_isbn,
)


class TestCleanIsbn:
    def test_strips_hyphens(self):
        assert clean_isbn("978-2-07-036055-0") == "9782070360550"

    def test_strips_spaces(self):
        assert clean_isbn("978 2 07 036055 0") == "9782070360550"

    def test_normalizes_trailing_x(self):
        assert clean_isbn("2-253-00449-x") == "225300449X"


class TestIsbn10:
    def test_valid(self):
        assert is_valid_isbn10("2070360555")

    def test_valid_with_x(self):
        assert is_valid_isbn10("020161622X")

    def test_invalid_checksum(self):
        assert not is_valid_isbn10("2070360556")

    def test_too_short(self):
        assert not is_valid_isbn10("12345")


class TestIsbn13:
    def test_valid(self):
        assert is_valid_isbn13("9782070360550")

    def test_invalid_checksum(self):
        assert not is_valid_isbn13("9782070360551")

    def test_valid_979(self):
        assert is_valid_isbn13("9791032305690")


class TestConversion:
    def test_isbn10_to_isbn13(self):
        assert isbn10_to_isbn13("2070360555") == "9782070360550"

    def test_isbn13_to_isbn10(self):
        assert isbn13_to_isbn10("9782070360550") == "2070360555"

    def test_isbn13_979_cannot_convert(self):
        # 979-prefixed ISBNs can't be converted to ISBN-10
        assert isbn13_to_isbn10("9791032305690") is None

    def test_invalid_input_returns_none(self):
        assert isbn10_to_isbn13("invalid") is None
        assert isbn13_to_isbn10("invalid") is None


class TestNormalize:
    def test_isbn13_passthrough(self):
        assert normalize_isbn("9782070360550") == "9782070360550"

    def test_isbn10_converted(self):
        assert normalize_isbn("2070360555") == "9782070360550"

    def test_with_hyphens(self):
        assert normalize_isbn("978-2-07-036055-0") == "9782070360550"

    def test_invalid_returns_none(self):
        assert normalize_isbn("not-an-isbn") is None
        assert normalize_isbn("") is None


class TestExtractFromText:
    def test_finds_isbn13_in_text(self):
        assert extract_isbn_from_text("ISBN : 9782070360550") == "9782070360550"

    def test_finds_isbn13_with_hyphens(self):
        assert extract_isbn_from_text("Code ISBN: 978-2-07-036055-0") == "9782070360550"

    def test_finds_isbn10_and_converts(self):
        result = extract_isbn_from_text("Ref: 2070360555 - Fondation")
        assert result == "9782070360550"

    def test_no_isbn_returns_none(self):
        assert extract_isbn_from_text("No ISBN here") is None

    def test_prefers_isbn13(self):
        text = "ISBN-13: 9782070360550, ISBN-10: 2070360555"
        assert extract_isbn_from_text(text) == "9782070360550"
