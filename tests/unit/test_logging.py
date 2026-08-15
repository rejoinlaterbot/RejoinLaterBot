"""Ensure unreviewed framework records cannot reach production logs."""

import logging

from rejoinlater.logging import ApplicationOnlyFilter


def test_only_application_loggers_pass_privacy_filter() -> None:
    privacy_filter = ApplicationOnlyFilter()
    safe = logging.LogRecord("rejoinlater.services.delivery", 20, "", 1, "safe", (), None)
    external = logging.LogRecord("aiogram.event", 40, "", 1, "sensitive update", (), None)

    assert privacy_filter.filter(safe) is True
    assert privacy_filter.filter(external) is False
