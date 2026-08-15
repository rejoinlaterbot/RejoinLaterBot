"""Container startup that migrates the database before polling."""

from __future__ import annotations

import os

from alembic import command
from alembic.config import Config

from rejoinlater.config import Settings
from rejoinlater.main import main


def start() -> None:
    """Apply idempotent migrations using the file-backed URL, then start the bot."""

    settings = Settings()
    os.environ["DATABASE_URL"] = settings.secret("database_url")
    command.upgrade(Config("alembic.ini"), "head")
    main()


if __name__ == "__main__":
    start()
