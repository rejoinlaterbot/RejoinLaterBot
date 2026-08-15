"""Shared Hidden/Visible, relative duration, and confirmation wizard."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from rejoinlater.config import Settings
from rejoinlater.db.repository import Repository
from rejoinlater.domain import DurationBucket, NewBreak, ReturnMode, Visibility
from rejoinlater.i18n import I18n
from rejoinlater.telegram.helpers import locale_for
from rejoinlater.telegram.keyboards import (
    confirmation_keyboard,
    duration_keyboard,
    visibility_keyboard,
)
from rejoinlater.telegram.states import ReturnWizard

logger = logging.getLogger(__name__)
router = Router(name="wizard")

_DURATIONS: dict[str, tuple[timedelta, DurationBucket]] = {
    "1h": (timedelta(hours=1), DurationBucket.H1),
    "6h": (timedelta(hours=6), DurationBucket.H6),
    "12h": (timedelta(hours=12), DurationBucket.H12),
    "1d": (timedelta(days=1), DurationBucket.D1),
    "3d": (timedelta(days=3), DurationBucket.D3),
    "1w": (timedelta(weeks=1), DurationBucket.W1),
    "2w": (timedelta(weeks=2), DurationBucket.W2),
    "30d": (timedelta(days=30), DurationBucket.D30),
}


async def begin_wizard(message: Message, state: FSMContext, locale: str, i18n: I18n) -> None:
    """Start both modes with Hidden preselected as the privacy-preserving default."""

    await state.update_data(visibility=Visibility.HIDDEN.value)
    await state.set_state(ReturnWizard.visibility)
    text = "\n\n".join(
        (
            i18n.t(locale, "how_appear"),
            "\n".join(
                (
                    i18n.t(locale, "hidden_option"),
                    i18n.t(locale, "hidden_description"),
                )
            ),
            "\n".join(
                (
                    i18n.t(locale, "visible_option"),
                    i18n.t(locale, "visible_description"),
                )
            ),
        )
    )
    await message.answer(text, reply_markup=visibility_keyboard(i18n, locale))


@router.callback_query(ReturnWizard.visibility, F.data.startswith("vis:"))
async def choose_visibility(
    callback: CallbackQuery,
    state: FSMContext,
    repository: Repository,
    i18n: I18n,
) -> None:
    """Record only the selected privacy class in transient state."""

    value = (callback.data or "").partition(":")[2]
    if value not in {Visibility.HIDDEN.value, Visibility.VISIBLE.value}:
        await callback.answer()
        return
    locale = await locale_for(callback.from_user, repository)
    await state.update_data(visibility=value)
    await state.set_state(ReturnWizard.duration)
    if isinstance(callback.message, Message):
        await callback.message.edit_text(
            i18n.t(locale, "choose_duration"),
            reply_markup=duration_keyboard(i18n, locale),
        )
    await callback.answer()


@router.callback_query(ReturnWizard.duration, F.data.startswith("dur:"))
async def choose_duration(
    callback: CallbackQuery,
    state: FSMContext,
    repository: Repository,
    i18n: I18n,
    settings: Settings,
) -> None:
    """Choose a bucket; exact custom days never enter analytics."""

    value = (callback.data or "").partition(":")[2]
    locale = await locale_for(callback.from_user, repository)
    if value == "custom":
        await state.set_state(ReturnWizard.custom_days)
        if isinstance(callback.message, Message):
            await callback.message.edit_text(
                i18n.t(locale, "custom_days_prompt", max_days=settings.max_custom_days)
            )
        await callback.answer()
        return
    choice = _DURATIONS.get(value)
    if choice is None:
        await callback.answer()
        return
    duration, bucket = choice
    await state.update_data(
        return_at=(datetime.now(UTC) + duration).isoformat(),
        duration_bucket=bucket.value,
        duration_key=value,
    )
    if isinstance(callback.message, Message):
        await _show_confirmation(callback.message, state, i18n, locale)
    await callback.answer()


@router.message(ReturnWizard.custom_days)
async def custom_duration(
    message: Message,
    state: FSMContext,
    repository: Repository,
    i18n: I18n,
    settings: Settings,
) -> None:
    """Validate and schedule a custom whole number of days."""

    if message.from_user is None:
        return
    locale = await locale_for(message.from_user, repository)
    try:
        days = int(message.text or "")
    except ValueError:
        days = 0
    if not 1 <= days <= settings.max_custom_days:
        await message.answer(
            i18n.t(locale, "custom_days_invalid", max_days=settings.max_custom_days)
        )
        return
    await state.update_data(
        return_at=(datetime.now(UTC) + timedelta(days=days)).isoformat(),
        duration_bucket=DurationBucket.CUSTOM.value,
        custom_days=days,
    )
    await _show_confirmation(message, state, i18n, locale)


async def _show_confirmation(
    message: Message,
    state: FSMContext,
    i18n: I18n,
    locale: str,
) -> None:
    """Show only the relative duration, never a timezone, title, or public locator."""

    data = await state.get_data()
    mode = ReturnMode(str(data["mode"]))
    visibility = Visibility(str(data["visibility"]))
    duration = (
        i18n.t(locale, "duration_custom_days", count=int(data["custom_days"]))
        if "custom_days" in data
        else i18n.t(locale, f"duration_{data['duration_key']}")
    )
    text = i18n.t(
        locale,
        "confirmation",
        visibility=i18n.t(locale, f"visibility_{visibility.value}"),
        mode=i18n.t(locale, f"mode_{mode.value}"),
        duration=duration,
    )
    await state.set_state(ReturnWizard.confirmation)
    await message.answer(text, reply_markup=confirmation_keyboard(i18n, locale))


@router.callback_query(ReturnWizard.confirmation, F.data == "wizard:confirm")
async def confirm_return(
    callback: CallbackQuery,
    state: FSMContext,
    repository: Repository,
    i18n: I18n,
) -> None:
    """Encrypt and atomically persist the confirmed return plus aggregate counters."""

    locale = await locale_for(callback.from_user, repository)
    data: dict[str, Any] = await state.get_data()
    mode = ReturnMode(str(data["mode"]))
    new = NewBreak(
        user_id=callback.from_user.id,
        chat_id=int(data["chat_id"]),
        public_locator=(str(data["public_locator"]) if data.get("public_locator") else None),
        mode=mode,
        visibility=Visibility(str(data["visibility"])),
        return_at=datetime.fromisoformat(str(data["return_at"])),
        duration_bucket=DurationBucket(str(data["duration_bucket"])),
    )
    record_id = await repository.create_break(new)
    logger.info("event=break_saved record_uuid=%s", record_id)
    text = i18n.t(locale, f"scheduled_{mode.value}")
    await state.clear()
    if isinstance(callback.message, Message):
        await callback.message.edit_text(text)
    await callback.answer()


@router.callback_query(F.data == "wizard:cancel")
async def cancel_return(
    callback: CallbackQuery,
    state: FSMContext,
    repository: Repository,
    i18n: I18n,
) -> None:
    """Discard all transient identifiers and choices."""

    locale = await locale_for(callback.from_user, repository)
    await state.clear()
    if isinstance(callback.message, Message):
        await callback.message.edit_text(i18n.t(locale, "cancelled"))
    await callback.answer()
