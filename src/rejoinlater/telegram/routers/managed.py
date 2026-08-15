"""Unified private group selection for managed invites or public links."""

from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    ChatShared,
    KeyboardButton,
    KeyboardButtonRequestChat,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    User,
)

from rejoinlater.db.repository import Repository
from rejoinlater.domain import PublicDestination, ReturnMode
from rejoinlater.i18n import I18n
from rejoinlater.services.telegram_access import (
    BotInviteAccess,
    InvalidPublicLocator,
    inspect_bot_invite_access,
    normalize_api_username,
    resolve_public_input,
)
from rejoinlater.telegram.helpers import locale_for
from rejoinlater.telegram.routers.wizard import begin_wizard

router = Router(name="managed")

# The request ID only correlates the private service message with this keyboard. It
# identifies neither a Telegram user nor a chat and therefore needs no persistence.
MANAGED_CHAT_REQUEST_ID = 742_901


def managed_chat_keyboard(i18n: I18n, locale: str) -> ReplyKeyboardMarkup:
    """Request a group ID/username without asking Telegram to add or promote the bot."""

    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(
                    text=i18n.t(locale, "choose_managed_group"),
                    request_chat=KeyboardButtonRequestChat(
                        request_id=MANAGED_CHAT_REQUEST_ID,
                        chat_is_channel=False,
                        # Deliberately omit bot_is_member and administrator-right
                        # criteria: Telegram clients may satisfy those criteria by
                        # adding/promoting the bot during selection. We only need the
                        # ID/public username and perform read-only checks afterward.
                        request_username=True,
                    ),
                )
            ]
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def _managed_checklist(i18n: I18n, locale: str, access: BotInviteAccess) -> str:
    """Render all Managed Return prerequisites without exposing chat metadata."""

    return i18n.t(
        locale,
        "managed_checklist",
        member="✅" if access.is_member else "❌",
        administrator="✅" if access.is_administrator else "❌",
        invite="✅" if access.can_invite_users else "❌",
    )


def _managed_failure_reason(access: BotInviteAccess) -> str:
    """Return the first failed prerequisite in dependency order."""

    if not access.is_member:
        return "managed_failure_not_member"
    if not access.is_administrator:
        return "managed_failure_not_admin"
    return "managed_failure_no_invite"


async def _public_destination_for_selection(
    bot: Bot,
    shared: ChatShared,
    access: BotInviteAccess,
) -> PublicDestination | None:
    """Return an ID-bound public destination, or ``None`` for a private group."""

    username = shared.username
    if username is None and access.is_member:
        try:
            chat = await bot.get_chat(shared.chat_id)
        except TelegramAPIError as exc:
            raise InvalidPublicLocator from exc
        if chat.type not in {ChatType.GROUP, ChatType.SUPERGROUP}:
            raise InvalidPublicLocator
        username = chat.username
    if username is None:
        return None

    destination = await resolve_public_input(bot, f"@{username}")
    if destination.chat_id != shared.chat_id:
        raise InvalidPublicLocator
    return destination


async def _start_group_picker(
    message: Message,
    actor: User,
    state: FSMContext,
    repository: Repository,
    i18n: I18n,
) -> None:
    """Open the system picker without sending anything to a Telegram group."""

    locale = await locale_for(actor, repository)
    await repository.activate_user(actor.id, locale)
    await state.clear()
    await message.answer(
        i18n.t(locale, "managed_picker_prompt"),
        reply_markup=managed_chat_keyboard(i18n, locale),
    )


@router.message(Command("add"), F.chat.type == ChatType.PRIVATE)
async def add_command(
    message: Message,
    state: FSMContext,
    repository: Repository,
    i18n: I18n,
) -> None:
    """Open the unified group picker from the private command menu."""

    if message.from_user:
        await _start_group_picker(message, message.from_user, state, repository, i18n)


@router.callback_query(F.data.in_({"group:add", "public:add", "managed:add"}))
async def add_button(
    callback: CallbackQuery,
    state: FSMContext,
    repository: Repository,
    i18n: I18n,
) -> None:
    """Open the picker from current or legacy private About buttons."""

    if isinstance(callback.message, Message):
        await _start_group_picker(
            callback.message,
            callback.from_user,
            state,
            repository,
            i18n,
        )
    await callback.answer()


@router.message(F.chat.type == ChatType.PRIVATE, F.chat_shared)
async def managed_chat_selected(
    message: Message,
    state: FSMContext,
    repository: Repository,
    i18n: I18n,
    bot: Bot,
) -> None:
    """Choose a managed invite, public-link fallback, or fail closed."""

    if message.from_user is None or message.chat_shared is None:
        return
    locale = await locale_for(message.from_user, repository)
    shared = message.chat_shared
    if shared.request_id != MANAGED_CHAT_REQUEST_ID:
        return

    access = await inspect_bot_invite_access(bot, shared.chat_id)
    if access is None:
        # Telegram exception text may include chat metadata, so it is not logged.
        await message.answer(
            i18n.t(locale, "managed_group_unavailable"),
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    checklist = _managed_checklist(i18n, locale, access)

    if access.ready:
        try:
            chat = await bot.get_chat(shared.chat_id)
            if chat.type not in {ChatType.GROUP, ChatType.SUPERGROUP}:
                raise ValueError
            public_locator = normalize_api_username(chat.username) if chat.username else None
        except (TelegramAPIError, ValueError):
            # Telegram exception text may include chat metadata, so it is not logged.
            await message.answer(
                i18n.t(locale, "managed_group_unavailable"),
                reply_markup=ReplyKeyboardRemove(),
            )
            return

        await state.update_data(
            mode=ReturnMode.MANAGED.value,
            chat_id=chat.id,
            public_locator=public_locator,
        )
        await message.answer(
            f"{checklist}\n\n{i18n.t(locale, 'managed_group_selected')}",
            reply_markup=ReplyKeyboardRemove(),
        )
        await begin_wizard(message, state, locale, i18n)
        return

    failure = "\n\n".join(
        (
            checklist,
            "\n".join(
                (
                    i18n.t(locale, "managed_check_failed"),
                    i18n.t(locale, _managed_failure_reason(access)),
                )
            ),
        )
    )
    try:
        destination = await _public_destination_for_selection(bot, shared, access)
    except InvalidPublicLocator:
        await message.answer(
            f"{failure}\n\n{i18n.t(locale, 'invalid_public_locator')}",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    if destination is None:
        await message.answer(
            f"{failure}\n\n{i18n.t(locale, 'permissions_missing')}",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    await state.update_data(
        mode=ReturnMode.PUBLIC.value,
        chat_id=destination.chat_id,
        public_locator=destination.username,
    )
    await message.answer(
        f"{failure}\n\n{i18n.t(locale, 'prompt_public_locator')}",
        reply_markup=ReplyKeyboardRemove(),
    )
    await begin_wizard(message, state, locale, i18n)
