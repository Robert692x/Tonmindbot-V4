from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import User
from bot.database.repositories import UserRepository
from bot.handlers.common import edit_panel
from bot.keyboards.inline import settings_keyboard
from bot.services.i18n import get_text
from bot.utils.formatters import format_settings

router = Router(name="settings")


@router.message(Command("settings"))
async def settings_command_handler(message: Message, user: User) -> None:
    await message.answer(format_settings(user), reply_markup=settings_keyboard(user))


@router.callback_query(F.data == "settings")
async def settings_panel_handler(callback: CallbackQuery, user: User) -> None:
    await edit_panel(callback, format_settings(user), settings_keyboard(user))
    await callback.answer()


@router.callback_query(F.data.in_({"settings:lang:en", "settings:lang:ru"}))
async def settings_language_handler(callback: CallbackQuery, session: AsyncSession, user: User) -> None:
    language_code = callback.data.rsplit(":", maxsplit=1)[-1]
    await UserRepository(session).set_language(user, language_code)
    language_name = get_text(user, "language_english") if language_code == "en" else get_text(user, "language_russian")
    await edit_panel(callback, format_settings(user), settings_keyboard(user))
    await callback.answer(get_text(user, "settings_language_updated", language=language_name))
