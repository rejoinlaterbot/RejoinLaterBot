"""Short-lived in-memory wizard state; no message or title is persisted."""

from aiogram.fsm.state import State, StatesGroup


class ReturnWizard(StatesGroup):
    """Shared Managed/Public choice flow."""

    visibility = State()
    duration = State()
    custom_days = State()
    confirmation = State()
