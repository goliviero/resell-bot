"""Symmetric encryption for sensitive DB fields (SMTP passwords, etc.).

Uses Fernet (AES-128-CBC + HMAC-SHA256) with a key derived from the
ENCRYPTION_KEY env var. If no key is set, falls back to DASHBOARD_PASS.
"""

import base64
import hashlib
import logging
import os

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

_SALT = b"resell-bot-fernet-v1"
_fernet: Fernet | None = None


def _get_fernet() -> Fernet | None:
    """Derive a Fernet instance from env var. Cached after first call."""
    global _fernet
    if _fernet is not None:
        return _fernet

    secret = os.getenv("ENCRYPTION_KEY") or os.getenv("DASHBOARD_PASS")
    if not secret:
        return None

    derived = hashlib.pbkdf2_hmac("sha256", secret.encode(), _SALT, 100_000)
    key = base64.urlsafe_b64encode(derived[:32])
    _fernet = Fernet(key)
    return _fernet


def encrypt(plaintext: str) -> str:
    """Encrypt a string. Returns 'enc:...' prefixed ciphertext.

    If no encryption key is configured, returns the plaintext as-is
    (local dev mode).
    """
    f = _get_fernet()
    if f is None:
        return plaintext
    token = f.encrypt(plaintext.encode())
    return "enc:" + token.decode()


def decrypt(stored: str) -> str:
    """Decrypt a stored value. Handles both encrypted ('enc:...') and
    plain-text legacy values transparently.
    """
    if not stored.startswith("enc:"):
        # Legacy plain-text value — return as-is
        return stored

    f = _get_fernet()
    if f is None:
        logger.warning("Encrypted value found but no ENCRYPTION_KEY set — cannot decrypt")
        return ""

    try:
        return f.decrypt(stored[4:].encode()).decode()
    except InvalidToken:
        logger.error("Failed to decrypt value — wrong ENCRYPTION_KEY?")
        return ""
