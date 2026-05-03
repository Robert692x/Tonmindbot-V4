from __future__ import annotations

import asyncio
import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.analytics.network_engine import analyze_network
from bot.analytics.score_engine import compute_wallet_score
from bot.database.models import User
from bot.database.repositories import UserRepository
from bot.handlers.common import edit_panel
from bot.keyboards.inline import (
    simple_refresh_keyboard,
    wallet_analysis_keyboard,
    wallet_keyboard,
    wallet_pnl_detail_keyboard,
    wallet_transactions_keyboard,
)
from bot.services.container import ServiceContainer
from bot.services.i18n import get_text
from bot.services.wallet_analytics import (
    WalletPnL,
    analyze_wallet_behavior,
    calculate_wallet_pnl,
    get_transaction_summary,
    get_wallet_activity,
)
from bot.states import WalletStates
from bot.utils.formatters import (
    format_activity_report,
    format_analysis,
    format_network_report,
    format_pnl,
    format_portfolio,
    format_pnl_brief,
    format_transactions,
    format_txs_brief,
    format_wallet,
    format_wallet_brief,
    format_wallet_report,
    format_wallet_score,
)

log = logging.getLogger(__name__)
router = Router(name="wallet")

_LOADING_MSG = "⏳ Loading data…"


# ── Shared helpers ────────────────────────────────────────────────────────────

def _require_wallet(user: User) -> bool:
    return bool(user.wallet_address)


def _parse_args(message: Message) -> list[str]:
    parts = (message.text or "").split(maxsplit=1)
    return parts[1].split() if len(parts) > 1 else []


def _resolve_address(args: list[str], user: User, tonapi) -> str | None:
    for part in args:
        if tonapi.is_probable_address(part):
            return part
    return user.wallet_address


def _parse_days(args: list[str], default: int = 7) -> int:
    for part in args:
        if part.isdigit() and int(part) in (1, 7, 30):
            return int(part)
    return default


async def _no_wallet_panel(callback: CallbackQuery, user: User) -> None:
    await edit_panel(callback, get_text(user, "wallet_not_connected"), wallet_keyboard(user, False))
    await callback.answer()


# ── Main wallet view ──────────────────────────────────────────────────────────

@router.callback_query(F.data == "wallet")
async def wallet_handler(callback: CallbackQuery, user: User, services: ServiceContainer) -> None:
    if not _require_wallet(user):
        await _no_wallet_panel(callback, user)
        return

    report = await services.tonapi.get_wallet_report(user.wallet_address)
    await edit_panel(callback, format_wallet(user, report), wallet_keyboard(user, True))
    await callback.answer()


# ── Connect / update address flow ─────────────────────────────────────────────

@router.callback_query(F.data == "wallet:connect")
async def wallet_connect_handler(callback: CallbackQuery, state: FSMContext, user: User) -> None:
    await state.set_state(WalletStates.waiting_for_address)
    await edit_panel(callback, get_text(user, "wallet_connect_prompt"), wallet_keyboard(user, False))
    await callback.answer()


@router.message(WalletStates.waiting_for_address)
async def wallet_input_handler(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    services: ServiceContainer,
) -> None:
    address = (message.text or "").strip()
    if not services.tonapi.is_probable_address(address):
        await message.answer(get_text(user, "wallet_invalid_address"))
        return

    try:
        report = await services.tonapi.get_wallet_report(address, limit=1)
    except Exception:
        await message.answer(get_text(user, "wallet_validation_failed"))
        return

    await UserRepository(session).set_wallet_address(user, address)
    await state.clear()
    await message.answer(
        f"{get_text(user, 'wallet_connected_success')}\n\n{format_wallet(user, report)}",
        reply_markup=wallet_keyboard(user, True),
    )


# ── Transactions module ───────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("wallet:txs"))
async def wallet_txs_handler(callback: CallbackQuery, user: User, services: ServiceContainer) -> None:
    if not _require_wallet(user):
        await _no_wallet_panel(callback, user)
        return

    parts = (callback.data or "").split(":")
    days = int(parts[2]) if len(parts) == 3 and parts[2].isdigit() else 7

    await callback.answer(get_text(user, "wallet_loading"))

    try:
        txs, total_in, total_out, count = await get_transaction_summary(
            user.wallet_address, days, tonapi=services.tonapi
        )
    except Exception as exc:
        log.warning("wallet_txs_handler failed for %s: %s", user.wallet_address, exc)
        txs, total_in, total_out, count = [], 0.0, 0.0, 0

    text = format_transactions(user, txs, total_in, total_out, count, days, wallet_address=user.wallet_address)
    await edit_panel(callback, text, wallet_transactions_keyboard(user, days))


