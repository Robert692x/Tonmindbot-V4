from __future__ import annotations

import asyncio
import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery

from bot.database.models import User
from bot.handlers.common import edit_panel
from bot.keyboards.inline import analytics_keyboard, wallet_pnl_keyboard
from bot.services.container import ServiceContainer
from bot.services.i18n import get_text
from bot.services.wallet_analytics import calculate_wallet_pnl
from bot.utils.formatters import format_wallet_analytics, format_wallet_pnl

log = logging.getLogger(__name__)
router = Router(name="analytics")


@router.callback_query(F.data == "analytics")
async def analytics_handler(
    callback: CallbackQuery, user: User, services: ServiceContainer
) -> None:
    if not user.wallet_address:
        await callback.answer(get_text(user, "connect_wallet_first"), show_alert=True)
        return

    wallet_report, market = await asyncio.gather(
        services.tonapi.get_wallet_report(user.wallet_address),
        services.market.get_ton_market_snapshot(),
    )
    text = format_wallet_analytics(user, wallet_report, market)
    await edit_panel(callback, text, analytics_keyboard(user))
    await callback.answer()


@router.callback_query(F.data.in_({"analytics:pnl:1", "analytics:pnl:7", "analytics:pnl:30"}))
async def analytics_pnl_handler(
    callback: CallbackQuery, user: User, services: ServiceContainer
) -> None:
    if not user.wallet_address:
        await callback.answer(get_text(user, "connect_wallet_first"), show_alert=True)
        return

    days = int(callback.data.rsplit(":", 1)[-1])
    await callback.answer()

    pnl = await calculate_wallet_pnl(
        user.wallet_address, days, tonapi=services.tonapi
    )
    text = format_wallet_pnl(pnl)
    await edit_panel(callback, text, wallet_pnl_keyboard(user))
