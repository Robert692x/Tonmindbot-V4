from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from html import escape

from bot.database.models import User
from bot.handlers.common import edit_panel
from bot.keyboards.inline import price_keyboard, search_prompt_keyboard, search_result_keyboard, simple_refresh_keyboard
from bot.services.container import ServiceContainer
from bot.services.i18n import get_text
from bot.states import PriceStates
from bot.utils.formatters import format_market_overview, format_market_snapshot, format_price_card, format_trending

log = logging.getLogger(__name__)
router = Router(name="price")


async def _show_overview(target: CallbackQuery | Message, user: User, services: ServiceContainer) -> None:
    try:
        tokens = await services.market.get_market_overview()
        text = format_market_overview(user, tokens)
    except Exception as exc:
        log.warning("Market overview failed, falling back to TON-only: %s", exc)
        snapshot = await services.market.get_ton_market_snapshot()
        text = format_market_snapshot(user, snapshot)

    if isinstance(target, CallbackQuery):
        await edit_panel(target, text, price_keyboard(user))
    else:
        await target.answer(text, reply_markup=price_keyboard(user))


@router.message(Command("price"))
async def price_command_handler(message: Message, state: FSMContext, user: User, services: ServiceContainer) -> None:
    await state.clear()
    await _show_overview(message, user, services)


@router.callback_query(F.data == "price")
async def price_callback_handler(
    callback: CallbackQuery, state: FSMContext, user: User, services: ServiceContainer
) -> None:
    await state.clear()
    await _show_overview(callback, user, services)
    await callback.answer()


@router.callback_query(F.data == "price:search")
async def price_search_prompt_handler(callback: CallbackQuery, state: FSMContext, user: User) -> None:
    await state.set_state(PriceStates.searching)
    await edit_panel(callback, get_text(user, "price_search_prompt"), search_prompt_keyboard(user))
    await callback.answer()


@router.message(PriceStates.searching)
async def price_search_handler(
    message: Message, state: FSMContext, user: User, services: ServiceContainer
) -> None:
    query = (message.text or "").strip()
    if not query:
        return

    searching_msg = await message.answer(get_text(user, "price_searching"))

    try:
        tokens = await services.market.search_token(query)
    except Exception as exc:
        log.warning("Token search error for %r: %s", query, exc)
        await searching_msg.edit_text(get_text(user, "error_generic"))
        return

    await state.clear()

    if not tokens:
        await searching_msg.edit_text(
            get_text(user, "price_not_found", query=escape(query)),
            reply_markup=search_result_keyboard(user),
        )
        return

    if len(tokens) == 1:
        text = format_price_card(user, tokens[0])
    else:
        header = get_text(user, "price_search_results", query=escape(query))
        cards = "\n\n".join(format_price_card(user, t) for t in tokens[:3])
        text = f"{header}\n\n{cards}"

    await searching_msg.edit_text(text, reply_markup=search_result_keyboard(user))


@router.callback_query(F.data == "price:trending")
async def price_trending_handler(
    callback: CallbackQuery, user: User, services: ServiceContainer
) -> None:
    try:
        tokens = await services.market.get_trending()
        text = format_trending(user, tokens)
    except Exception as exc:
        log.warning("Trending fetch failed: %s", exc)
        text = get_text(user, "error_generic")

    await edit_panel(callback, text, simple_refresh_keyboard(user, "price:trending"))
    await callback.answer()
