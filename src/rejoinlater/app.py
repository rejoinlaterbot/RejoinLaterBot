"""Composition root for long polling; business services are transport-neutral."""

from __future__ import annotations

import asyncio
from contextlib import suppress

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from rejoinlater.config import Settings
from rejoinlater.crypto import DataProtector
from rejoinlater.db.repository import Repository
from rejoinlater.db.session import create_database
from rejoinlater.i18n import I18n
from rejoinlater.logging import configure_logging
from rejoinlater.services.delivery import DeliveryWorker
from rejoinlater.telegram.commands import configure_bot_profile, configure_command_menu
from rejoinlater.telegram.deduplication import StartDeduplicator
from rejoinlater.telegram.routers import register_routers


async def run(settings: Settings | None = None) -> None:
    """Start polling and the single database-driven scheduler worker."""

    config = settings or Settings()
    configure_logging(config.log_level)
    encryption_key = config.secret("data_encryption_key")
    protector = DataProtector(encryption_key, config.secret("lookup_hmac_key"))
    i18n = I18n()
    engine, sessions = create_database(config.secret("database_url"))
    repository = Repository(sessions, protector)
    bot = Bot(token=config.secret("telegram_bot_token"))
    dispatcher = Dispatcher(storage=MemoryStorage())
    register_routers(dispatcher)
    worker = DeliveryWorker(bot, repository, protector, i18n, config)
    start_deduplicator = StartDeduplicator()
    scheduler_task = asyncio.create_task(worker.run(), name="database-scheduler")
    try:
        await configure_bot_profile(bot, i18n)
        await configure_command_menu(bot, i18n)
        await dispatcher.start_polling(
            bot,
            repository=repository,
            i18n=i18n,
            settings=config,
            worker=worker,
            start_deduplicator=start_deduplicator,
        )
    finally:
        scheduler_task.cancel()
        with suppress(asyncio.CancelledError):
            await scheduler_task
        await bot.session.close()
        await engine.dispose()
