"""Hard deletion on rejoin and targeted retries after external state changes."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.enums import ChatMemberStatus, ChatType
from aiogram.types import ChatMemberUpdated

from rejoinlater.db.repository import Repository
from rejoinlater.services.delivery import DeliveryWorker

router = Router(name="membership")


@router.chat_member()
async def member_changed(event: ChatMemberUpdated, repository: Repository) -> None:
    """Delete Managed state immediately when Telegram reports a real/early return."""

    new = event.new_chat_member
    is_present = new.status in {
        ChatMemberStatus.CREATOR,
        ChatMemberStatus.ADMINISTRATOR,
        ChatMemberStatus.MEMBER,
    } or (new.status == ChatMemberStatus.RESTRICTED and bool(getattr(new, "is_member", False)))
    if is_present:
        await repository.delete_member_return(new.user.id, event.chat.id)


@router.my_chat_member(F.chat.type == ChatType.PRIVATE)
async def private_bot_status(
    event: ChatMemberUpdated, repository: Repository, worker: DeliveryWorker
) -> None:
    """Unpause blocked deliveries when Telegram reports that the bot is usable again."""

    if event.new_chat_member.status == ChatMemberStatus.MEMBER:
        await repository.unpause_user(event.from_user.id)
        worker.wake()


@router.my_chat_member(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}))
async def group_bot_status(
    event: ChatMemberUpdated, repository: Repository, worker: DeliveryWorker
) -> None:
    """Retry unavailable rows after Invite Users permission is restored."""

    new = event.new_chat_member
    if new.status == ChatMemberStatus.ADMINISTRATOR and bool(
        getattr(new, "can_invite_users", False)
    ):
        await repository.unpause_chat(event.chat.id)
        worker.wake()
