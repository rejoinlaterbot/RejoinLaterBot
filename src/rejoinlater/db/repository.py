"""Privacy-aware repositories and atomic aggregate accounting."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from rejoinlater.crypto import DataProtector
from rejoinlater.db.models import AggregateCounter, BreakRecord, UserPreference
from rejoinlater.domain import (
    DeliveryMethod,
    NewBreak,
    PauseReason,
    ReturnMode,
    Visibility,
)


@dataclass(frozen=True, slots=True)
class VisibleReturn:
    """Transient status data for one visible return, decrypted only in process memory."""

    record_id: uuid.UUID
    chat_id: int
    public_locator: str | None
    mode: ReturnMode
    return_at: datetime


@dataclass(frozen=True, slots=True)
class VisibleReturnPage:
    """Total visible count plus the bounded nearest rows shown by /status."""

    total_count: int
    items: list[VisibleReturn]


class Repository:
    """Database operations that consistently apply encryption and blind indexes."""

    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        protector: DataProtector,
    ) -> None:
        self.sessions = sessions
        self.protector = protector

    async def create_break(self, new: NewBreak) -> uuid.UUID:
        """Create or replace a pending return and increment analytics atomically."""

        record_id = uuid.uuid4()
        user_id_enc = self.protector.encrypt_id(new.user_id)
        user_lookup_hash = self.protector.lookup_hash(new.user_id)
        chat_id_enc = self.protector.encrypt_id(new.chat_id)
        chat_lookup_hash = self.protector.lookup_hash(new.chat_id)
        public_locator_enc = (
            self.protector.encrypt_text(new.public_locator) if new.public_locator else None
        )
        statement = insert(BreakRecord).values(
            id=record_id,
            mode=new.mode,
            visibility=new.visibility,
            user_id_enc=user_id_enc,
            user_lookup_hash=user_lookup_hash,
            chat_id_enc=chat_id_enc,
            chat_lookup_hash=chat_lookup_hash,
            public_locator_enc=public_locator_enc,
            return_at=new.return_at,
        )
        upsert_statement = statement.on_conflict_do_update(
            constraint="uq_break_user_chat",
            set_={
                "mode": new.mode,
                "visibility": new.visibility,
                "user_id_enc": user_id_enc,
                "chat_id_enc": chat_id_enc,
                "public_locator_enc": public_locator_enc,
                "return_at": new.return_at,
                "delivery_sent": False,
                "delivery_sent_at": None,
                "delivery_method": None,
                "delivery_paused": False,
                "pause_reason": None,
                "created_at": func.now(),
            },
        ).returning(BreakRecord.id)
        keys = (
            f"privacy_{new.visibility.value}",
            new.duration_bucket.value,
            f"mode_{new.mode.value}",
        )
        async with self.sessions() as session, session.begin():
            saved_id = (await session.execute(upsert_statement)).scalar_one()
            for key in keys:
                counter_statement = insert(AggregateCounter).values(key=key, value=1)
                await session.execute(
                    counter_statement.on_conflict_do_update(
                        index_elements=[AggregateCounter.key],
                        set_={"value": AggregateCounter.value + 1},
                    )
                )
        return saved_id

    async def preference(self, user_id: int) -> UserPreference | None:
        """Look up activation/settings through a keyed blind index."""

        lookup = self.protector.lookup_hash(user_id)
        async with self.sessions() as session:
            return await session.get(UserPreference, lookup)

    async def activate_user(self, user_id: int, language_code: str) -> None:
        """Create/update the minimal private-chat preference row."""

        lookup = self.protector.lookup_hash(user_id)
        statement = insert(UserPreference).values(
            user_lookup_hash=lookup,
            user_id_enc=self.protector.encrypt_id(user_id),
            language_code=language_code,
        )
        async with self.sessions() as session, session.begin():
            await session.execute(
                statement.on_conflict_do_update(
                    index_elements=[UserPreference.user_lookup_hash],
                    set_={"language_code": language_code, "updated_at": func.now()},
                )
            )

    async def visible_returns(self, user_id: int, limit: int = 5) -> VisibleReturnPage:
        """Return total visible count and the nearest not-yet-delivered rows."""

        predicates = (
            BreakRecord.user_lookup_hash == self.protector.lookup_hash(user_id),
            BreakRecord.visibility == Visibility.VISIBLE,
            BreakRecord.delivery_sent.is_(False),
        )
        count_statement = select(func.count()).select_from(BreakRecord).where(*predicates)
        records_statement = (
            select(BreakRecord).where(*predicates).order_by(BreakRecord.return_at).limit(limit)
        )
        async with self.sessions() as session:
            total_count = int((await session.execute(count_statement)).scalar_one())
            records = list((await session.scalars(records_statement)).all())
        return VisibleReturnPage(
            total_count=total_count,
            items=[
                VisibleReturn(
                    record_id=record.id,
                    chat_id=self.protector.decrypt_id(record.chat_id_enc),
                    public_locator=(
                        self.protector.decrypt_text(record.public_locator_enc)
                        if record.public_locator_enc is not None
                        else None
                    ),
                    mode=record.mode,
                    return_at=record.return_at,
                )
                for record in records
            ],
        )

    async def lock_visible_return(
        self,
        session: AsyncSession,
        user_id: int,
        record_id: uuid.UUID,
    ) -> BreakRecord | None:
        """Lock one owned visible row for an authenticated immediate return."""

        statement = (
            select(BreakRecord)
            .where(
                BreakRecord.id == record_id,
                BreakRecord.user_lookup_hash == self.protector.lookup_hash(user_id),
                BreakRecord.visibility == Visibility.VISIBLE,
                BreakRecord.delivery_sent.is_(False),
            )
            .with_for_update()
        )
        return (await session.scalars(statement)).one_or_none()

    async def delete_member_return(self, user_id: int, chat_id: int) -> int:
        """Hard-delete Managed Return state when Telegram reports an actual rejoin."""

        statement = delete(BreakRecord).where(
            BreakRecord.user_lookup_hash == self.protector.lookup_hash(user_id),
            BreakRecord.chat_lookup_hash == self.protector.lookup_hash(chat_id),
            BreakRecord.mode == ReturnMode.MANAGED,
        )
        async with self.sessions() as session, session.begin():
            result = await session.execute(statement)
            return int(result.rowcount)  # type: ignore[attr-defined]

    async def unpause_user(self, user_id: int) -> None:
        """Retry only delivery blocked by the user's private-chat state."""

        statement = (
            update(BreakRecord)
            .where(
                BreakRecord.user_lookup_hash == self.protector.lookup_hash(user_id),
                BreakRecord.pause_reason == PauseReason.BLOCKED,
            )
            .values(delivery_paused=False, pause_reason=None)
        )
        async with self.sessions() as session, session.begin():
            await session.execute(statement)

    async def unpause_chat(self, chat_id: int) -> None:
        """Retry unavailable Managed Returns only after a group permission event."""

        statement = (
            update(BreakRecord)
            .where(
                BreakRecord.chat_lookup_hash == self.protector.lookup_hash(chat_id),
                BreakRecord.pause_reason == PauseReason.UNAVAILABLE,
            )
            .values(delivery_paused=False, pause_reason=None)
        )
        async with self.sessions() as session, session.begin():
            await session.execute(statement)

    async def increment_fallback(self, session: AsyncSession) -> None:
        """Increment the unlinkable public-fallback counter in the delivery transaction."""

        statement = insert(AggregateCounter).values(key="fallback_public_used", value=1)
        await session.execute(
            statement.on_conflict_do_update(
                index_elements=[AggregateCounter.key],
                set_={"value": AggregateCounter.value + 1},
            )
        )

    async def hard_delete_public_deliveries(self) -> int:
        """Finish the crash-safe mark-then-delete protocol in a new transaction."""

        statement = delete(BreakRecord).where(
            BreakRecord.delivery_sent.is_(True),
            BreakRecord.delivery_method == DeliveryMethod.PUBLIC_LINK,
        )
        async with self.sessions() as session, session.begin():
            result = await session.execute(statement)
            return int(result.rowcount)  # type: ignore[attr-defined]

    async def rearm_expired_managed_invites(self, ttl_hours: int) -> int:
        """Make an unused expired invite eligible for a fresh single-use delivery."""

        statement = (
            update(BreakRecord)
            .where(
                BreakRecord.delivery_sent.is_(True),
                BreakRecord.delivery_method == DeliveryMethod.MANAGED_INVITE,
                BreakRecord.delivery_sent_at <= datetime.now(UTC) - timedelta(hours=ttl_hours),
            )
            .values(delivery_sent=False, delivery_sent_at=None, delivery_method=None)
        )
        async with self.sessions() as session, session.begin():
            result = await session.execute(statement)
            return int(result.rowcount)  # type: ignore[attr-defined]

    async def due_records(
        self,
        session: AsyncSession,
        batch_size: int,
        user_id: int | None = None,
    ) -> list[BreakRecord]:
        """Lock one bounded due batch; competing workers skip already locked rows."""

        statement = (
            select(BreakRecord)
            .where(
                BreakRecord.return_at <= datetime.now(UTC),
                BreakRecord.delivery_sent.is_(False),
                BreakRecord.delivery_paused.is_(False),
            )
            .order_by(BreakRecord.return_at)
            .limit(batch_size)
            .with_for_update(skip_locked=True)
        )
        if user_id is not None:
            statement = statement.where(
                BreakRecord.user_lookup_hash == self.protector.lookup_hash(user_id)
            )
        return list((await session.scalars(statement)).all())
