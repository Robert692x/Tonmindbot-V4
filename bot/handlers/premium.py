from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import User
from bot.database.repositories import SubscriptionRepository
from bot.handlers.common import edit_panel
from bot.keyboards.inline import premium_keyboard
from bot.services.container import ServiceContainer
from bot.services.i18n import get_text
from bot.states import PaymentStates
from bot.utils.formatters import format_premium

router = Router(name="premium")


@router.callback_query(F.data == "premium")
async def premium_handler(
    callback: CallbackQuery,
    session: AsyncSession,
    user: User,
    services: ServiceContainer,
) -> None:
    pending = await SubscriptionRepository(session).get_pending_for_user(user.id)
    text = format_premium(
        user,
        pending,
        services.settings.payment_wallet,
        services.settings.PREMIUM_PRICE_TON,
        services.settings.PREMIUM_DAYS,
    )
    await edit_panel(callback, text, premium_keyboard(user, pending is not None, user.is_premium))
    await callback.answer()


@router.callback_query(F.data == "premium:buy")
async def premium_buy_handler(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    services: ServiceContainer,
) -> None:
    checkout = await services.premium.get_or_create_checkout(session, user)
    await state.set_state(PaymentStates.awaiting_confirmation)
    await state.update_data(payment_comment=checkout.payment_comment)
    text = format_premium(
        user,
        checkout,
        services.settings.payment_wallet,
        services.settings.PREMIUM_PRICE_TON,
        services.settings.PREMIUM_DAYS,
    )
    await edit_panel(callback, text, premium_keyboard(user, True, user.is_premium))
    await callback.answer(get_text(user, "premium_payment_generated"))


@router.callback_query(F.data == "premium:check")
async def premium_check_handler(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    services: ServiceContainer,
) -> None:
    activated = await services.premium.verify_user_payment(session, user)
    if activated is None:
        await callback.answer(get_text(user, "premium_not_detected"), show_alert=True)
        return
    await state.clear()
    text = (
        f"{get_text(user, 'premium_activated_title')}\n"
        f"{get_text(user, 'label_status')}: <b>{activated.status.upper()}</b>\n"
        f"{get_text(user, 'label_expires_at')}: <b>{activated.expires_at:%Y-%m-%d %H:%M UTC}</b>"
    )
    await edit_panel(callback, text, premium_keyboard(user, False, True))
    await callback.answer(get_text(user, "premium_active_ack"))
