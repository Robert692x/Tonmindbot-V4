from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.repositories import UserRepository


class UserContextMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        event_from_user = data.get("event_from_user")
        session: AsyncSession | None = data.get("session")
        if event_from_user is None or session is None:
            return await handler(event, data)

        user = await UserRepository(session).get_or_create_from_telegram(event_from_user)
        if user.is_blocked:
            if isinstance(event, Message):
                await event.answer("Access to the bot is restricted for this account.")
            return None

        data["user"] = user
        return await handler(event, data)
