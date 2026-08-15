"""Telegram command menus are contextual and localized."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.types import BotCommandScopeAllGroupChats, BotCommandScopeAllPrivateChats

from rejoinlater.i18n import SUPPORTED_LOCALES, I18n
from rejoinlater.telegram.commands import configure_bot_profile, configure_command_menu


@pytest.mark.asyncio
async def test_command_menu_has_private_group_and_localized_scopes() -> None:
    bot = SimpleNamespace(
        set_chat_menu_button=AsyncMock(),
        set_my_commands=AsyncMock(),
        delete_my_commands=AsyncMock(),
    )

    await configure_command_menu(bot, I18n())

    bot.set_chat_menu_button.assert_awaited_once()
    assert bot.set_my_commands.await_count == 1 + len(SUPPORTED_LOCALES)
    assert bot.delete_my_commands.await_count == 1 + len(SUPPORTED_LOCALES)

    calls = bot.set_my_commands.await_args_list
    private_default = next(
        call for call in calls if isinstance(call.kwargs["scope"], BotCommandScopeAllPrivateChats)
    )
    assert [command.command for command in private_default.args[0]] == [
        "about",
        "language",
        "add",
        "status",
    ]
    assert isinstance(
        bot.delete_my_commands.await_args_list[0].kwargs["scope"],
        BotCommandScopeAllGroupChats,
    )


@pytest.mark.asyncio
async def test_bot_profile_publishes_localized_unified_return_description() -> None:
    bot = SimpleNamespace(
        set_my_description=AsyncMock(),
        set_my_short_description=AsyncMock(),
    )
    i18n = I18n()

    await configure_bot_profile(bot, i18n)

    expected_calls = 1 + len(SUPPORTED_LOCALES)
    assert bot.set_my_description.await_count == expected_calls
    assert bot.set_my_short_description.await_count == expected_calls
    description = bot.set_my_description.await_args_list[0].kwargs["description"]
    assert "private invitation" in description
    assert "public group link" in description
    assert "verified" not in description.lower()
    assert all(
        len(catalog["bot_description"]) <= 512 and len(catalog["bot_short_description"]) <= 120
        for catalog in i18n.catalogs.values()
    )
