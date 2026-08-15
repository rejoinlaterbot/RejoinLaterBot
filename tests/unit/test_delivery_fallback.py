"""Managed/Public fallback routing tests around the identity validator boundary."""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from rejoinlater.crypto import DataProtector
from rejoinlater.domain import (
    DeliveryMethod,
    PauseReason,
    PublicDestination,
    ReturnMode,
    Visibility,
)
from rejoinlater.i18n import I18n
from rejoinlater.services import delivery
from rejoinlater.services.delivery import DeliveryWorker


def make_worker(key: str, other_key: str) -> tuple[DeliveryWorker, SimpleNamespace, DataProtector]:
    """Create a worker whose fake boundaries retain no Telegram metadata."""

    protector = DataProtector(key, other_key)
    repository = SimpleNamespace(
        preference=AsyncMock(return_value=SimpleNamespace(language_code="en")),
        increment_fallback=AsyncMock(),
    )
    bot = SimpleNamespace(send_message=AsyncMock())
    settings = SimpleNamespace(invite_ttl_hours=24)
    worker = DeliveryWorker(
        bot=bot,
        repository=repository,
        protector=protector,
        i18n=I18n(),
        settings=settings,
    )
    return worker, repository, protector


def make_record(protector: DataProtector, public: bool = True) -> SimpleNamespace:
    """Build one transient ORM-like pending Managed record."""

    return SimpleNamespace(
        id=uuid.uuid4(),
        mode=ReturnMode.MANAGED,
        visibility=Visibility.HIDDEN,
        user_id_enc=protector.encrypt_id(7),
        chat_id_enc=protector.encrypt_id(-1001),
        public_locator_enc=protector.encrypt_text("@oldgroup") if public else None,
        delivery_sent=False,
        delivery_sent_at=None,
        delivery_method=None,
        delivery_paused=False,
        pause_reason=None,
    )


@pytest.mark.asyncio
async def test_managed_permission_lost_uses_only_validated_public_fallback(
    key: str, other_key: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    worker, repository, protector = make_worker(key, other_key)
    record = make_record(protector)
    session = SimpleNamespace(delete=AsyncMock())
    monkeypatch.setattr(delivery, "bot_can_invite", AsyncMock(return_value=False))
    monkeypatch.setattr(
        delivery,
        "validate_stored_destination",
        AsyncMock(return_value=PublicDestination(-1001, "@currentgroup", "Current title")),
    )

    await worker._deliver_locked(session, record)

    assert record.delivery_sent is True
    assert record.delivery_method == DeliveryMethod.PUBLIC_LINK
    repository.increment_fallback.assert_awaited_once_with(session)
    sent_markup = worker.bot.send_message.await_args.kwargs["reply_markup"]
    assert sent_markup.inline_keyboard[0][0].url == "https://t.me/currentgroup"
    assert sent_markup.inline_keyboard[0][0].text == "Current title"
    assert "Current title" in worker.bot.send_message.await_args.args[1]


@pytest.mark.asyncio
async def test_immediate_visible_return_is_deleted_after_successful_delivery(
    key: str, other_key: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    worker, repository, protector = make_worker(key, other_key)
    record = make_record(protector)
    record.visibility = Visibility.VISIBLE
    session = SimpleNamespace(delete=AsyncMock())
    monkeypatch.setattr(delivery, "bot_can_invite", AsyncMock(return_value=False))
    monkeypatch.setattr(
        delivery,
        "validate_stored_destination",
        AsyncMock(return_value=PublicDestination(-1001, "@currentgroup", "Current title")),
    )

    completed = await worker._deliver_locked(session, record, delete_after_delivery=True)

    assert completed is True
    session.delete.assert_awaited_once_with(record)
    assert record.delivery_sent is False
    repository.increment_fallback.assert_awaited_once_with(session)


@pytest.mark.asyncio
async def test_managed_private_group_never_invents_fallback(
    key: str, other_key: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    worker, repository, protector = make_worker(key, other_key)
    record = make_record(protector, public=False)
    session = SimpleNamespace(delete=AsyncMock())
    monkeypatch.setattr(delivery, "bot_can_invite", AsyncMock(return_value=False))

    await worker._deliver_locked(session, record)

    assert record.delivery_sent is False
    assert record.delivery_paused is True
    assert record.pause_reason == PauseReason.UNAVAILABLE
    repository.increment_fallback.assert_not_awaited()
    assert "https://t.me/" not in worker.bot.send_message.await_args.args[1]


@pytest.mark.asyncio
async def test_reassigned_managed_username_never_sends_public_url(
    key: str, other_key: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    worker, repository, protector = make_worker(key, other_key)
    record = make_record(protector)
    session = SimpleNamespace(delete=AsyncMock())
    monkeypatch.setattr(delivery, "bot_can_invite", AsyncMock(return_value=False))
    validator = AsyncMock(return_value=None)
    monkeypatch.setattr(delivery, "validate_stored_destination", validator)

    await worker._deliver_locked(session, record)

    validator.assert_awaited_once_with(worker.bot, "@oldgroup", -1001)
    assert record.delivery_sent is False
    assert record.pause_reason == PauseReason.UNAVAILABLE
    repository.increment_fallback.assert_not_awaited()
    assert worker.bot.send_message.await_args.kwargs.get("reply_markup") is None
