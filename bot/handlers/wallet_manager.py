from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import User
from bot.handlers.common import edit_panel
from bot.keyboards.inline import (
    simple_refresh_keyboard,
    wm_alert_settings_keyboard,
    wm_confirm_remove_keyboard,
    wm_main_keyboard,
    wm_wallet_keyboard,
)
from bot.services.container import ServiceContainer
from bot.services.i18n import get_text
from bot.services.wallet_manager import WalletAlreadyExistsError, WalletLimitError
from bot.states import WalletManagerStates
from bot.utils.formatters import format_wallet_detail, format_wallet_manager

log = logging.getLogger(__name__)
router = Router(name="wallet_manager")

_LOADING = "Loading..."


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _show_main(target: CallbackQuery | Message, session: AsyncSession, user: User, services: ServiceContainer) -> None:
    wallets = await services.wallet_manager.list_wallets(session, user.id)
    text = format_wallet_manager(user, wallets)
    kb = wm_main_keyboard(user, wallets)
    if isinstance(target, CallbackQuery):
        await edit_panel(target, text, kb)
    else:
        await target.answer(text, reply_markup=kb)


# ── Main screen ───────────────────────────────────────────────────────────────

@router.message(Command("wm", "walletmanager"))
async def wm_command(message: Message, session: AsyncSession, user: User, services: ServiceContainer) -> None:
    await _show_main(message, session, user, services)


@router.callback_query(F.data == "wm")
async def wm_callback(callback: CallbackQuery, session: AsyncSession, user: User, services: ServiceContainer) -> None:
    await _show_main(callback, session, user, services)
    await callback.answer()


# ── Add wallet ────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "wm:add")
async def wm_add_prompt(callback: CallbackQuery, state: FSMContext, user: User) -> None:
    await state.set_state(WalletManagerStates.waiting_for_address)
    await edit_panel(
        callback,
        get_text(user, "wm_add_prompt"),
        simple_refresh_keyboard(user, "wm"),
    )
    await callback.answer()


@router.message(WalletManagerStates.waiting_for_address)
async def wm_add_address_input(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    services: ServiceContainer,
) -> None:
    raw = (message.text or "").strip()
    parts = raw.split(maxsplit=1)
    address = parts[0]
    name = parts[1].strip() if len(parts) > 1 else None

    if not services.tonapi.is_probable_address(address):
        await message.answer(get_text(user, "wallet_invalid_address"))
        return

    try:
        wallet = await services.wallet_manager.add_wallet(session, user.id, address, name)
    except WalletAlreadyExistsError:
        await message.answer(get_text(user, "wm_already_exists"))
        return
    except WalletLimitError as exc:
        await message.answer(str(exc))
        return

    await state.clear()
    label = f"  {wallet.label}" if wallet.label else ""
    await message.answer(
        f"{get_text(user, 'wm_added')}\n<code>{address}</code>{label}",
        reply_markup=simple_refresh_keyboard(user, "wm"),
    )


# ── Wallet detail ─────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("wm:w:"))
async def wm_wallet_detail(callback: CallbackQuery, session: AsyncSession, user: User, services: ServiceContainer) -> None:
    wallet_id = int(callback.data.split(":")[-1])
    wallet = await services.wallet_manager.get_wallet(session, user.id, wallet_id)
    if wallet is None:
        await callback.answer(get_text(user, "wm_not_found"), show_alert=True)
        return

    await callback.answer(_LOADING)

    try:
        report = await services.tonapi.get_wallet_report(wallet.address)
        balance = report.balance_ton
        last_act = report.last_activity.strftime("%Y-%m-%d") if report.last_activity else "n/a"
        tx_count = len(report.transactions)
        risk = report.risk.level.upper()
    except Exception:
        balance, last_act, tx_count, risk = 0.0, "n/a", 0, "n/a"

    cfg = services.wallet_manager.get_alert_config(wallet)
    text = format_wallet_detail(
        user, wallet, balance, last_act, tx_count, risk,
        behavior="—", alert_config=cfg,
    )
    await edit_panel(callback, text, wm_wallet_keyboard(user, wallet_id, wallet.alerts_enabled))


# ── Toggle alerts (ON/OFF) ────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("wm:toggle:"))
async def wm_toggle_alerts(callback: CallbackQuery, session: AsyncSession, user: User, services: ServiceContainer) -> None:
    wallet_id = int(callback.data.split(":")[-1])
    wallet = await services.wallet_manager.toggle_alerts(session, user.id, wallet_id)
    if wallet is None:
        await callback.answer(get_text(user, "wm_not_found"), show_alert=True)
        return
    status = get_text(user, "wm_alerts_on") if wallet.alerts_enabled else get_text(user, "wm_alerts_off")
    await callback.answer(f"Alerts: {status}")
    await edit_panel(callback, get_text(user, "wm_alerts_updated"), wm_wallet_keyboard(user, wallet_id, wallet.alerts_enabled))


