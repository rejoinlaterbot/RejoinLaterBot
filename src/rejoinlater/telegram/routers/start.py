"""Private activation, About information, and language selection."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from rejoinlater.db.repository import Repository
from rejoinlater.i18n import SUPPORTED_LOCALES, I18n
from rejoinlater.services.delivery import DeliveryWorker
from rejoinlater.telegram.deduplication import StartDeduplicator
from rejoinlater.telegram.helpers import locale_for
from rejoinlater.telegram.keyboards import home_keyboard, language_keyboard

logger = logging.getLogger(__name__)
router = Router(name="start")


async def _show_about(message: Message, locale: str, i18n: I18n) -> None:
    """Show usage and privacy instructions independently from language selection."""

    text = "\n\n".join(
        (
            i18n.t(locale, "welcome"),
            i18n.t(locale, "privacy"),
            i18n.t(locale, "blocked_info"),
            i18n.t(locale, "open_source"),
        )
    )
    await message.answer(text, reply_markup=home_keyboard(i18n, locale))


@router.message(CommandStart(), F.chat.type == ChatType.PRIVATE)
async def start_private(
    message: Message,
    state: FSMContext,
    repository: Repository,
    i18n: I18n,
    worker: DeliveryWorker,
    start_deduplicator: StartDeduplicator,
) -> None:
    """Activate private delivery and show the private About screen."""

    if message.from_user is None:
        return
    if not await start_deduplicator.accept(message.from_user.id):
        logger.info("event=duplicate_start_ignored")
        return
    await state.clear()
    locale = await locale_for(message.from_user, repository)
    # Telegram reserves /start for initial activation. It is intentionally absent
    # from our menu because About and Language are independent user-facing commands.
    await repository.activate_user(message.from_user.id, locale)
    await repository.unpause_user(message.from_user.id)
    worker.wake()

    await _show_about(message, locale, i18n)


@router.message(Command("about"), F.chat.type == ChatType.PRIVATE)
async def about_private(
    message: Message,
    state: FSMContext,
    repository: Repository,
    i18n: I18n,
) -> None:
    """Show the instruction without opening or changing language settings."""

    if message.from_user is None:
        return
    await state.clear()
    locale = await locale_for(message.from_user, repository)
    await repository.activate_user(message.from_user.id, locale)
    await _show_about(message, locale, i18n)


@router.message(Command("language"), F.chat.type == ChatType.PRIVATE)
async def language_private(
    message: Message,
    state: FSMContext,
    repository: Repository,
    i18n: I18n,
) -> None:
    """Open only the language selector."""

    if message.from_user is None:
        return
    await state.clear()
    locale = await locale_for(message.from_user, repository)
    await message.answer(
        i18n.t(locale, "choose_language"),
        reply_markup=language_keyboard(i18n),
    )


@router.callback_query(F.data.startswith("lang:"))
async def select_language(
    callback: CallbackQuery,
    state: FSMContext,
    repository: Repository,
    i18n: I18n,
    worker: DeliveryWorker,
) -> None:
    """Persist only the chosen locale and encrypted Telegram user ID."""

    locale = (callback.data or "").partition(":")[2]
    if locale not in SUPPORTED_LOCALES:
        await callback.answer()
        return
    await repository.activate_user(callback.from_user.id, locale)
    await repository.unpause_user(callback.from_user.id)
    worker.wake()
    await state.clear()
    if isinstance(callback.message, Message):
        await callback.message.edit_text(
            i18n.t(
                locale,
                "language_selected",
                language=i18n.t(locale, "language_name"),
            )
        )
    await callback.answer()
