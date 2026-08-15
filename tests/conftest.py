"""Shared deterministic test helpers."""

import base64

import pytest


@pytest.fixture
def key() -> str:
    """Return one valid URL-safe Base64 32-byte test key."""

    return base64.urlsafe_b64encode(bytes(range(32))).decode("ascii")


@pytest.fixture
def other_key() -> str:
    """Return a different valid key."""

    return base64.urlsafe_b64encode(bytes(range(1, 33))).decode("ascii")
