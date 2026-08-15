"""Small domain types shared by transport, persistence, and services."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class ReturnMode(StrEnum):
    """How access will be restored."""

    MANAGED = "managed"
    PUBLIC = "public"


class Visibility(StrEnum):
    """Whether a pending return may contribute to private status output."""

    HIDDEN = "hidden"
    VISIBLE = "visible"


class PauseReason(StrEnum):
    """Why scheduler retries must wait for an external Telegram event."""

    BLOCKED = "blocked"
    UNAVAILABLE = "unavailable"


class DeliveryMethod(StrEnum):
    """The successfully delivered access mechanism."""

    MANAGED_INVITE = "managed_invite"
    PUBLIC_LINK = "public_link"


class DurationBucket(StrEnum):
    """Privacy-safe analytics buckets; custom values never store the chosen days."""

    H1 = "duration_1h"
    H6 = "duration_6h"
    H12 = "duration_12h"
    D1 = "duration_1d"
    D3 = "duration_3d"
    W1 = "duration_1w"
    W2 = "duration_2w"
    D30 = "duration_30d"
    CUSTOM = "duration_custom"


@dataclass(frozen=True, slots=True)
class NewBreak:
    """Plaintext creation input that must exist only in process memory."""

    user_id: int
    chat_id: int
    public_locator: str | None
    mode: ReturnMode
    visibility: Visibility
    return_at: datetime
    duration_bucket: DurationBucket


@dataclass(frozen=True, slots=True)
class PublicDestination:
    """A current Telegram destination verified against the original chat ID."""

    chat_id: int
    username: str
    title: str
