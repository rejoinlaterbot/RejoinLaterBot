"""Translation parity, status non-disclosure, and forbidden persistence fields."""

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from rejoinlater.db.models import BreakRecord, UserPreference
from rejoinlater.db.repository import VisibleReturn, VisibleReturnPage
from rejoinlater.domain import DurationBucket, ReturnMode, Visibility
from rejoinlater.i18n import SUPPORTED_LOCALES, I18n
from rejoinlater.telegram.routers.start import _show_about
from rejoinlater.telegram.routers.status import status_private
from rejoinlater.telegram.routers.wizard import (
    _DURATIONS,
    _show_confirmation,
    begin_wizard,
    custom_duration,
)


def test_all_translation_catalogs_have_identical_keys() -> None:
    i18n = I18n()
    expected = set(i18n.catalogs["en"])

    assert len(i18n.catalogs) == 7
    assert all(set(i18n.catalogs[locale]) == expected for locale in SUPPORTED_LOCALES)


def test_all_about_catalogs_link_to_the_public_apache_project() -> None:
    i18n = I18n()

    for catalog in i18n.catalogs.values():
        assert "Apache License 2.0" in catalog["open_source"]
        assert "https://github.com/rejoinlaterbot/RejoinLaterBot" in catalog["open_source"]


@pytest.mark.asyncio
async def test_about_message_shows_the_public_repository() -> None:
    message = SimpleNamespace(answer=AsyncMock())

    await _show_about(message, "en", I18n())

    text = message.answer.await_args.args[0]
    assert "Open source under the Apache License 2.0" in text
    assert "https://github.com/rejoinlaterbot/RejoinLaterBot" in text


def test_updated_english_and_russian_return_copy() -> None:
    i18n = I18n()
    english = i18n.catalogs["en"]
    russian = i18n.catalogs["ru"]

    assert not any("verified" in text.lower() for text in english.values())
    assert english["hidden_option"].startswith("Hidden return")
    assert russian["hidden_option"].startswith("Скрытный возврат")
    assert "secret_option" not in english
    assert Visibility.HIDDEN.value == "hidden"
    assert "clear the message history" in english["scheduled_managed"]
    assert "private invitation will not be sent" in english["scheduled_managed"]
    assert "очистить историю сообщений" in russian["scheduled_public"]
    assert "приватным приглашением отправлено не будет" in russian["scheduled_managed"]
    assert english["return_ready"].startswith("Your link to return to the group/channel:")
    assert russian["return_ready"].startswith("Ваша ссылка для возврата в группу/канал:")


@pytest.mark.asyncio
@pytest.mark.parametrize("hidden_count", [0, 50])
async def test_zero_visible_status_is_identical(hidden_count: int) -> None:
    """The unused parameter represents DB states the handler must never inspect."""

    _ = hidden_count
    i18n = I18n()
    message = SimpleNamespace(
        from_user=SimpleNamespace(id=7, language_code="en"), answer=AsyncMock()
    )
    repository = SimpleNamespace(
        preference=AsyncMock(return_value=SimpleNamespace(language_code="en")),
        visible_returns=AsyncMock(return_value=VisibleReturnPage(total_count=0, items=[])),
    )
    bot = SimpleNamespace(get_chat=AsyncMock())

    await status_private(message, repository, i18n, bot)

    message.answer.assert_awaited_once_with("Nothing to show here.", reply_markup=None)
    repository.visible_returns.assert_awaited_once_with(7, limit=5)


@pytest.mark.asyncio
async def test_status_shows_five_nearest_visible_group_titles_with_actions() -> None:
    i18n = I18n()
    now = datetime.now(UTC)
    returns = [
        VisibleReturn(
            record_id=uuid.uuid4(),
            chat_id=-1000 - index,
            public_locator=None,
            mode=ReturnMode.MANAGED,
            return_at=now + timedelta(days=index),
        )
        for index in range(1, 6)
    ]
    repository = SimpleNamespace(
        preference=AsyncMock(return_value=SimpleNamespace(language_code="en")),
        visible_returns=AsyncMock(return_value=VisibleReturnPage(total_count=12, items=returns)),
    )
    bot = SimpleNamespace(
        get_chat=AsyncMock(
            side_effect=[
                SimpleNamespace(id=item.chat_id, title=f"Group {index}")
                for index, item in enumerate(returns, start=1)
            ]
        )
    )
    message = SimpleNamespace(
        from_user=SimpleNamespace(id=7, language_code="en"),
        answer=AsyncMock(),
    )

    await status_private(message, repository, i18n, bot)

    text = message.answer.await_args.args[0]
    markup = message.answer.await_args.kwargs["reply_markup"]
    assert text.startswith("Active breaks: 12\n\n")
    assert all(f"{index}. Group {index}" in text for index in range(1, 6))
    assert "Return is scheduled in:" in text
    assert len(markup.inline_keyboard) == 5
    assert markup.inline_keyboard[0][0].text == "1. Return now"
    assert markup.inline_keyboard[0][0].callback_data == f"status:return:{returns[0].record_id}"


