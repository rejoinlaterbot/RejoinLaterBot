"""Public input and username-reassignment fail-closed tests."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.enums import ChatMemberStatus, ChatType
from aiogram.exceptions import TelegramBadRequest

from rejoinlater.services.telegram_access import (
    InvalidPublicLocator,
    bot_can_invite,
    inspect_bot_invite_access,
    normalize_public_input,
    resolve_public_input,
    validate_stored_destination,
)


def api_failure() -> TelegramBadRequest:
    """Return an API error whose message must never enter application logs."""

    return TelegramBadRequest(method=MagicMock(), message="sensitive locator")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("@somegroup", "@somegroup"),
        ("https://t.me/somegroup", "@somegroup"),
        ("t.me/somegroup", "@somegroup"),
        ("somegroup", "@somegroup"),
        ("-10012345", -10012345),
    ],
)
def test_normalize_supported_public_forms(raw: str, expected: str | int) -> None:
    assert normalize_public_input(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "https://t.me/+abcdef",
        "https://t.me/joinchat/abcdef",
        "http://t.me/somegroup",
        "https://example.com/somegroup",
        "https://t.me/somegroup/123",
        "tiny",
    ],
)
def test_reject_private_or_ambiguous_forms(raw: str) -> None:
    with pytest.raises(InvalidPublicLocator):
        normalize_public_input(raw)


@pytest.mark.asyncio
async def test_add_requires_group_and_public_username() -> None:
    bot = SimpleNamespace(
        get_chat=AsyncMock(
            return_value=SimpleNamespace(
                id=-1001,
                type=ChatType.SUPERGROUP,
                username="somegroup",
                title="Transient title",
            )
        )
    )

    destination = await resolve_public_input(bot, "@somegroup")

    assert destination.chat_id == -1001
    assert destination.username == "@somegroup"


@pytest.mark.asyncio
async def test_same_username_same_chat_id_is_safe() -> None:
    bot = SimpleNamespace(
        get_chat=AsyncMock(
            return_value=SimpleNamespace(
                id=-1001,
                type=ChatType.SUPERGROUP,
                username="samegroup",
                title="Current only",
            )
        )
    )

    result = await validate_stored_destination(bot, "@samegroup", -1001)

    assert result is not None and result.chat_id == -1001


@pytest.mark.asyncio
async def test_username_reassignment_never_uses_wrong_destination() -> None:
    bot = SimpleNamespace(
        get_chat=AsyncMock(
            return_value=SimpleNamespace(
                id=-9999,
                type=ChatType.SUPERGROUP,
                username="samegroup",
                title="Attacker destination",
            )
        )
    )

    result = await validate_stored_destination(bot, "@samegroup", -1001)

    assert result is None
    bot.get_chat.assert_awaited_once_with("@samegroup")


@pytest.mark.asyncio
async def test_missing_old_username_can_recover_new_username_by_original_id() -> None:
    new_chat = SimpleNamespace(
        id=-1001,
        type=ChatType.SUPERGROUP,
        username="newgroup",
        title="Current title",
    )
    bot = SimpleNamespace(get_chat=AsyncMock(side_effect=[api_failure(), new_chat]))

    result = await validate_stored_destination(bot, "@oldgroup", -1001)

    assert result is not None and result.username == "@newgroup"


@pytest.mark.asyncio
async def test_group_became_private_fails_closed() -> None:
    private_chat = SimpleNamespace(
        id=-1001,
        type=ChatType.SUPERGROUP,
        username=None,
        title="Must not persist",
    )
    bot = SimpleNamespace(get_chat=AsyncMock(side_effect=[api_failure(), private_chat]))

    assert await validate_stored_destination(bot, "@oldgroup", -1001) is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "can_invite", "expected"),
    [
        (ChatMemberStatus.ADMINISTRATOR, True, True),
        (ChatMemberStatus.ADMINISTRATOR, False, False),
        (ChatMemberStatus.MEMBER, False, False),
    ],
)
async def test_managed_permission_check(
    status: ChatMemberStatus, can_invite: bool, expected: bool
) -> None:
    bot = SimpleNamespace(
        get_me=AsyncMock(return_value=SimpleNamespace(id=1)),
        get_chat_member=AsyncMock(
            return_value=SimpleNamespace(status=status, can_invite_users=can_invite)
        ),
    )

    assert await bot_can_invite(bot, -1001) is expected


@pytest.mark.asyncio
async def test_inaccessible_selected_group_is_reported_as_not_joined() -> None:
    bot = SimpleNamespace(
        get_me=AsyncMock(return_value=SimpleNamespace(id=1)),
        get_chat_member=AsyncMock(side_effect=api_failure()),
    )

    access = await inspect_bot_invite_access(bot, -1001)

    assert access is not None
    assert access.is_member is False
    assert access.is_administrator is False
    assert access.can_invite_users is False
