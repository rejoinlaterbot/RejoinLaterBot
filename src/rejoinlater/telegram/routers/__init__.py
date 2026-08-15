"""Router registration in deterministic command-to-state order."""

from aiogram import Dispatcher

from rejoinlater.telegram.routers import managed, membership, start, status, wizard


def register_routers(dispatcher: Dispatcher) -> None:
    """Attach all Telegram transport adapters."""

    dispatcher.include_routers(
        start.router,
        managed.router,
        status.router,
        wizard.router,
        membership.router,
    )
