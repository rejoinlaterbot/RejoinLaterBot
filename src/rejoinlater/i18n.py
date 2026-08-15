"""JSON catalog loader with strict cross-language key parity."""

from __future__ import annotations

import json
from importlib.resources import files
from typing import Any

SUPPORTED_LOCALES = ("en", "fr", "zh", "ru", "es", "hi", "ar")


class I18n:
    """Load all catalogs once; Telegram metadata is never part of this cache."""

    def __init__(self) -> None:
        self.catalogs: dict[str, dict[str, str]] = {}
        root = files("rejoinlater.locales")
        for locale in SUPPORTED_LOCALES:
            raw = root.joinpath(f"{locale}.json").read_text(encoding="utf-8")
            self.catalogs[locale] = json.loads(raw)
        reference = set(self.catalogs["en"])
        if any(set(catalog) != reference for catalog in self.catalogs.values()):
            raise RuntimeError("translation catalogs have mismatched keys")

    def t(self, locale: str, key: str, **values: Any) -> str:
        """Format one externalized user-facing string with English fallback."""

        catalog = self.catalogs.get(locale, self.catalogs["en"])
        return catalog[key].format(**values)
