"""Transient presentation helpers that never cache or persist Telegram titles."""

from __future__ import annotations

import regex


def truncate_graphemes(value: str, limit: int = 26) -> str:
    """Trim near a word boundary without splitting a Unicode grapheme cluster."""

    clusters = regex.findall(r"\X", value.strip())
    if len(clusters) <= limit:
        return "".join(clusters)
    shortened = "".join(clusters[:limit]).rstrip()
    boundary = shortened.rfind(" ")
    if boundary >= max(1, limit // 2):
        shortened = shortened[:boundary]
    return f"{shortened.rstrip()}…"
