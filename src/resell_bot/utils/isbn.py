"""ISBN-10 / ISBN-13 validation and normalisation."""

import re

ISBN_10_RE = re.compile(r"^(\d{9}[\dXx])$")
ISBN_13_RE = re.compile(r"^(97[89]\d{10})$")


def clean_isbn(raw: str) -> str:
    """Strip hyphens, spaces, and other non-digit chars (except trailing X)."""
    cleaned = re.sub(r"[^0-9Xx]", "", raw.strip())
    # Normalise trailing x to X
    if cleaned and cleaned[-1] == "x":
        cleaned = cleaned[:-1] + "X"
    return cleaned


def is_valid_isbn10(isbn: str) -> bool:
    """Validate an ISBN-10 checksum."""
    isbn = clean_isbn(isbn)
    if not ISBN_10_RE.match(isbn):
        return False
    total = 0
    for i, ch in enumerate(isbn[:9]):
        total += int(ch) * (10 - i)
    check = isbn[9]
    total += 10 if check == "X" else int(check)
    return total % 11 == 0


def is_valid_isbn13(isbn: str) -> bool:
    """Validate an ISBN-13 checksum."""
    isbn = clean_isbn(isbn)
    if not ISBN_13_RE.match(isbn):
        return False
    total = sum(int(ch) * (1 if i % 2 == 0 else 3) for i, ch in enumerate(isbn))
    return total % 10 == 0


def isbn10_to_isbn13(isbn10: str) -> str | None:
    """Convert ISBN-10 to ISBN-13. Returns None if input is invalid."""
    isbn10 = clean_isbn(isbn10)
    if not is_valid_isbn10(isbn10):
        return None
    body = "978" + isbn10[:9]
    total = sum(int(ch) * (1 if i % 2 == 0 else 3) for i, ch in enumerate(body))
    check = (10 - (total % 10)) % 10
    return body + str(check)


def isbn13_to_isbn10(isbn13: str) -> str | None:
    """Convert ISBN-13 to ISBN-10. Only works for 978-prefixed ISBNs."""
    isbn13 = clean_isbn(isbn13)
    if not is_valid_isbn13(isbn13) or not isbn13.startswith("978"):
        return None
    body = isbn13[3:12]
    total = sum(int(ch) * (10 - i) for i, ch in enumerate(body))
    check = (11 - (total % 11)) % 11
    check_char = "X" if check == 10 else str(check)
    return body + check_char


def normalize_isbn(raw: str) -> str | None:
    """Return a cleaned ISBN-13 if valid, else None."""
    cleaned = clean_isbn(raw)
    if len(cleaned) == 13 and is_valid_isbn13(cleaned):
        return cleaned
    if len(cleaned) == 10 and is_valid_isbn10(cleaned):
        return isbn10_to_isbn13(cleaned)
    return None


def extract_isbn_from_text(text: str) -> str | None:
    """Try to find an ISBN in free text."""
    # ISBN-13 first (more specific)
    match = re.search(r"97[89][\d-]{10,16}", text)
    if match:
        candidate = clean_isbn(match.group())
        if is_valid_isbn13(candidate):
            return candidate

    # ISBN-10
    match = re.search(r"\b(\d[\d-]{8,12}[\dXx])\b", text)
    if match:
        candidate = clean_isbn(match.group())
        if is_valid_isbn10(candidate):
            return isbn10_to_isbn13(candidate)

    return None
