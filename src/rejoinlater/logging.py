"""Structured metadata-only logging configuration."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime


class JsonFormatter(logging.Formatter):
    """Emit event lines without serializing Telegram or application objects."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "time": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        return json.dumps(payload, ensure_ascii=True)


class ApplicationOnlyFilter(logging.Filter):
    """Drop third-party records whose free-form messages were not privacy-reviewed."""

    def filter(self, record: logging.LogRecord) -> bool:
        return record.name == "rejoinlater" or record.name.startswith("rejoinlater.")


def configure_logging(level: str) -> None:
    """Disable verbose framework update logging and install a safe formatter."""

    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    handler.addFilter(ApplicationOnlyFilter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())
    # aiogram's handled-update diagnostics are unnecessary for operation and may
    # expose update identifiers; API error details are normalized by our boundary.
    logging.getLogger("aiogram.event").disabled = True
    logging.getLogger("aiogram.dispatcher").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
