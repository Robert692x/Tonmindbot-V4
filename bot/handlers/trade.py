from __future__ import annotations

import logging
import re

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import User
from bot.handlers.common import edit_panel
from bot.keyboards.inline import (
    simple_refresh_keyboard,
    trade_back_keyboard,
    trade_menu_keyboard,
    trade_period_keyboard,
)
from bot.services.container import ServiceContainer
from bot.services.i18n import get_text
from bot.states import TradeStates
from bot.trading.analytics import get_trading_summary
from bot.trading.formatters import (
    format_pnl_summary,
    format_trade_added,
    format_trade_history,
    format_trading_stats,
    format_trading_summary,
    format_positions,
)
from bot.trading.history import get_trade_history
from bot.trading.service import InsufficientPositionError

log = logging.getLogger(__name__)
router = Router(name="trade")

# BUY ETH 0.5 3000 [FEE 5]
_TRADE_RE = re.compile(
    r"^(BUY|SELL)\s+([A-Za-z0-9]+)\s+"
    r"([0-9]+(?:\.[0-9]+)?)\s+"
    r"([0-9]+(?:\.[0-9]+)?)"
    r"(?:\s+FEE\s+([0-9]+(?:\.[0-9]+)?))?$",
    re.IGNORECASE,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _resolve_token(
    services: ServiceContainer, raw_symbol: str
) -> tuple[str, str]:
    try:
        results = await services.market.search_token(raw_symbol, limit=1)
        if results:
            return results[0].coin_id, results[0].symbol
    except Exception as exc:
        log.warning("Token search failed for %r: %s", raw_symbol, exc)
    return raw_symbol.lower(), raw_symbol.upper()


async def _fetch_price_map(
    services: ServiceContainer, token_ids: list[str]
) -> dict[str, float]:
    if not token_ids:
        return {}
    try:
        tokens = await services.market.get_tokens_market(token_ids)
        return {t.coin_id: t.price_usd for t in tokens}
    except Exception as exc:
        log.warning("Price fetch failed: %s", exc)
        return {}


# ── Menu ──────────────────────────────────────────────────────────────────────

@router.message(Command("trade"))
async def trade_command_handler(message: Message, state: FSMContext, user: User) -> None:
    await state.clear()
    await message.answer(get_text(user, "trade_menu_title"), reply_markup=trade_menu_keyboard(user))


@router.callback_query(F.data == "trade")
async def trade_menu_handler(callback: CallbackQuery, state: FSMContext, user: User) -> None:
    await state.clear()
    await edit_panel(callback, get_text(user, "trade_menu_title"), trade_menu_keyboard(user))
    await callback.answer()


# ── Add trade ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "trade:add")
async def trade_add_prompt_handler(
    callback: CallbackQuery, state: FSMContext, user: User
) -> None:
    await state.set_state(TradeStates.adding)
    await edit_panel(callback, get_text(user, "trade_add_prompt"), trade_back_keyboard(user))
    await callback.answer()


@router.message(TradeStates.adding)
async def trade_add_input_handler(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    services: ServiceContainer,
) -> None:
    raw = (message.text or "").strip()
    match = _TRADE_RE.match(raw)
    if not match:
        await message.answer(get_text(user, "trade_error_invalid_format"))
        return

    side = match.group(1).upper()
    raw_symbol = match.group(2)
    amount = float(match.group(3))
    price = float(match.group(4))
    fee = float(match.group(5)) if match.group(5) else 0.0

    if amount <= 0 or price <= 0:
        await message.answer(get_text(user, "trade_error_invalid_format"))
        return

    token_id, symbol = await _resolve_token(services, raw_symbol)

    try:
        trade = await services.trading.add_trade(
            session,
            user_id=user.id,
            token_id=token_id,
            symbol=symbol,
            side=side,
            amount=amount,
            price=price,
            fee=fee,
        )
    except InsufficientPositionError as exc:
        await message.answer(get_text(user, "trade_error_insufficient", detail=str(exc)))
        return
    except Exception as exc:
        log.exception("add_trade failed: %s", exc)
        await message.answer(get_text(user, "error_generic"))
        return

    await state.clear()
    await message.answer(format_trade_added(trade), reply_markup=trade_back_keyboard(user))


# ── Positions ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "trade:positions")
async def trade_positions_handler(
    callback: CallbackQuery,
    session: AsyncSession,
    user: User,
    services: ServiceContainer,
) -> None:
    positions = await services.trading.get_positions(session, user.id)
    price_map = await _fetch_price_map(services, [p.token_id for p in positions])
    text = format_positions(positions, price_map)
    await edit_panel(callback, text, simple_refresh_keyboard(user, "trade:positions"))
    await callback.answer()


# ── History ───────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "trade:history")
async def trade_history_handler(
    callback: CallbackQuery,
    session: AsyncSession,
    user: User,
    services: ServiceContainer,
) -> None:
    trades = await get_trade_history(session, user.id)
    text = format_trade_history(trades)
    await edit_panel(callback, text, trade_period_keyboard(user, "history"))
    await callback.answer()


@router.callback_query(F.data.in_({"trade:history:7", "trade:history:30"}))
async def trade_history_period_handler(
    callback: CallbackQuery,
    session: AsyncSession,
    user: User,
) -> None:
    days = int(callback.data.rsplit(":", 1)[-1])
    trades = await get_trade_history(session, user.id, days=days)
    text = format_trade_history(trades, period_label=f"({days}D)")
    await edit_panel(callback, text, trade_period_keyboard(user, "history"))
    await callback.answer()


# ── PnL ───────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "trade:pnl")
async def trade_pnl_handler(
    callback: CallbackQuery,
    session: AsyncSession,
    user: User,
    services: ServiceContainer,
) -> None:
    records = await services.trading.get_realized_pnl_records(session, user.id)
    positions = await services.trading.get_positions(session, user.id)
    price_map = await _fetch_price_map(services, [p.token_id for p in positions])
    text = format_pnl_summary(records, positions, price_map)
    await edit_panel(callback, text, simple_refresh_keyboard(user, "trade:pnl"))
    await callback.answer()


# ── Stats ─────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "trade:stats")
async def trade_stats_handler(
    callback: CallbackQuery,
    session: AsyncSession,
    user: User,
    services: ServiceContainer,
) -> None:
    stats = await services.trading.get_trading_stats(session, user.id)
    text = format_trading_stats(stats)
    await edit_panel(callback, text, simple_refresh_keyboard(user, "trade:stats"))
    await callback.answer()


# ── Time-based summaries ──────────────────────────────────────────────────────

@router.callback_query(F.data.in_({"trade:summary:7", "trade:summary:30"}))
async def trade_summary_handler(
    callback: CallbackQuery,
    session: AsyncSession,
    user: User,
) -> None:
    days = int(callback.data.rsplit(":", 1)[-1])
    summary = await get_trading_summary(session, user.id, days)
    text = format_trading_summary(summary)
    await edit_panel(callback, text, trade_period_keyboard(user, "summary"))
    await callback.answer()
