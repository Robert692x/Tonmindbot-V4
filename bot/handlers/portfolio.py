from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery

from bot.database.models import User
from bot.handlers.common import edit_panel
from bot.keyboards.inline import simple_refresh_keyboard
from bot.services.i18n import get_text
from bot.services.container import ServiceContainer
from bot.utils.formatters import format_portfolio

router = Router(name="portfolio")


@router.callback_query(F.data == "portfolio")
async def portfolio_handler(callback: CallbackQuery, user: User, services: ServiceContainer) -> None:
    if not user.wallet_address:
        await callback.answer(get_text(user, "connect_wallet_first"), show_alert=True)
        return
    portfolio = await services.tonapi.get_wallet_portfolio(user.wallet_address)
    await edit_panel(callback, format_portfolio(user, portfolio), simple_refresh_keyboard(user, "portfolio"))
    await callback.answer()
