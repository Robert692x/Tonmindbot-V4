import logging
from typing import Any, Awaitable, Callable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from bot.database.crud import check_premium, get_or_create_user
from bot.database.db import get_session

log = logging.getLogger(__name__)


class AuthMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        tg_user = data.get("event_from_user")
        if not tg_user:
            return await handler(event, data)

        async with get_session() as session:
            user, created = await get_or_create_user(
                session,
                telegram_id=tg_user.id,
                username=tg_user.username,
                first_name=tg_user.first_name,
            )
            if user.is_banned:
                log.warning("Banned user blocked: %d", tg_user.id)
                return

            user = await check_premium(session, user)
            data["db_user"] = user
            data["is_premium"] = user.is_premium

        if created:
            log.info("New user: tg=%d @%s", tg_user.id, tg_user.username)

        return await handler(event, data)
