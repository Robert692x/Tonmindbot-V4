import time
import logging
from typing import Any, Awaitable, Callable
from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject

log = logging.getLogger(__name__)
_last: dict[int, float] = {}


class ThrottleMiddleware(BaseMiddleware):
    def __init__(self, rate: float = 1.0):
        self.rate = rate

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not isinstance(event, Message):
            return await handler(event, data)

        uid = event.from_user.id if event.from_user else None
        if uid:
            now = time.monotonic()
            if now - _last.get(uid, 0) < self.rate:
                return
            _last[uid] = now

        return await handler(event, data)