# ── Portfolio module ──────────────────────────────────────────────────────────

@router.callback_query(F.data == "wallet:portfolio")
async def wallet_portfolio_handler(callback: CallbackQuery, user: User, services: ServiceContainer) -> None:
    if not _require_wallet(user):
        await _no_wallet_panel(callback, user)
        return

    await callback.answer(get_text(user, "wallet_loading"))

    from bot.keyboards.inline import simple_refresh_keyboard

    try:
        portfolio = await services.tonapi.get_wallet_portfolio(user.wallet_address, limit=20)
    except Exception as exc:
        log.warning("wallet_portfolio_handler failed for %s: %s", user.wallet_address, exc)
        portfolio = []

    text = format_portfolio(user, portfolio)
    await edit_panel(
        callback,
        text,
        simple_refresh_keyboard(user, "wallet:portfolio"),
    )


# ── PNL module ────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("wallet:pnl"))
async def wallet_pnl_handler(callback: CallbackQuery, user: User, services: ServiceContainer) -> None:
    if not _require_wallet(user):
        await _no_wallet_panel(callback, user)
        return

    parts = (callback.data or "").split(":")
    days = int(parts[2]) if len(parts) == 3 and parts[2].isdigit() else 7

    await callback.answer(get_text(user, "wallet_loading"))

    try:
        pnl = await calculate_wallet_pnl(user.wallet_address, days, tonapi=services.tonapi)
    except Exception as exc:
        log.warning("wallet_pnl_handler failed for %s: %s", user.wallet_address, exc)
        from bot.services.wallet_analytics import WalletPnL
        pnl = WalletPnL(address=user.wallet_address, period_days=days, inflow=0, outflow=0, fees=0, tx_count=0)

    await edit_panel(callback, format_pnl(user, pnl), wallet_pnl_detail_keyboard(user, days))


# ── Deep analysis module ──────────────────────────────────────────────────────

@router.callback_query(F.data == "wallet:analysis")
async def wallet_analysis_handler(callback: CallbackQuery, user: User, services: ServiceContainer) -> None:
    if not _require_wallet(user):
        await _no_wallet_panel(callback, user)
        return

    await callback.answer(get_text(user, "wallet_loading"))

    try:
        behavior = await analyze_wallet_behavior(
            user.wallet_address,
            tonapi=services.tonapi,
            period_days=30,
        )
    except Exception as exc:
        log.warning("wallet_analysis_handler failed for %s: %s", user.wallet_address, exc)
        await edit_panel(callback, get_text(user, "error_generic"), wallet_analysis_keyboard(user))
        return

    await edit_panel(callback, format_analysis(user, behavior), wallet_analysis_keyboard(user))


# ── /wallet [address] ─────────────────────────────────────────────────────────

@router.message(Command("wallet"))
async def cmd_wallet(message: Message, user: User, services: ServiceContainer) -> None:
    args = _parse_args(message)
    address = _resolve_address(args, user, services.tonapi)

    if not address:
        await message.answer(get_text(user, "wallet_cmd_no_address"))
        return
    if not services.tonapi.is_probable_address(address):
        await message.answer(get_text(user, "wallet_invalid_address"))
        return

    msg = await message.answer(_LOADING_MSG)

    report, behavior = await asyncio.gather(
        services.tonapi.get_wallet_report(address),
        analyze_wallet_behavior(address, tonapi=services.tonapi, period_days=30),
    )
    text = format_wallet_brief(address, report.balance_ton, behavior)
    await msg.edit_text(text, reply_markup=simple_refresh_keyboard(user, "wallet"))


# ── /tx <address> [1|7|30] ────────────────────────────────────────────────────

@router.message(Command("tx"))
async def cmd_tx(message: Message, user: User, services: ServiceContainer) -> None:
    args = _parse_args(message)
    address = _resolve_address(args, user, services.tonapi)
    days = _parse_days(args)

    if not address:
        await message.answer(get_text(user, "wallet_cmd_no_address"))
        return

    msg = await message.answer(_LOADING_MSG)
    txs, total_in, total_out, count = await get_transaction_summary(address, days, tonapi=services.tonapi)
    await msg.edit_text(
        format_txs_brief(address, txs, total_in, total_out, count, days),
        reply_markup=simple_refresh_keyboard(user, "wallet"),
    )


