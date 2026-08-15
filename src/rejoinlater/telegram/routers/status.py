"""Private visible-only return list and authenticated immediate completion."""

from __future__ import annotations

import logging
import math
import uuid
from datetime import UTC, datetime

from aiogram import Bot, F, Router
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from rejoinlater.db.repository import Repository, VisibleReturn
from rejoinlater.i18n import I18n
from rejoinlater.services.delivery import DeliveryWorker
from rejoinlater.services.telegram_access import validate_stored_destination
from rejoinlater.services.text import truncate_graphemes
from rejoinlater.telegram.helpers import locale_for

logger = logging.getLogger(__name__)
router = Router(name="status")


def _remaining(return_at: datetime, i18n: I18n, locale: str) -> str:
    """Render the existing privacy-safe relative hour/day buckets."""

    seconds = max(0, (return_at - datetime.now(UTC)).total_seconds())
    hours = max(1, math.ceil(seconds / 3600))
    if hours < 48:
        return i18n.t(locale, "remaining_hours", count=hours)
    return i18n.t(locale, "remaining_days", count=math.ceil(hours / 24))


async def _current_group_title(
    item: VisibleReturn,
    bot: Bot,
    i18n: I18n,
    locale: str,
) -> str:
    """Resolve a current title without storing it or trusting a reassigned username."""

    if item.public_locator is not None:
        destination = await validate_stored_destination(
            bot,
            item.public_locator,
            item.chat_id,
        )
        if destination is not None and destination.title:
            return truncate_graphemes(destination.title)

    try:
        chat = await bot.get_chat(item.chat_id)
    except TelegramAPIError:
        chat = None
    if chat is not None and chat.id == item.chat_id and chat.title:
        return truncate_graphemes(chat.title)
    return i18n.t(locale, f"mode_{item.mode.value}")


async def _status_view(
    user_id: int,
    repository: Repository,
    i18n: I18n,
    locale: str,
    bot: Bot,
) -> tuple[str, InlineKeyboardMarkup | None]:
    """Build at most five visible entries and their one-to-one action buttons."""

    page = await repository.visible_returns(user_id, limit=5)
    if not page.items:
        return i18n.t(locale, "status_empty"), None

    entries: list[str] = []
    buttons: list[list[InlineKeyboardButton]] = []
    for index, item in enumerate(page.items, start=1):
        title = await _current_group_title(item, bot, i18n, locale)
        entries.append(
            i18n.t(
                locale,
                "status_active",
                count=title,
                title=f"{index}. {title}",
                remaining=_remaining(item.return_at, i18n, locale),
            )
        )
        buttons.append(
            [
                InlineKeyboardButton(
                    text=f"{index}. {i18n.t(locale, 'status_return_now')}",
                    callback_data=f"status:return:{item.record_id}",
                )
            ]
        )
    body = "\n\n".join(entries)
    text = f"{i18n.t(locale, 'status_header', count=page.total_count)}\n\n{body}"
    return text, InlineKeyboardMarkup(inline_keyboard=buttons)


@router.message(Command("status"), F.chat.type == ChatType.PRIVATE)
async def status_private(
    message: Message,
    repository: Repository,
    i18n: I18n,
    bot: Bot,
) -> None:
    """Show only the five nearest Visible returns; Hidden rows are never queried."""

    if message.from_user is None:
        return
    locale = await locale_for(message.from_user, repository)
    text, markup = await _status_view(message.from_user.id, repository, i18n, locale, bot)
    await message.answer(text, reply_markup=markup)


@router.callback_query(F.data.startswith("status:return:"))
async def return_now(
    callback: CallbackQuery,
    repository: Repository,
    i18n: I18n,
    bot: Bot,
    worker: DeliveryWorker,
) -> None:
    """Deliver one owned Visible return immediately and remove it after completion."""

    locale = await locale_for(callback.from_user, repository)
    try:
        record_id = uuid.UUID((callback.data or "").removeprefix("status:return:"))
    except ValueError:
        await callback.answer()
        return

    try:
        completed = await worker.deliver_now(record_id, callback.from_user.id)
    except Exception as exc:
        logger.error("event=immediate_return_error error_type=%s", type(exc).__name__)
        await callback.answer(i18n.t(locale, "generic_error"), show_alert=True)
        return

    if not completed:
        await callback.answer(i18n.t(locale, "generic_error"), show_alert=True)
        return

    if isinstance(callback.message, Message):
        text, markup = await _status_view(
            callback.from_user.id,
            repository,
            i18n,
            locale,
            bot,
        )
        await callback.message.edit_text(text, reply_markup=markup)
    await callback.answer()
