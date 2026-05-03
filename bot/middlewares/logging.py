from __future__ import annotations

import logging
import time
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

log = logging.getLogger(__name__)


class LoggingMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        started_at = time.perf_counter()
        event_from_user = data.get("event_from_user")
        event_name = type(event).__name__
        user_id = getattr(event_from_user, "id", "anonymous")
        try:
            return await handler(event, data)
        finally:
            duration_ms = (time.perf_counter() - started_at) * 1000
            log.info("Handled %s for %s in %.1fms", event_name, user_id, duration_ms)
