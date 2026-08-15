"""Short-lived in-memory guards for repeated Telegram client actions."""

from __future__ import annotations

import asyncio


class StartDeduplicator:
    """Accept only the first /start from a user during a short client retry window."""

    def __init__(self, window_seconds: float = 2.0) -> None:
        self.window_seconds = window_seconds
        self._active_users: set[int] = set()
        self._lock = asyncio.Lock()

    async def accept(self, user_id: int) -> bool:
        """Return false for a concurrent/repeated start and forget the user shortly after."""

        async with self._lock:
            if user_id in self._active_users:
                return False
            self._active_users.add(user_id)
            asyncio.get_running_loop().call_later(
                self.window_seconds,
                self._active_users.discard,
                user_id,
            )
            return True
