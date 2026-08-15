"""Duplicate Telegram /start protection."""

from __future__ import annotations

import asyncio

import pytest

from rejoinlater.telegram.deduplication import StartDeduplicator


@pytest.mark.asyncio
async def test_only_one_concurrent_start_is_accepted_per_user() -> None:
    guard = StartDeduplicator()

    results = await asyncio.gather(guard.accept(101), guard.accept(101))

    assert results.count(True) == 1
    assert results.count(False) == 1
    assert await guard.accept(202) is True


@pytest.mark.asyncio
async def test_user_is_forgotten_after_retry_window() -> None:
    guard = StartDeduplicator(window_seconds=0.001)

    assert await guard.accept(101) is True
    await asyncio.sleep(0.002)

    assert await guard.accept(101) is True
