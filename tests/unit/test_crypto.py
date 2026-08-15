"""Encryption, blind index, and alias security tests."""

import pytest

from rejoinlater.crypto import CryptoError, DataProtector


def test_ciphertext_round_trip_and_random_nonce(key: str, other_key: str) -> None:
    protector = DataProtector(key, other_key)
    first = protector.encrypt_id(123456789)
    second = protector.encrypt_id(123456789)

    assert first != second
    assert b"123456789" not in first
    assert protector.decrypt_id(first) == 123456789


def test_incorrect_encryption_key_fails(key: str, other_key: str) -> None:
    value = DataProtector(key, other_key).encrypt_text("@publicgroup")

    with pytest.raises(CryptoError):
        DataProtector(other_key, key).decrypt_text(value)


def test_blind_indexes_are_keyed_and_deterministic(key: str, other_key: str) -> None:
    first = DataProtector(key, other_key)
    second = DataProtector(other_key, key)

    assert first.lookup_hash(42) == first.lookup_hash(42)
    assert first.lookup_hash(42) != first.lookup_hash(43)
    assert first.lookup_hash(42) != second.lookup_hash(42)
