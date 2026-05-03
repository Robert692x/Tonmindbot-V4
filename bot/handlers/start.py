from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import User
from bot.database.repositories import ReferralRepository, UserRepository
from bot.handlers.common import edit_panel, welcome_text
from bot.keyboards.inline import main_menu_keyboard
from bot.services.i18n import get_text
from bot.services.container import ServiceContainer

router = Router(name="start")


@router.message(CommandStart())
async def start_handler(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    services: ServiceContainer,
) -> None:
    await state.clear()
    referral_note = ""
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) == 2 and parts[1].startswith("ref_"):
        referral_code = parts[1][4:].strip().upper()
        referrer = await UserRepository(session).get_by_referral_code(referral_code)
        if referrer is not None:
            attached = await ReferralRepository(session).attach_referral(referrer, user)
            if attached:
                await services.premium.grant_referral_bonus(session, referrer, services.settings.REFERRAL_BONUS_DAYS)
                referral_note = f"\n\n{get_text(user, 'referral_linked')}"

    await message.answer(f"{welcome_text(user)}{referral_note}", reply_markup=main_menu_keyboard(user))


@router.callback_query(F.data == "menu")
async def menu_handler(callback: CallbackQuery, state: FSMContext, user: User) -> None:
    await state.clear()
    await edit_panel(callback, welcome_text(user), main_menu_keyboard(user))
    await callback.answer()