# ── /portfolio [address] ──────────────────────────────────────────────────────

@router.message(Command("portfolio"))
async def cmd_portfolio(message: Message, user: User, services: ServiceContainer) -> None:
    args = _parse_args(message)
    address = _resolve_address(args, user, services.tonapi)

    if not address:
        await message.answer(get_text(user, "wallet_cmd_no_address"))
        return

    msg = await message.answer(_LOADING_MSG)
    portfolio = await services.tonapi.get_wallet_portfolio(address, limit=20)
    await msg.edit_text(
        format_portfolio(user, portfolio),
        reply_markup=simple_refresh_keyboard(user, "portfolio"),
    )


# ── /pnl <address> [1|7|30] ──────────────────────────────────────────────────

@router.message(Command("pnl"))
async def cmd_pnl(message: Message, user: User, services: ServiceContainer) -> None:
    args = _parse_args(message)
    address = _resolve_address(args, user, services.tonapi)
    days = _parse_days(args)

    if not address:
        await message.answer(get_text(user, "wallet_cmd_no_address"))
        return

    msg = await message.answer(_LOADING_MSG)
    pnl = await calculate_wallet_pnl(address, days, tonapi=services.tonapi)
    await msg.edit_text(
        format_pnl_brief(address, pnl),
        reply_markup=simple_refresh_keyboard(user, "wallet"),
    )


# ── /analyze <address> ────────────────────────────────────────────────────────

@router.message(Command("analyze"))
async def cmd_analyze(message: Message, user: User, services: ServiceContainer) -> None:
    args = _parse_args(message)
    address = _resolve_address(args, user, services.tonapi)

    if not address:
        await message.answer(get_text(user, "wallet_cmd_no_address"))
        return

    msg = await message.answer(_LOADING_MSG)
    behavior = await analyze_wallet_behavior(address, tonapi=services.tonapi, period_days=30)
    await msg.edit_text(
        format_analysis(user, behavior),
        reply_markup=simple_refresh_keyboard(user, "wallet"),
    )


# ── /score <address> ──────────────────────────────────────────────────────────

@router.message(Command("score"))
async def cmd_score(message: Message, user: User, services: ServiceContainer) -> None:
    args = _parse_args(message)
    address = _resolve_address(args, user, services.tonapi)

    if not address:
        await message.answer(get_text(user, "wallet_cmd_no_address"))
        return

    msg = await message.answer(_LOADING_MSG)
    report, behavior = await asyncio.gather(
        services.tonapi.get_wallet_report(address),
        analyze_wallet_behavior(address, tonapi=services.tonapi, period_days=30),
    )
    score = compute_wallet_score(behavior, report.balance_ton)
    await msg.edit_text(
        format_wallet_score(address, score),
        reply_markup=simple_refresh_keyboard(user, "wallet"),
    )


# ── /network <address> ────────────────────────────────────────────────────────

@router.message(Command("network"))
async def cmd_network(message: Message, user: User, services: ServiceContainer) -> None:
    args = _parse_args(message)
    address = _resolve_address(args, user, services.tonapi)

    if not address:
        await message.answer(get_text(user, "wallet_cmd_no_address"))
        return

    msg = await message.answer(_LOADING_MSG)
    network = await analyze_network(address, tonapi=services.tonapi)
    await msg.edit_text(
        format_network_report(address, network),
        reply_markup=simple_refresh_keyboard(user, "wallet"),
    )


# ── /activity <address> ───────────────────────────────────────────────────────

@router.message(Command("activity"))
async def cmd_activity(message: Message, user: User, services: ServiceContainer) -> None:
    args = _parse_args(message)
    address = _resolve_address(args, user, services.tonapi)

    if not address:
        await message.answer(get_text(user, "wallet_cmd_no_address"))
        return

    msg = await message.answer(_LOADING_MSG)
    activity = await get_wallet_activity(address, tonapi=services.tonapi)
    await msg.edit_text(
        format_activity_report(address, activity),
        reply_markup=simple_refresh_keyboard(user, "wallet"),
    )
