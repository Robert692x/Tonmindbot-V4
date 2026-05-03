from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import User
from bot.handlers.common import edit_panel
from bot.keyboards.inline import simple_refresh_keyboard, watchlist_add_keyboard, watchlist_keyboard
from bot.services.container import ServiceContainer
from bot.services.watchlist import WalletAlreadyExistsError, WatchlistLimitError
from bot.states import WatchlistStates
from bot.utils.formatters import format_watchlist

log = logging.getLogger(__name__)
router = Router(name="watchlist")


async def _show_watchlist(
    target: CallbackQuery | Message,
    session: AsyncSession,
    user: User,
    services: ServiceContainer,
) -> None:
    wallets = await services.watchlist.get_user_wallets(session, user.id)
    text = format_watchlist(wallets)
    kb = watchlist_keyboard(user, wallets)
    if isinstance(target, CallbackQuery):
        await edit_panel(target, text, kb)
    else:
        await target.answer(text, reply_markup=kb)


# ── Menu ──────────────────────────────────────────────────────────────────────

@router.message(Command("watchlist", "wallets"))
async def watchlist_command_handler(
    message: Message, state: FSMContext, session: AsyncSession, user: User, services: ServiceContainer
) -> None:
    await state.clear()
    await _show_watchlist(message, session, user, services)


# ── /add_wallet <address> [label] ─────────────────────────────────────────────

@router.message(Command("add_wallet"))
async def add_wallet_command_handler(
    message: Message,
    session: AsyncSession,
    user: User,
    services: ServiceContainer,
) -> None:
    raw = (message.text or "").split(maxsplit=1)
    if len(raw) < 2:
        await message.answer(
            "Usage: <code>/add_wallet EQabc...123 [optional label]</code>"
        )
        return

    parts = raw[1].strip().split(maxsplit=1)
    address = parts[0]
    label = parts[1].strip() if len(parts) > 1 else None

    if not services.tonapi.is_probable_address(address):
        await message.answer("Invalid TON address.")
        return

    try:
        await services.watchlist.add_wallet(session, user.id, address, label)
    except WalletAlreadyExistsError:
        await message.answer("This address is already in your watchlist.")
        return
    except WatchlistLimitError as exc:
        await message.answer(str(exc))
        return

    label_note = f"\nLabel: <b>{label}</b>" if label else ""
    await message.answer(
        f"Wallet added.\n\n<code>{address}</code>{label_note}\nAlerts: ON",
        reply_markup=simple_refresh_keyboard(user, "watchlist"),
    )


# ── /remove_wallet <address> ──────────────────────────────────────────────────

@router.message(Command("remove_wallet"))
async def remove_wallet_command_handler(
    message: Message,
    session: AsyncSession,
    user: User,
    services: ServiceContainer,
) -> None:
    raw = (message.text or "").split(maxsplit=1)
    if len(raw) < 2:
        await message.answer("Usage: <code>/remove_wallet EQabc...123</code>")
        return

    address = raw[1].strip()
    if not services.tonapi.is_probable_address(address):
        await message.answer("Invalid TON address.")
        return

    removed = await services.watchlist.remove_by_address(session, user.id, address)
    if not removed:
        await message.answer("Wallet not found in your watchlist.")
        return

    await message.answer(
        f"🗑 Wallet removed.\n<code>{address}</code>",
        reply_markup=simple_refresh_keyboard(user, "watchlist"),
    )


# ── /rename_wallet <address> <label> ─────────────────────────────────────────

@router.message(Command("rename_wallet"))
async def rename_wallet_command_handler(
    message: Message,
    session: AsyncSession,
    user: User,
    services: ServiceContainer,
) -> None:
    raw = (message.text or "").split(maxsplit=1)
    if len(raw) < 2:
        await message.answer(
            "Usage: <code>/rename_wallet EQabc...123 New label</code>"
        )
        return

    parts = raw[1].strip().split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(
            "Usage: <code>/rename_wallet EQabc...123 New label</code>"
        )
        return

    address, label = parts[0], parts[1].strip()

    if not services.tonapi.is_probable_address(address):
        await message.answer("Invalid TON address.")
        return

    wallet = await services.watchlist.rename_wallet(session, user.id, address, label)
    if wallet is None:
        await message.answer("Wallet not found in your watchlist.")
        return

    await message.answer(
        f"✏️ Wallet renamed.\n<code>{address}</code>\nNew label: <b>{label}</b>",
        reply_markup=simple_refresh_keyboard(user, "watchlist"),
    )


@router.callback_query(F.data == "watchlist")
async def watchlist_callback_handler(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, user: User, services: ServiceContainer
) -> None:
    await state.clear()
    await _show_watchlist(callback, session, user, services)
    await callback.answer()


# ── Add wallet ────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "watchlist:add")
async def watchlist_add_prompt_handler(
    callback: CallbackQuery, state: FSMContext, user: User
) -> None:
    await state.set_state(WatchlistStates.waiting_for_address)
    await edit_panel(
        callback,
        "Send the wallet address to monitor.\n\n"
        "Optionally add a label after the address:\n"
        "<code>EQabc...123</code>\n"
        "<code>EQabc...123  My wallet</code>",
        watchlist_add_keyboard(user),
    )
    await callback.answer()


@router.message(WatchlistStates.waiting_for_address)
async def watchlist_add_input_handler(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    services: ServiceContainer,
) -> None:
    raw = (message.text or "").strip()
    parts = raw.split(maxsplit=1)
    address = parts[0]
    label = parts[1].strip() if len(parts) > 1 else None

    if not services.tonapi.is_probable_address(address):
        await message.answer(
            "Invalid TON address. Send an <code>EQ...</code> or <code>UQ...</code> address."
        )
        return

    try:
        wallet = await services.watchlist.add_wallet(session, user.id, address, label)
    except WalletAlreadyExistsError:
        await message.answer("This address is already in your watchlist.")
        return
    except WatchlistLimitError as exc:
        await message.answer(str(exc))
        return

    await state.clear()
    label_line = f"\nLabel: {label}" if label else ""
    await message.answer(
        f"Wallet added.\n\nAddress: {address}{label_line}\nAlerts: ON",
        reply_markup=simple_refresh_keyboard(user, "watchlist"),
    )


# ── Toggle alerts ─────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("watchlist:toggle:"))
async def watchlist_toggle_handler(
    callback: CallbackQuery,
    session: AsyncSession,
    user: User,
    services: ServiceContainer,
) -> None:
    wallet_id = int(callback.data.rsplit(":", 1)[-1])
    wallet = await services.watchlist.toggle_alerts(
        session, user.id, wallet_id, enabled=True  # will be set below
    )
    if wallet is None:
        await callback.answer("Wallet not found.", show_alert=True)
        return

    # Actual toggle: flip current state
    wallet.alerts_enabled = not wallet.alerts_enabled
    status = "ON" if wallet.alerts_enabled else "OFF"
    await callback.answer(f"Alerts {status}")
    await _show_watchlist(callback, session, user, services)


# ── Remove wallet ─────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("watchlist:remove:"))
async def watchlist_remove_handler(
    callback: CallbackQuery,
    session: AsyncSession,
    user: User,
    services: ServiceContainer,
) -> None:
    wallet_id = int(callback.data.rsplit(":", 1)[-1])
    removed = await services.watchlist.remove_wallet(session, user.id, wallet_id)
    if not removed:
        await callback.answer("Wallet not found.", show_alert=True)
        return
    await callback.answer("Wallet removed.")
    await _show_watchlist(callback, session, user, services)
