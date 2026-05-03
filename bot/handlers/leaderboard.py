from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.database.models import User
from bot.handlers.common import edit_panel
from bot.keyboards.inline import leaderboard_keyboard, leaderboard_search_keyboard
from bot.services.container import ServiceContainer
from bot.services.i18n import get_text
from bot.services.leaderboard import (
    get_active_token,
    get_token_holders,
    set_active_token,
)
from bot.states import LeaderboardStates
from bot.utils.formatters import format_token_leaderboard

log = logging.getLogger(__name__)
router = Router(name="leaderboard")

_LOADING = "Loading..."


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _show_leaderboard(
    target: CallbackQuery | Message,
    user: User,
    services: ServiceContainer,
    token_address: str,
) -> None:
    try:
        lb = await get_token_holders(
            token_address,
            tonapi=services.tonapi,
            cache=services.cache,
            limit=10,
        )
        text = format_token_leaderboard(
            user,
            lb.token_address,
            lb.symbol,
            lb.total_supply,
            lb.holders,
        )
    except Exception as exc:
        log.warning("Leaderboard fetch failed for %s: %s", token_address, exc)
        text = get_text(user, "lb_fetch_error")

    kb = leaderboard_keyboard(user)
    if isinstance(target, CallbackQuery):
        await edit_panel(target, text, kb)
    else:
        await target.answer(text, reply_markup=kb)


# ── Main leaderboard screen ───────────────────────────────────────────────────

@router.callback_query(F.data == "leaderboard")
async def leaderboard_handler(
    callback: CallbackQuery, user: User, services: ServiceContainer
) -> None:
    await callback.answer(_LOADING)
    # Use the user's persisted token (defaults to ALGO if never set).
    token_address = await get_active_token(
        user.id,
        cache=services.cache,
        default=services.settings.ALGO_JETTON_ADDRESS,
    )
    await _show_leaderboard(callback, user, services, token_address)


# ── Token search ──────────────────────────────────────────────────────────────

@router.callback_query(F.data == "leaderboard:search")
async def leaderboard_search_prompt(
    callback: CallbackQuery, state: FSMContext, user: User
) -> None:
    await state.set_state(LeaderboardStates.waiting_for_token_address)
    await edit_panel(
        callback,
        get_text(user, "lb_search_prompt"),
        leaderboard_search_keyboard(user),
    )
    await callback.answer()


@router.message(LeaderboardStates.waiting_for_token_address)
async def leaderboard_token_input(
    message: Message,
    state: FSMContext,
    user: User,
    services: ServiceContainer,
) -> None:
    address = (message.text or "").strip()

    if not services.tonapi.is_probable_address(address):
        await message.answer(get_text(user, "lb_invalid_address"))
        return

    # Validate by trying to fetch metadata
    try:
        await services.tonapi.get_jetton_metadata(address)
    except Exception:
        await message.answer(get_text(user, "lb_invalid_token"))
        return

    # Persist the chosen token — survives navigation
    await set_active_token(user.id, address, cache=services.cache)
    await state.clear()

    await _show_leaderboard(message, user, services, address)
