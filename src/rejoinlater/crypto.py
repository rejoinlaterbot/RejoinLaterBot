"""Authenticated encryption and keyed lookup primitives.

Telegram identifiers and public locators must never be database-searchable plaintext.
AES-GCM provides confidentiality and tamper detection; separate HMAC keys create stable
blind indexes without enabling an offline dictionary attack from a database-only leak.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class CryptoError(ValueError):
    """Raised for invalid keys or malformed/authentication-failed ciphertext."""


def _decode_key(encoded: str, label: str) -> bytes:
    try:
        key = base64.urlsafe_b64decode(encoded.encode("ascii"))
    except (ValueError, UnicodeError) as exc:
        raise CryptoError(f"{label} must be URL-safe base64") from exc
    if len(key) != 32:
        raise CryptoError(f"{label} must decode to exactly 32 bytes")
    return key


class DataProtector:
    """Protect persistence values with AES-256-GCM and per-value random nonces."""

    _AAD = b"rejoinlater:v1"

    def __init__(self, encryption_key: str, lookup_key: str) -> None:
        self._aes = AESGCM(_decode_key(encryption_key, "DATA_ENCRYPTION_KEY"))
        self._lookup_key = _decode_key(lookup_key, "LOOKUP_HMAC_KEY")

    def encrypt_text(self, plaintext: str) -> bytes:
        """Encrypt UTF-8 text; the nonce prefix is safe to store with ciphertext."""

        nonce = os.urandom(12)
        return nonce + self._aes.encrypt(nonce, plaintext.encode("utf-8"), self._AAD)

    def decrypt_text(self, value: bytes) -> str:
        """Authenticate and decrypt a persisted value."""

        if len(value) < 29:
            raise CryptoError("ciphertext is malformed")
        try:
            plain = self._aes.decrypt(value[:12], value[12:], self._AAD)
            return plain.decode("utf-8")
        except (InvalidTag, UnicodeDecodeError) as exc:
            raise CryptoError("ciphertext authentication failed") from exc

    def encrypt_id(self, telegram_id: int) -> bytes:
        """Encrypt a Telegram integer without format-preserving leakage."""

        return self.encrypt_text(str(telegram_id))

    def decrypt_id(self, value: bytes) -> int:
        """Decrypt a Telegram integer ID."""

        try:
            return int(self.decrypt_text(value))
        except ValueError as exc:
            raise CryptoError("decrypted identifier is invalid") from exc

    def lookup_hash(self, telegram_id: int) -> bytes:
        """Build a deterministic HMAC blind index for a Telegram ID."""

        return hmac.new(
            self._lookup_key,
            str(telegram_id).encode("ascii"),
            hashlib.sha256,
        ).digest()
