"""PostgreSQL migration, encryption-at-rest, analytics, and due-index tests."""

from __future__ import annotations

import os
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from testcontainers.community.postgres import PostgresContainer

from rejoinlater.crypto import DataProtector
from rejoinlater.db.models import AggregateCounter, BreakRecord
from rejoinlater.db.repository import Repository
from rejoinlater.domain import (
    DeliveryMethod,
    DurationBucket,
    NewBreak,
    PauseReason,
    ReturnMode,
    Visibility,
)

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def postgres_url() -> Generator[str, None, None]:
    """Run migrations against a completely clean PostgreSQL container."""

    configured_url = os.environ.get("TEST_DATABASE_URL")
    if configured_url:
        old_url = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = configured_url
        config = Config(str(Path(__file__).parents[2] / "alembic.ini"))
        command.downgrade(config, "base")
        command.upgrade(config, "head")
        yield configured_url
        if old_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = old_url
        return

    try:
        container = PostgresContainer("postgres:17-alpine")
        container.start()
    except Exception as exc:
        pytest.skip(f"Docker/PostgreSQL unavailable: {type(exc).__name__}")
    url = container.get_connection_url().replace("psycopg2", "asyncpg")
    old_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url
    config = Config(str(Path(__file__).parents[2] / "alembic.ini"))
    command.upgrade(config, "head")
    yield url
    if old_url is None:
        os.environ.pop("DATABASE_URL", None)
    else:
        os.environ["DATABASE_URL"] = old_url
    container.stop()


@pytest.mark.asyncio
async def test_encrypted_creation_atomic_analytics_and_due_plan(
    postgres_url: str, key: str, other_key: str
) -> None:
    engine = create_async_engine(postgres_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    protector = DataProtector(key, other_key)
    repository = Repository(sessions, protector)
    new = NewBreak(
        user_id=123456789,
        chat_id=-100987654,
        public_locator="@privacygroup",
        mode=ReturnMode.PUBLIC,
        visibility=Visibility.HIDDEN,
        return_at=datetime.now(UTC) - timedelta(minutes=1),
        duration_bucket=DurationBucket.W1,
    )

    await repository.create_break(new)

    async with sessions() as session:
        record = (await session.scalars(select(BreakRecord))).one()
        counters = {
            row.key: row.value for row in (await session.scalars(select(AggregateCounter))).all()
        }
        assert b"123456789" not in record.user_id_enc
        assert b"-100987654" not in record.chat_id_enc
        assert b"@privacygroup" not in (record.public_locator_enc or b"")
        assert protector.decrypt_id(record.user_id_enc) == 123456789
        assert protector.decrypt_text(record.public_locator_enc or b"") == "@privacygroup"
        assert counters == {"privacy_hidden": 1, "duration_1w": 1, "mode_public": 1}

        await session.execute(text("ANALYZE break_records"))
        await session.execute(text("SET LOCAL enable_seqscan = off"))
        plan_rows = await session.execute(
            text(
                "EXPLAIN SELECT id FROM break_records "
                "WHERE return_at <= NOW() AND delivery_sent = FALSE "
                "AND delivery_paused = FALSE ORDER BY return_at LIMIT 100"
            )
        )
        plan = "\n".join(str(row[0]) for row in plan_rows)
        assert "ix_break_due_pending" in plan
    await engine.dispose()


@pytest.mark.asyncio
async def test_repeated_group_replaces_existing_return_and_resets_delivery(
    postgres_url: str, key: str, other_key: str
) -> None:
    engine = create_async_engine(postgres_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    protector = DataProtector(key, other_key)
    repository = Repository(sessions, protector)
    user_id = 22334455
    chat_id = -10011223344
    first_return_at = datetime.now(UTC) + timedelta(days=7)
    replacement_return_at = datetime.now(UTC) + timedelta(minutes=17)

    original_id = await repository.create_break(
        NewBreak(
            user_id=user_id,
            chat_id=chat_id,
            public_locator=None,
            mode=ReturnMode.MANAGED,
            visibility=Visibility.HIDDEN,
            return_at=first_return_at,
            duration_bucket=DurationBucket.W1,
        )
    )
    async with sessions() as session, session.begin():
        record = (
            await session.scalars(
                select(BreakRecord).where(
                    BreakRecord.user_lookup_hash == protector.lookup_hash(user_id),
                    BreakRecord.chat_lookup_hash == protector.lookup_hash(chat_id),
                )
            )
        ).one()
        record.delivery_sent = True
        record.delivery_sent_at = datetime.now(UTC)
        record.delivery_method = DeliveryMethod.MANAGED_INVITE
        record.delivery_paused = True
        record.pause_reason = PauseReason.UNAVAILABLE

    replacement_id = await repository.create_break(
        NewBreak(
            user_id=user_id,
            chat_id=chat_id,
            public_locator="@replacementgroup",
            mode=ReturnMode.PUBLIC,
            visibility=Visibility.VISIBLE,
            return_at=replacement_return_at,
            duration_bucket=DurationBucket.CUSTOM,
        )
    )

    async with sessions() as session:
        records = (
            await session.scalars(
                select(BreakRecord).where(
                    BreakRecord.user_lookup_hash == protector.lookup_hash(user_id),
                    BreakRecord.chat_lookup_hash == protector.lookup_hash(chat_id),
                )
            )
        ).all()

    assert replacement_id == original_id
    assert len(records) == 1
    replacement = records[0]
    assert replacement.mode == ReturnMode.PUBLIC
    assert replacement.visibility == Visibility.VISIBLE
    assert replacement.return_at == replacement_return_at
    assert protector.decrypt_text(replacement.public_locator_enc or b"") == "@replacementgroup"
    assert replacement.delivery_sent is False
    assert replacement.delivery_sent_at is None
    assert replacement.delivery_method is None
    assert replacement.delivery_paused is False
    assert replacement.pause_reason is None
    await repository.create_break(
        NewBreak(
            user_id=user_id,
            chat_id=-10099887766,
            public_locator=None,
            mode=ReturnMode.MANAGED,
            visibility=Visibility.HIDDEN,
            return_at=replacement_return_at - timedelta(minutes=1),
            duration_bucket=DurationBucket.CUSTOM,
        )
    )
    visible_returns = await repository.visible_returns(user_id, limit=5)
    assert visible_returns.total_count == 1
    assert [item.record_id for item in visible_returns.items] == [replacement_id]
    assert visible_returns.items[0].chat_id == chat_id
    assert visible_returns.items[0].public_locator == "@replacementgroup"
    async with sessions() as session, session.begin():
        owned = await repository.lock_visible_return(session, user_id, replacement_id)
        assert owned is not None
    async with sessions() as session, session.begin():
        foreign = await repository.lock_visible_return(session, user_id + 1, replacement_id)
        assert foreign is None
    await engine.dispose()
