"""Telegram permission and public-destination verification boundaries."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

from aiogram import Bot
from aiogram.enums import ChatMemberStatus, ChatType
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest, TelegramForbiddenError

from rejoinlater.domain import PublicDestination

_USERNAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]{4,31}$")
_NUMERIC_ID = re.compile(r"^-?[0-9]+$")


class InvalidPublicLocator(ValueError):
    """Input cannot be proven to identify a public Telegram group."""


@dataclass(frozen=True, slots=True)
class BotInviteAccess:
    """Three independently reportable conditions for Managed Return."""

    is_member: bool
    is_administrator: bool
    can_invite_users: bool

    @property
    def ready(self) -> bool:
        """Return whether all conditions required to create an invite are met."""

        return self.is_member and self.is_administrator and self.can_invite_users


def normalize_public_input(value: str) -> str | int:
    """Normalize supported public forms and reject invite/join-request links."""

    candidate = value.strip()
    if _NUMERIC_ID.fullmatch(candidate):
        return int(candidate)

    if candidate.startswith("@"):
        candidate = candidate[1:]
    elif "://" in candidate or candidate.lower().startswith(("t.me/", "telegram.me/")):
        with_scheme = candidate if "://" in candidate else f"https://{candidate}"
        parsed = urlparse(with_scheme)
        if parsed.scheme != "https" or parsed.netloc.lower() not in {"t.me", "telegram.me"}:
            raise InvalidPublicLocator
        parts = [part for part in parsed.path.split("/") if part]
        if parsed.query or parsed.fragment or len(parts) != 1:
            raise InvalidPublicLocator
        candidate = parts[0]

    if candidate.startswith("+") or candidate.lower() == "joinchat":
        raise InvalidPublicLocator
    if not _USERNAME.fullmatch(candidate):
        raise InvalidPublicLocator
    return f"@{candidate}"


def normalize_api_username(username: str) -> str:
    """Normalize Telegram's username field after applying the same syntax policy."""

    result = normalize_public_input(f"@{username}")
    if not isinstance(result, str):
        raise InvalidPublicLocator
    return result


async def resolve_public_input(bot: Bot, value: str) -> PublicDestination:
    """Resolve `/add` input, requiring a public group/supergroup username."""

    locator = normalize_public_input(value)
    try:
        chat = await bot.get_chat(locator)
    except TelegramAPIError as exc:
        # Do not wrap Telegram's exception text: it can contain the requested locator.
        raise InvalidPublicLocator from exc
    if chat.type not in {ChatType.GROUP, ChatType.SUPERGROUP} or not chat.username:
        raise InvalidPublicLocator
    return PublicDestination(
        chat_id=chat.id,
        username=normalize_api_username(chat.username),
        title=chat.title or "",
    )


async def validate_stored_destination(
    bot: Bot,
    stored_locator: str,
    original_chat_id: int,
) -> PublicDestination | None:
    """Fail closed unless a current public username is bound to the original chat ID.

    A username that resolves to a different ID is treated as reassignment and is never
    followed. Only failure to resolve the old username permits a best-effort lookup by
    the encrypted original ID, which may reveal a new username for that exact group.
    """

    try:
        old_chat = await bot.get_chat(stored_locator)
    except TelegramAPIError:
        old_chat = None

    if old_chat is not None:
        if old_chat.id != original_chat_id:
            return None
        if old_chat.type not in {ChatType.GROUP, ChatType.SUPERGROUP} or not old_chat.username:
            return None
        try:
            username = normalize_api_username(old_chat.username)
        except InvalidPublicLocator:
            return None
        return PublicDestination(old_chat.id, username, old_chat.title or "")

    try:
        current_chat = await bot.get_chat(original_chat_id)
    except TelegramAPIError:
        return None
    if (
        current_chat.id != original_chat_id
        or current_chat.type not in {ChatType.GROUP, ChatType.SUPERGROUP}
        or not current_chat.username
    ):
        return None
    try:
        username = normalize_api_username(current_chat.username)
    except InvalidPublicLocator:
        return None
    return PublicDestination(current_chat.id, username, current_chat.title or "")


async def inspect_bot_invite_access(bot: Bot, chat_id: int) -> BotInviteAccess | None:
    """Inspect Managed Return conditions without changing group membership or rights.

    ``None`` means Telegram could not complete the check because of a transient or
    otherwise unclassified API failure. A missing/inaccessible chat is reported as a
    non-membership result because bots cannot inspect a private group they are not in.
    """

    try:
        bot_user = await bot.get_me()
    except TelegramAPIError:
        return None

    try:
        member = await bot.get_chat_member(chat_id, bot_user.id)
    except (TelegramBadRequest, TelegramForbiddenError):
        return BotInviteAccess(False, False, False)
    except TelegramAPIError:
        return None

    is_member = member.status in {
        ChatMemberStatus.CREATOR,
        ChatMemberStatus.ADMINISTRATOR,
        ChatMemberStatus.MEMBER,
    } or (
        member.status == ChatMemberStatus.RESTRICTED and bool(getattr(member, "is_member", False))
    )
    is_administrator = member.status in {
        ChatMemberStatus.CREATOR,
        ChatMemberStatus.ADMINISTRATOR,
    }
    can_invite_users = is_administrator and bool(getattr(member, "can_invite_users", False))
    return BotInviteAccess(is_member, is_administrator, can_invite_users)


async def bot_can_invite(bot: Bot, chat_id: int) -> bool:
    """Perform a fresh least-privilege permission check at each sensitive operation."""

    access = await inspect_bot_invite_access(bot, chat_id)
    return access is not None and access.ready


async def user_is_still_member(bot: Bot, chat_id: int, user_id: int) -> bool | None:
    """Return membership when observable, otherwise `None` to trigger fallback logic."""

    try:
        member = await bot.get_chat_member(chat_id, user_id)
    except TelegramAPIError:
        return None
    if member.status in {
        ChatMemberStatus.CREATOR,
        ChatMemberStatus.ADMINISTRATOR,
        ChatMemberStatus.MEMBER,
    }:
        return True
    if member.status == ChatMemberStatus.RESTRICTED:
        return bool(getattr(member, "is_member", False))
    return False
