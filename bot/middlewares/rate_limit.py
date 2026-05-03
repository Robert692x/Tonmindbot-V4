from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from bot.services.cache import CacheService
from config import Settings


class RateLimitMiddleware(BaseMiddleware):
    def __init__(self, cache: CacheService, settings: Settings) -> None:
        self.cache = cache
        self.settings = settings

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        event_from_user = data.get("event_from_user")
        if event_from_user is None:
            return await handler(event, data)

        key = f"rate-limit:{event_from_user.id}:{type(event).__name__}"
        count = await self.cache.increment(key, self.settings.RATE_LIMIT_WINDOW_SECONDS)
        if count > self.settings.RATE_LIMIT_MAX_EVENTS:
            if isinstance(event, Message):
                await event.answer("Too many requests in a short burst. Please wait a moment.")
            elif isinstance(event, CallbackQuery):
                await event.answer("Too many requests. Please slow down a bit.", show_alert=False)
            return None
        return await handler(event, data)
