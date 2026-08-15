"""Context-specific Telegram command menu registration."""

from __future__ import annotations

from aiogram import Bot
from aiogram.types import (
    BotCommand,
    BotCommandScopeAllGroupChats,
    BotCommandScopeAllPrivateChats,
    MenuButtonCommands,
)

from rejoinlater.i18n import SUPPORTED_LOCALES, I18n


def _private_commands(i18n: I18n, locale: str) -> list[BotCommand]:
    """Commands available in a private conversation."""

    return [
        BotCommand(command="about", description=i18n.t(locale, "command_about")),
        BotCommand(command="language", description=i18n.t(locale, "command_language")),
        BotCommand(command="add", description=i18n.t(locale, "command_add")),
        BotCommand(command="status", description=i18n.t(locale, "command_status")),
    ]


async def configure_command_menu(bot: Bot, i18n: I18n) -> None:
    """Register default and localized menus for private chats and groups."""

    await bot.set_chat_menu_button(menu_button=MenuButtonCommands())
    private_scope = BotCommandScopeAllPrivateChats()
    group_scope = BotCommandScopeAllGroupChats()

    # English defaults cover clients whose language is outside our supported set.
    await bot.set_my_commands(_private_commands(i18n, "en"), scope=private_scope)
    await bot.delete_my_commands(scope=group_scope)

    for locale in SUPPORTED_LOCALES:
        await bot.set_my_commands(
            _private_commands(i18n, locale),
            scope=private_scope,
            language_code=locale,
        )
        await bot.delete_my_commands(
            scope=group_scope,
            language_code=locale,
        )


async def configure_bot_profile(bot: Bot, i18n: I18n) -> None:
    """Publish localized setup guidance before a user starts the bot."""

    await bot.set_my_description(description=i18n.t("en", "bot_description"))
    await bot.set_my_short_description(short_description=i18n.t("en", "bot_short_description"))
    for locale in SUPPORTED_LOCALES:
        await bot.set_my_description(
            description=i18n.t(locale, "bot_description"),
            language_code=locale,
        )
        await bot.set_my_short_description(
            short_description=i18n.t(locale, "bot_short_description"),
            language_code=locale,
        )
