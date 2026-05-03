from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery

from bot.database.models import User
from bot.handlers.common import edit_panel
from bot.keyboards.inline import simple_refresh_keyboard
from bot.services.container import ServiceContainer
from bot.utils.formatters import format_whales

router = Router(name="whales")


@router.callback_query(F.data == "whales")
async def whales_handler(callback: CallbackQuery, user: User, services: ServiceContainer) -> None:
    whales = await services.tonapi.get_recent_whales()
    await edit_panel(callback, format_whales(user, whales), simple_refresh_keyboard(user, "whales"))
    await callback.answer()
