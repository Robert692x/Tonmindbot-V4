from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import User
from bot.database.repositories import ReferralRepository
from bot.handlers.common import edit_panel
from bot.keyboards.inline import simple_refresh_keyboard
from bot.services.container import ServiceContainer
from bot.utils.formatters import format_profile

router = Router(name="profile")


@router.callback_query(F.data == "profile")
async def profile_handler(
    callback: CallbackQuery,
    session: AsyncSession,
    user: User,
    services: ServiceContainer,
) -> None:
    referral_count = await ReferralRepository(session).count_for_user(user.id)
    text = format_profile(user, user, referral_count, services.settings.BOT_USERNAME)
    await edit_panel(callback, text, simple_refresh_keyboard(user, "profile"))
    await callback.answer()
