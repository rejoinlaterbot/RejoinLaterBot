"""Transport helpers for locale selection without storing Telegram profile fields."""

from __future__ import annotations

from aiogram.types import User

from rejoinlater.db.repository import Repository
from rejoinlater.i18n import SUPPORTED_LOCALES


async def locale_for(user: User, repository: Repository) -> str:
    """Prefer explicit settings; use Telegram language transiently as a fallback."""

    preference = await repository.preference(user.id)
    if preference:
        return preference.language_code
    candidate = (user.language_code or "en").split("-")[0]
    return candidate if candidate in SUPPORTED_LOCALES else "en"