def test_forbidden_metadata_columns_do_not_exist() -> None:
    forbidden = {
        "group_name",
        "group_title",
        "group_description",
        "group_avatar",
        "user_username",
        "user_first_name",
        "user_last_name",
        "message_text",
        "deleted_at",
        "is_deleted",
    }

    assert forbidden.isdisjoint(BreakRecord.__table__.columns.keys())


def test_user_preferences_do_not_store_timezone() -> None:
    assert "utc_offset_minutes" not in UserPreference.__table__.columns


@pytest.mark.asyncio
async def test_visibility_explanations_are_attached_to_option_names() -> None:
    i18n = I18n()
    state = SimpleNamespace(update_data=AsyncMock(), set_state=AsyncMock())
    message = SimpleNamespace(answer=AsyncMock())

    await begin_wizard(message, state, "en", i18n)

    prompt = message.answer.await_args.args[0]
    markup = message.answer.await_args.kwargs["reply_markup"]
    assert ("Hidden return — recommended\nThis return will not be displayed in /status.") in prompt
    assert (
        "Visible return\n"
        "This return will be displayed in /status with the current group name and a Return now "
        "button."
    ) in prompt
    state.update_data.assert_awaited_once_with(visibility="hidden")
    assert markup.inline_keyboard[0][0].callback_data == "vis:hidden"


@pytest.mark.asyncio
async def test_confirmation_contains_only_relative_duration() -> None:
    i18n = I18n()
    state = SimpleNamespace(
        get_data=AsyncMock(
            return_value={
                "mode": ReturnMode.PUBLIC.value,
                "visibility": Visibility.HIDDEN.value,
                "duration_key": "6h",
            }
        ),
        set_state=AsyncMock(),
    )
    message = SimpleNamespace(answer=AsyncMock())

    await _show_confirmation(message, state, i18n, "en")

    confirmation = message.answer.await_args.args[0]
    assert "Return is scheduled in:\n6 hours" in confirmation
    assert "UTC" not in confirmation


@pytest.mark.asyncio
async def test_custom_integer_is_scheduled_in_days() -> None:
    i18n = I18n()
    state = SimpleNamespace(
        update_data=AsyncMock(),
        get_data=AsyncMock(
            return_value={
                "mode": ReturnMode.PUBLIC.value,
                "visibility": Visibility.HIDDEN.value,
                "custom_days": 5,
            }
        ),
        set_state=AsyncMock(),
    )
    message = SimpleNamespace(
        from_user=SimpleNamespace(id=7, language_code="en"),
        text="5",
        answer=AsyncMock(),
    )
    repository = SimpleNamespace(
        preference=AsyncMock(return_value=SimpleNamespace(language_code="en"))
    )
    settings = SimpleNamespace(max_custom_days=3650)

    before = datetime.now(UTC)
    await custom_duration(message, state, repository, i18n, settings)
    after = datetime.now(UTC)

    scheduled = datetime.fromisoformat(state.update_data.await_args.kwargs["return_at"])
    assert before + timedelta(days=5) <= scheduled <= after + timedelta(days=5)


def test_fixed_duration_options_include_hour_and_week_buckets() -> None:
    assert list(_DURATIONS) == ["1h", "6h", "12h", "1d", "3d", "1w", "2w", "30d"]
    assert _DURATIONS["1h"] == (timedelta(hours=1), DurationBucket.H1)
    assert _DURATIONS["1w"] == (timedelta(weeks=1), DurationBucket.W1)
    assert _DURATIONS["2w"] == (timedelta(days=14), DurationBucket.W2)
