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
    admin_wm_list_keyboard,
    admin_wm_wallet_keyboard,
    simple_refresh_keyboard,
)
from bot.services.container import ServiceContainer
from bot.services.i18n import get_text
from bot.states import AdminStates
from bot.utils.formatters import format_admin_wallet_detail, format_admin_wallet_list

log = logging.getLogger(__name__)
router = Router(name="admin_wallets")


def _is_admin(user: User, services: ServiceContainer) -> bool:
    return user.telegram_id in services.settings.ADMIN_IDS


# ── Admin wallet list ─────────────────────────────────────────────────────────

@router.message(Command("admin_wm"))
async def admin_wm_command(message: Message, session: AsyncSession, user: User, services: ServiceContainer) -> None:
    if not _is_admin(user, services):
        return
    entries = await services.wallet_manager.admin_list_wallets(session)
    await message.answer(
        format_admin_wallet_list(user, entries, flagged_only=False),
        reply_markup=admin_wm_list_keyboard(user),
    )


@router.callback_query(F.data == "admin:wm")
async def admin_wm_list(callback: CallbackQuery, session: AsyncSession, user: User, services: ServiceContainer) -> None:
    if not _is_admin(user, services):
        await callback.answer("Unauthorized", show_alert=True)
        return
    entries = await services.wallet_manager.admin_list_wallets(session)
    await edit_panel(
        callback,
        format_admin_wallet_list(user, entries, flagged_only=False),
        admin_wm_list_keyboard(user, flagged_only=False),
    )
    await callback.answer()


@router.callback_query(F.data == "admin:wm:flagged")
async def admin_wm_flagged(callback: CallbackQuery, session: AsyncSession, user: User, services: ServiceContainer) -> None:
    if not _is_admin(user, services):
        await callback.answer("Unauthorized", show_alert=True)
        return
    entries = await services.wallet_manager.admin_list_wallets(session, flagged_only=True)
    await edit_panel(
        callback,
        format_admin_wallet_list(user, entries, flagged_only=True),
        admin_wm_list_keyboard(user, flagged_only=True),
    )
    await callback.answer()


# ── Admin: open wallet by /awm_{id} command ───────────────────────────────────

@router.message(Command(commands=["awm"]))
async def admin_open_wallet_cmd(message: Message, session: AsyncSession, user: User, services: ServiceContainer) -> None:
    if not _is_admin(user, services):
        return
    parts = (message.text or "").split("_", maxsplit=1)
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("Usage: /awm_123")
        return
    wallet_id = int(parts[1])
    row = await services.wallet_manager.admin_get_wallet_by_id(session, wallet_id)
    if row is None:
        await message.answer("Wallet not found.")
        return
    wallet, tg_id, username = row
    await message.answer(
        format_admin_wallet_detail(user, wallet, tg_id, username),
        reply_markup=admin_wm_wallet_keyboard(user, wallet.id, wallet.flagged),
    )


# ── Admin: wallet detail panel ────────────────────────────────────────────────

@router.callback_query(F.data.startswith("admin:wm:w:"))
async def admin_wallet_detail(callback: CallbackQuery, session: AsyncSession, user: User, services: ServiceContainer) -> None:
    if not _is_admin(user, services):
        await callback.answer("Unauthorized", show_alert=True)
        return
    wallet_id = int(callback.data.split(":")[-1])
    row = await services.wallet_manager.admin_get_wallet_by_id(session, wallet_id)
    if row is None:
        await callback.answer("Not found", show_alert=True)
        return
    wallet, tg_id, username = row
    await edit_panel(
        callback,
        format_admin_wallet_detail(user, wallet, tg_id, username),
        admin_wm_wallet_keyboard(user, wallet.id, wallet.flagged),
    )
    await callback.answer()


# ── Admin: flag / unflag ──────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("admin:wm:flag:"))
async def admin_toggle_flag(callback: CallbackQuery, session: AsyncSession, user: User, services: ServiceContainer) -> None:
    if not _is_admin(user, services):
        await callback.answer("Unauthorized", show_alert=True)
        return
    wallet_id = int(callback.data.split(":")[-1])
    wallet = await services.wallet_manager.admin_toggle_flag(session, wallet_id)
    if wallet is None:
        await callback.answer("Not found", show_alert=True)
        return
    state = "FLAGGED" if wallet.flagged else "CLEAN"
    await callback.answer(f"Wallet: {state}")
    row = await services.wallet_manager.admin_get_wallet_by_id(session, wallet_id)
    if row:
        wallet, tg_id, username = row
        await edit_panel(
            callback,
            format_admin_wallet_detail(user, wallet, tg_id, username),
            admin_wm_wallet_keyboard(user, wallet_id, wallet.flagged),
        )


# ── Admin: add note ───────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("admin:wm:note:"))
async def admin_note_prompt(callback: CallbackQuery, state: FSMContext, user: User) -> None:
    wallet_id = int(callback.data.split(":")[-1])
    await state.set_state(AdminStates.waiting_for_note)
    await state.update_data(wallet_id=wallet_id)
    await edit_panel(
        callback,
        "Send a note for this wallet (or 'clear' to remove):",
        simple_refresh_keyboard(user, "admin:wm"),
    )
    await callback.answer()


@router.message(AdminStates.waiting_for_note)
async def admin_note_input(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    services: ServiceContainer,
) -> None:
    if not _is_admin(user, services):
        return
    data = await state.get_data()
    wallet_id = data.get("wallet_id")
    note = (message.text or "").strip()
    if note.lower() == "clear":
        note = ""
    await services.wallet_manager.admin_set_note(session, wallet_id, note)
    await state.clear()
    await message.answer("Note saved.", reply_markup=simple_refresh_keyboard(user, "admin:wm"))


# ── Admin: risk override ──────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("admin:wm:risk:"))
async def admin_risk_override(callback: CallbackQuery, session: AsyncSession, user: User, services: ServiceContainer) -> None:
    if not _is_admin(user, services):
        await callback.answer("Unauthorized", show_alert=True)
        return
    parts = callback.data.split(":")
    wallet_id, level = int(parts[3]), parts[4]
    override = None if level == "CLEAR" else level
    wallet = await services.wallet_manager.admin_set_risk_override(session, wallet_id, override)
    if wallet is None:
        await callback.answer("Not found", show_alert=True)
        return
    await callback.answer(f"Risk override: {override or 'cleared'}")
    row = await services.wallet_manager.admin_get_wallet_by_id(session, wallet_id)
    if row:
        wallet, tg_id, username = row
        await edit_panel(
            callback,
            format_admin_wallet_detail(user, wallet, tg_id, username),
            admin_wm_wallet_keyboard(user, wallet_id, wallet.flagged),
        )


# ── Admin: remove wallet ──────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("admin:wm:rm:"))
async def admin_remove_wallet(callback: CallbackQuery, session: AsyncSession, user: User, services: ServiceContainer) -> None:
    if not _is_admin(user, services):
        await callback.answer("Unauthorized", show_alert=True)
        return
    wallet_id = int(callback.data.split(":")[-1])
    removed = await services.wallet_manager.admin_remove_wallet(session, wallet_id)
    if not removed:
        await callback.answer("Not found", show_alert=True)
        return
    await callback.answer("Wallet removed.")
    entries = await services.wallet_manager.admin_list_wallets(session)
    await edit_panel(
        callback,
        format_admin_wallet_list(user, entries, flagged_only=False),
        admin_wm_list_keyboard(user),
    )
