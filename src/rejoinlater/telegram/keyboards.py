"""Inline keyboards built only from localized labels and opaque callback values."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from rejoinlater.i18n import SUPPORTED_LOCALES, I18n


def language_keyboard(i18n: I18n) -> InlineKeyboardMarkup:
    """Return the required seven-language selector."""

    rows = [
        [InlineKeyboardButton(text=i18n.t(code, "language_name"), callback_data=f"lang:{code}")]
        for code in SUPPORTED_LOCALES
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def home_keyboard(i18n: I18n, locale: str) -> InlineKeyboardMarkup:
    """Offer the unified group-return flow from the private About screen."""

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.t(locale, "add_public_group"), callback_data="group:add"
                )
            ],
        ]
    )


def visibility_keyboard(i18n: I18n, locale: str) -> InlineKeyboardMarkup:
    """Put Hidden first to make the privacy-preserving choice the default."""

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.t(locale, "hidden_option"), callback_data="vis:hidden"
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.t(locale, "visible_option"), callback_data="vis:visible"
                )
            ],
            [InlineKeyboardButton(text=i18n.t(locale, "cancel"), callback_data="wizard:cancel")],
        ]
    )


def duration_keyboard(i18n: I18n, locale: str) -> InlineKeyboardMarkup:
    """Return the eight fixed privacy-safe duration buckets plus custom."""

    values = ("1h", "6h", "12h", "1d", "3d", "1w", "2w", "30d", "custom")
    buttons = [
        InlineKeyboardButton(text=i18n.t(locale, f"duration_{value}"), callback_data=f"dur:{value}")
        for value in values
    ]
    rows = [buttons[index : index + 2] for index in range(0, len(buttons), 2)]
    rows.append(
        [InlineKeyboardButton(text=i18n.t(locale, "cancel"), callback_data="wizard:cancel")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def confirmation_keyboard(i18n: I18n, locale: str) -> InlineKeyboardMarkup:
    """Confirm or discard the transient wizard state."""

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.t(locale, "confirm"), callback_data="wizard:confirm"
                ),
                InlineKeyboardButton(text=i18n.t(locale, "cancel"), callback_data="wizard:cancel"),
            ]
        ]
    )
