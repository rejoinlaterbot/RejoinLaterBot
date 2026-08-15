"""Private Managed Return chat-picker criteria and validation tests."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.enums import ChatMemberStatus, ChatType

from rejoinlater.domain import ReturnMode
from rejoinlater.i18n import I18n
from rejoinlater.telegram.routers.managed import (
    MANAGED_CHAT_REQUEST_ID,
    add_command,
    managed_chat_keyboard,
    managed_chat_selected,
)


def test_picker_does_not_request_bot_membership_or_admin_rights() -> None:
    keyboard = managed_chat_keyboard(I18n(), "en")
    request = keyboard.keyboard[0][0].request_chat

    assert request is not None
    assert request.chat_is_channel is False
    assert request.bot_is_member is None
    assert request.bot_administrator_rights is None
    assert request.user_administrator_rights is None
    assert request.request_title is None
    assert request.request_username is True
    assert request.request_photo is None
    serialized = request.model_dump(exclude_none=True)
    assert "bot_is_member" not in serialized
    assert "bot_administrator_rights" not in serialized
    assert "user_administrator_rights" not in serialized


@pytest.mark.asyncio
async def test_add_shows_only_neutral_group_picker_prompt() -> None:
    message = SimpleNamespace(
        from_user=SimpleNamespace(id=7, language_code="en"),
        answer=AsyncMock(),
    )
    state = SimpleNamespace(clear=AsyncMock())
    repository = SimpleNamespace(
        preference=AsyncMock(return_value=SimpleNamespace(language_code="en")),
        activate_user=AsyncMock(),
    )

    await add_command(message, state, repository, I18n())

    prompt = message.answer.await_args.args[0]
    keyboard = message.answer.await_args.kwargs["reply_markup"]
    assert prompt == "Choose a group:"
    assert keyboard.keyboard[0][0].text == "Choose group"
    assert "Invite Users" not in prompt


@pytest.mark.asyncio
async def test_selected_group_is_validated_and_enters_private_wizard() -> None:
    message = SimpleNamespace(
        from_user=SimpleNamespace(id=7, language_code="en"),
        chat_shared=SimpleNamespace(
            request_id=MANAGED_CHAT_REQUEST_ID,
            chat_id=-1001,
            username="managedgroup",
        ),
        answer=AsyncMock(),
    )
    state = SimpleNamespace(update_data=AsyncMock(), set_state=AsyncMock())
    repository = SimpleNamespace(
        preference=AsyncMock(return_value=SimpleNamespace(language_code="en"))
    )
    bot = SimpleNamespace(
        get_chat=AsyncMock(
            return_value=SimpleNamespace(
                id=-1001,
                type=ChatType.SUPERGROUP,
                username="managedgroup",
            )
        ),
        get_me=AsyncMock(return_value=SimpleNamespace(id=99)),
        get_chat_member=AsyncMock(
            return_value=SimpleNamespace(
                status=ChatMemberStatus.ADMINISTRATOR,
                can_invite_users=True,
            )
        ),
    )

    await managed_chat_selected(message, state, repository, I18n(), bot)

    state.update_data.assert_any_await(
        mode=ReturnMode.MANAGED.value,
        chat_id=-1001,
        public_locator="@managedgroup",
    )
    assert message.answer.await_count == 2
    checks = message.answer.await_args_list[0].args[0]
    assert "✅ Bot is a member of the group" in checks
    assert "✅ Bot is an administrator of the group" in checks
    assert "✅ Bot has the Invite Users permission" in checks


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "can_invite", "expected_reason", "expected_checks"),
    [
        (
            ChatMemberStatus.LEFT,
            False,
            "RejoinLaterBot has not been added to this group",
            ("❌", "❌", "❌"),
        ),
        (
            ChatMemberStatus.MEMBER,
            False,
            "RejoinLaterBot is not an administrator of this group",
            ("✅", "❌", "❌"),
        ),
        (
            ChatMemberStatus.ADMINISTRATOR,
            False,
            "RejoinLaterBot does not have the Invite Users permission",
            ("✅", "✅", "❌"),
        ),
    ],
)
async def test_failed_group_check_reports_exact_reason_privately(
    status: ChatMemberStatus,
    can_invite: bool,
    expected_reason: str,
    expected_checks: tuple[str, str, str],
) -> None:
    message = SimpleNamespace(
        from_user=SimpleNamespace(id=7, language_code="en"),
        chat_shared=SimpleNamespace(
            request_id=MANAGED_CHAT_REQUEST_ID,
            chat_id=-1001,
            username=None,
        ),
        answer=AsyncMock(),
    )
    state = SimpleNamespace(update_data=AsyncMock(), set_state=AsyncMock())
    repository = SimpleNamespace(
        preference=AsyncMock(return_value=SimpleNamespace(language_code="en"))
    )
    bot = SimpleNamespace(
        get_chat=AsyncMock(
            return_value=SimpleNamespace(
                id=-1001,
                type=ChatType.GROUP,
                username=None,
            )
        ),
        get_me=AsyncMock(return_value=SimpleNamespace(id=99)),
        get_chat_member=AsyncMock(
            return_value=SimpleNamespace(
                status=status,
                can_invite_users=can_invite,
            )
        ),
    )

    await managed_chat_selected(message, state, repository, I18n(), bot)

    state.update_data.assert_not_awaited()
    result = message.answer.await_args.args[0]
    assert expected_reason in result
    assert f"{expected_checks[0]} Bot is a member of the group" in result
    assert f"{expected_checks[1]} Bot is an administrator of the group" in result
    assert f"{expected_checks[2]} Bot has the Invite Users permission" in result
    assert "cannot create a private return invitation" in result
    assert result.index("cannot create a private return invitation") < result.index(
        f"☝️ {expected_reason}"
    )
    assert "This is a private group" in result


@pytest.mark.asyncio
async def test_failed_managed_checks_use_public_link_flow() -> None:
    message = SimpleNamespace(
        from_user=SimpleNamespace(id=7, language_code="en"),
        chat_shared=SimpleNamespace(
            request_id=MANAGED_CHAT_REQUEST_ID,
            chat_id=-1001,
            username="publicgroup",
        ),
        answer=AsyncMock(),
    )
    state = SimpleNamespace(update_data=AsyncMock(), set_state=AsyncMock())
    repository = SimpleNamespace(
        preference=AsyncMock(return_value=SimpleNamespace(language_code="en"))
    )
    bot = SimpleNamespace(
        get_me=AsyncMock(return_value=SimpleNamespace(id=99)),
        get_chat_member=AsyncMock(
            return_value=SimpleNamespace(
                status=ChatMemberStatus.LEFT,
                can_invite_users=False,
            )
        ),
        get_chat=AsyncMock(
            return_value=SimpleNamespace(
                id=-1001,
                type=ChatType.SUPERGROUP,
                username="publicgroup",
                title="Transient title",
            )
        ),
    )

    await managed_chat_selected(message, state, repository, I18n(), bot)

    state.update_data.assert_any_await(
        mode=ReturnMode.PUBLIC.value,
        chat_id=-1001,
        public_locator="@publicgroup",
    )
    result = message.answer.await_args_list[0].args[0]
    assert "has not been added to this group" in result
    assert "This is a public group" in result
    assert "public link" in result
    assert "verified" not in result.lower()
    assert message.answer.await_count == 2


@pytest.mark.asyncio
async def test_public_selection_with_mismatched_id_fails_closed() -> None:
    message = SimpleNamespace(
        from_user=SimpleNamespace(id=7, language_code="en"),
        chat_shared=SimpleNamespace(
            request_id=MANAGED_CHAT_REQUEST_ID,
            chat_id=-1001,
            username="reassigned",
        ),
        answer=AsyncMock(),
    )
    state = SimpleNamespace(update_data=AsyncMock(), set_state=AsyncMock())
    repository = SimpleNamespace(
        preference=AsyncMock(return_value=SimpleNamespace(language_code="en"))
    )
    bot = SimpleNamespace(
        get_me=AsyncMock(return_value=SimpleNamespace(id=99)),
        get_chat_member=AsyncMock(
            return_value=SimpleNamespace(
                status=ChatMemberStatus.LEFT,
                can_invite_users=False,
            )
        ),
        get_chat=AsyncMock(
            return_value=SimpleNamespace(
                id=-9999,
                type=ChatType.SUPERGROUP,
                username="reassigned",
                title="Different group",
            )
        ),
    )

    await managed_chat_selected(message, state, repository, I18n(), bot)

    state.update_data.assert_not_awaited()
    assert "could not be safely confirmed" in message.answer.await_args.args[0]