# ── Alert type settings ───────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("wm:alerts:"))
async def wm_alert_settings(callback: CallbackQuery, session: AsyncSession, user: User, services: ServiceContainer) -> None:
    wallet_id = int(callback.data.split(":")[-1])
    wallet = await services.wallet_manager.get_wallet(session, user.id, wallet_id)
    if wallet is None:
        await callback.answer(get_text(user, "wm_not_found"), show_alert=True)
        return

    cfg = services.wallet_manager.get_alert_config(wallet)
    await edit_panel(
        callback,
        get_text(user, "wm_alert_settings_title"),
        wm_alert_settings_keyboard(
            user, wallet_id, cfg.types, cfg.threshold,
            services.settings.WHALE_THRESHOLD_TON,
        ),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("wm:at:"))
async def wm_toggle_alert_type(callback: CallbackQuery, session: AsyncSession, user: User, services: ServiceContainer) -> None:
    parts = callback.data.split(":")
    wallet_id, alert_type = int(parts[2]), parts[3]
    wallet = await services.wallet_manager.toggle_alert_type(session, user.id, wallet_id, alert_type)
    if wallet is None:
        await callback.answer(get_text(user, "wm_not_found"), show_alert=True)
        return

    cfg = services.wallet_manager.get_alert_config(wallet)
    await callback.answer(f"{alert_type.upper()}: {'ON' if cfg.types.get(alert_type) else 'OFF'}")
    await edit_panel(
        callback,
        get_text(user, "wm_alert_settings_title"),
        wm_alert_settings_keyboard(
            user, wallet_id, cfg.types, cfg.threshold,
            services.settings.WHALE_THRESHOLD_TON,
        ),
    )


# ── Set threshold ─────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("wm:threshold:"))
async def wm_threshold_prompt(callback: CallbackQuery, state: FSMContext, user: User) -> None:
    wallet_id = int(callback.data.split(":")[-1])
    await state.set_state(WalletManagerStates.waiting_for_threshold)
    await state.update_data(wallet_id=wallet_id)
    await edit_panel(callback, get_text(user, "wm_threshold_prompt"), simple_refresh_keyboard(user, "wm"))
    await callback.answer()


@router.message(WalletManagerStates.waiting_for_threshold)
async def wm_threshold_input(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    services: ServiceContainer,
) -> None:
    raw = (message.text or "").strip().replace(",", ".")
    if not raw.replace(".", "", 1).isdigit() or float(raw) <= 0:
        await message.answer(get_text(user, "wm_threshold_invalid"))
        return

    data = await state.get_data()
    wallet_id = data.get("wallet_id")
    await services.wallet_manager.set_threshold(session, user.id, wallet_id, float(raw))
    await state.clear()
    await message.answer(
        get_text(user, "wm_threshold_set", amount=f"{float(raw):,.0f}"),
        reply_markup=simple_refresh_keyboard(user, "wm"),
    )


# ── Remove wallet ─────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("wm:rm_confirm:"))
async def wm_remove_confirm(callback: CallbackQuery, user: User) -> None:
    wallet_id = int(callback.data.split(":")[-1])
    await edit_panel(
        callback,
        get_text(user, "wm_remove_confirm"),
        wm_confirm_remove_keyboard(user, wallet_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("wm:rm:"))
async def wm_remove_execute(callback: CallbackQuery, session: AsyncSession, user: User, services: ServiceContainer) -> None:
    wallet_id = int(callback.data.split(":")[-1])
    removed = await services.wallet_manager.remove_wallet(session, user.id, wallet_id)
    if not removed:
        await callback.answer(get_text(user, "wm_not_found"), show_alert=True)
        return
    await callback.answer(get_text(user, "wm_removed"))
    await _show_main(callback, session, user, services)


# ── Quick analysis redirect ───────────────────────────────────────────────────

@router.callback_query(F.data.startswith("wm:analyze:"))
async def wm_analyze(callback: CallbackQuery, session: AsyncSession, user: User, services: ServiceContainer) -> None:
    wallet_id = int(callback.data.split(":")[-1])
    wallet = await services.wallet_manager.get_wallet(session, user.id, wallet_id)
    if wallet is None:
        await callback.answer(get_text(user, "wm_not_found"), show_alert=True)
        return

    await callback.answer(_LOADING)
    from bot.services.wallet_analytics import analyze_wallet_behavior
    from bot.utils.formatters import format_analysis
    from bot.keyboards.inline import wallet_analysis_keyboard

    behavior = await analyze_wallet_behavior(wallet.address, tonapi=services.tonapi, period_days=30)
    await edit_panel(callback, format_analysis(user, behavior), wallet_analysis_keyboard(user))
