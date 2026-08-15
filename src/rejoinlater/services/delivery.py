"""Database-driven delivery with identity-safe fallback and hard deletion."""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession

from rejoinlater.config import Settings
from rejoinlater.crypto import DataProtector
from rejoinlater.db.models import BreakRecord
from rejoinlater.db.repository import Repository
from rejoinlater.domain import DeliveryMethod, PauseReason, ReturnMode
from rejoinlater.i18n import I18n
from rejoinlater.services.telegram_access import (
    bot_can_invite,
    user_is_still_member,
    validate_stored_destination,
)
from rejoinlater.services.text import truncate_graphemes

logger = logging.getLogger(__name__)


class DeliveryWorker:
    """Process due rows in bounded locked batches; no per-return timers exist in RAM."""

    def __init__(
        self,
        bot: Bot,
        repository: Repository,
        protector: DataProtector,
        i18n: I18n,
        settings: Settings,
    ) -> None:
        self.bot = bot
        self.repository = repository
        self.protector = protector
        self.i18n = i18n
        self.settings = settings
        self._wake = asyncio.Event()

    def wake(self) -> None:
        """Prompt the shared worker after an unblock/permission event."""

        self._wake.set()

    async def run(self) -> None:
        """Poll PostgreSQL at a fixed interval and survive recoverable API errors."""

        while True:
            try:
                await self.process_batch()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error("event=scheduler_error error_type=%s", type(exc).__name__)
            try:
                await asyncio.wait_for(
                    self._wake.wait(), timeout=self.settings.scheduler_interval_seconds
                )
                self._wake.clear()
            except TimeoutError:
                pass

    async def process_batch(self, user_id: int | None = None) -> None:
        """Mark public deliveries, commit, then hard-delete in a separate transaction."""

        # This first cleanup completes records marked immediately before an old crash.
        await self.repository.hard_delete_public_deliveries()
        # Expiring invite links must not make a still-pending Managed Return unreachable.
        await self.repository.rearm_expired_managed_invites(self.settings.invite_ttl_hours)
        async with self.repository.sessions() as session, session.begin():
            records = await self.repository.due_records(
                session, self.settings.scheduler_batch_size, user_id
            )
            for record in records:
                try:
                    async with session.begin_nested():
                        await self._deliver_locked(session, record)
                except Exception as exc:
                    logger.error(
                        "event=delivery_error record_uuid=%s error_type=%s",
                        record.id,
                        type(exc).__name__,
                    )
        # Public Reminder/Fallback requires a distinct committed mark before deletion.
        deleted = await self.repository.hard_delete_public_deliveries()
        if deleted:
            logger.info("event=return_deleted count=%d", deleted)

    async def deliver_now(self, record_id: uuid.UUID, user_id: int) -> bool:
        """Deliver and hard-delete one owned Visible return selected from /status."""

        async with self.repository.sessions() as session, session.begin():
            record = await self.repository.lock_visible_return(session, user_id, record_id)
            if record is None:
                return False
            return await self._deliver_locked(session, record, delete_after_delivery=True)

    async def _deliver_locked(
        self,
        session: AsyncSession,
        record: BreakRecord,
        *,
        delete_after_delivery: bool = False,
    ) -> bool:
        """Choose Managed invite, verified public fallback, or fail-closed notice."""

        user_id = self.protector.decrypt_id(record.user_id_enc)
        chat_id = self.protector.decrypt_id(record.chat_id_enc)
        locale = await self._locale(user_id)

        if record.mode == ReturnMode.MANAGED and await bot_can_invite(self.bot, chat_id):
            membership = await user_is_still_member(self.bot, chat_id, user_id)
            if membership is True:
                await session.delete(record)
                logger.info("event=return_deleted record_uuid=%s", record.id)
                return True
            if membership is False and await self._send_managed_invite(
                record, user_id, chat_id, locale
            ):
                await self._finish_delivery(
                    session,
                    record,
                    DeliveryMethod.MANAGED_INVITE,
                    delete_after_delivery,
                )
                return True

        if record.public_locator_enc is not None:
            stored_locator = self.protector.decrypt_text(record.public_locator_enc)
            destination = await validate_stored_destination(self.bot, stored_locator, chat_id)
            if destination is not None:
                sent = await self._send_public(record, user_id, destination, locale)
                if sent:
                    if record.mode == ReturnMode.MANAGED:
                        await self.repository.increment_fallback(session)
                        logger.info("event=public_fallback_used record_uuid=%s", record.id)
                    await self._finish_delivery(
                        session,
                        record,
                        DeliveryMethod.PUBLIC_LINK,
                        delete_after_delivery,
                    )
                    return True
                return False
            return await self._public_unavailable(session, record, user_id, locale)

        await self._managed_unavailable(record, user_id, locale)
        return False

    async def _finish_delivery(
        self,
        session: AsyncSession,
        record: BreakRecord,
        method: DeliveryMethod,
        delete_after_delivery: bool,
    ) -> None:
        """Persist normal delivery state or complete an explicit immediate return."""

        if delete_after_delivery:
            await session.delete(record)
            logger.info("event=return_completed_now record_uuid=%s", record.id)
            return
        record.delivery_sent = True
        record.delivery_sent_at = datetime.now(UTC)
        record.delivery_method = method
        logger.info("event=return_delivered record_uuid=%s", record.id)

    async def _locale(self, user_id: int) -> str:
        preference = await self.repository.preference(user_id)
        return preference.language_code if preference else "en"

    async def _send_managed_invite(
        self,
        record: BreakRecord,
        user_id: int,
        chat_id: int,
        locale: str,
    ) -> bool:
        """Create a single-use link only after fresh permission/membership checks."""

        try:
            invite = await self.bot.create_chat_invite_link(
                chat_id,
                member_limit=1,
                expire_date=datetime.now(UTC) + timedelta(hours=self.settings.invite_ttl_hours),
            )
            chat = await self.bot.get_chat(chat_id)
            label = truncate_graphemes(chat.title or self.i18n.t(locale, "rejoin_group"))
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text=label, url=invite.invite_link)]]
            )
            await self.bot.send_message(
                user_id,
                self.i18n.t(locale, "return_ready", label=label),
                reply_markup=keyboard,
            )
            return True
        except TelegramForbiddenError:
            record.delivery_paused = True
            record.pause_reason = PauseReason.BLOCKED
            return False
        except TelegramAPIError as exc:
            logger.warning("event=telegram_error error_type=%s", type(exc).__name__)
            return False

    async def _send_public(
        self,
        record: BreakRecord,
        user_id: int,
        destination: object,
        locale: str,
    ) -> bool:
        """Send a public URL only from the validator's current, ID-bound result."""

        # Local import keeps the destination type explicit without persisting it anywhere.
        from rejoinlater.domain import PublicDestination

        if not isinstance(destination, PublicDestination):
            raise TypeError("validated destination required")
        label = truncate_graphemes(destination.title or self.i18n.t(locale, "rejoin_group"))
        url = f"https://t.me/{destination.username.removeprefix('@')}"
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text=label, url=url)]]
        )
        try:
            await self.bot.send_message(
                user_id,
                self.i18n.t(locale, "return_ready", label=label),
                reply_markup=keyboard,
            )
            return True
        except TelegramForbiddenError:
            record.delivery_paused = True
            record.pause_reason = PauseReason.BLOCKED
            return False
        except TelegramAPIError as exc:
            logger.warning("event=telegram_error error_type=%s", type(exc).__name__)
            return False

    async def _public_unavailable(
        self,
        session: AsyncSession,
        record: BreakRecord,
        user_id: int,
        locale: str,
    ) -> bool:
        try:
            await self.bot.send_message(user_id, self.i18n.t(locale, "public_unavailable"))
        except TelegramForbiddenError:
            record.delivery_paused = True
            record.pause_reason = PauseReason.BLOCKED
            return False
        except TelegramAPIError as exc:
            logger.warning("event=telegram_error error_type=%s", type(exc).__name__)
            return False
        if record.mode == ReturnMode.PUBLIC:
            # There is no safe destination and no membership capability to wait for.
            await session.delete(record)
            logger.info("event=return_deleted record_uuid=%s", record.id)
            return True
        else:
            # Managed access may become available again after permissions are restored.
            record.delivery_paused = True
            record.pause_reason = PauseReason.UNAVAILABLE
            return False

    async def _managed_unavailable(
        self,
        record: BreakRecord,
        user_id: int,
        locale: str,
    ) -> None:
        try:
            await self.bot.send_message(user_id, self.i18n.t(locale, "managed_unavailable"))
        except TelegramForbiddenError:
            record.delivery_paused = True
            record.pause_reason = PauseReason.BLOCKED
            return
        except TelegramAPIError as exc:
            logger.warning("event=telegram_error error_type=%s", type(exc).__name__)
            return
        record.delivery_paused = True
        record.pause_reason = PauseReason.UNAVAILABLE
