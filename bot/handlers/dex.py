from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import User
from bot.database.repositories import UserRepository
from bot.handlers.common import edit_panel
from bot.keyboards.inline import (
    dex_keyboard,
    dex_risk_detail_keyboard,
    dex_risk_select_keyboard,
    dex_top_keyboard,
)
from bot.services.container import ServiceContainer
from bot.services.dex_screener import format_top_tokens, get_top_ton_tokens

router = Router(name="dex")


def _menu_text(user: User) -> str:
    state = "ON" if user.dex_alerts_enabled else "OFF"
    return (
        "<b>DEX Screener — TON</b>\n\n"
        "Top tokens · New listings · Risk analysis\n\n"
        f"Market cap alerts: <b>{state}</b>"
    )


# ── /dex  →  DEX menu ────────────────────────────────────────────────────────

@router.callback_query(F.data == "dex")
async def dex_menu_handler(callback: CallbackQuery, user: User) -> None:
    await edit_panel(callback, _menu_text(user), dex_keyboard(user, alerts_enabled=user.dex_alerts_enabled))
    await callback.answer()


# ── dex:top  /  /dex_top ─────────────────────────────────────────────────────

@router.callback_query(F.data == "dex:top")
async def dex_top_callback(callback: CallbackQuery, user: User) -> None:
    tokens = await get_top_ton_tokens()
    await edit_panel(callback, format_top_tokens(tokens), dex_top_keyboard(user))
    await callback.answer()


@router.message(Command("dex_top"))
async def cmd_dex_top(message: Message, user: User) -> None:
    tokens = await get_top_ton_tokens()
    await message.answer(
        format_top_tokens(tokens),
        reply_markup=dex_top_keyboard(user),
        parse_mode="HTML",
        disable_web_page_preview=True,
    )


# ── dex:alert_on / dex:alert_off  /  commands ────────────────────────────────

@router.callback_query(F.data.in_({"dex:alert_on", "dex:alert_off"}))
async def dex_alert_toggle_handler(
    callback: CallbackQuery, session: AsyncSession, user: User
) -> None:
    enabled = callback.data == "dex:alert_on"
    await UserRepository(session).set_dex_alerts_enabled(user, enabled)
    await edit_panel(callback, _menu_text(user), dex_keyboard(user, alerts_enabled=user.dex_alerts_enabled))
    status = "enabled" if enabled else "disabled"
    await callback.answer(f"DEX alerts {status}")


@router.message(Command("dex_alert_on"))
async def cmd_dex_alert_on(message: Message, session: AsyncSession, user: User) -> None:
    await UserRepository(session).set_dex_alerts_enabled(user, True)
    await message.answer("DEX market-cap alerts <b>enabled</b>.", parse_mode="HTML")


@router.message(Command("dex_alert_off"))
async def cmd_dex_alert_off(message: Message, session: AsyncSession, user: User) -> None:
    await UserRepository(session).set_dex_alerts_enabled(user, False)
    await message.answer("DEX market-cap alerts <b>disabled</b>.", parse_mode="HTML")


# ── dex:risk  →  token selector ──────────────────────────────────────────────

@router.callback_query(F.data == "dex:risk")
async def dex_risk_select_handler(callback: CallbackQuery, user: User) -> None:
    tokens = await get_top_ton_tokens()
    text = (
        "<b>Risk Analysis</b>\n\n"
        "Select a token to analyze its risk score, dev wallet, and market signals:"
    )
    await edit_panel(callback, text, dex_risk_select_keyboard(user, tokens))
    await callback.answer()


# ── dex:risk:{token_address}  →  full analysis ───────────────────────────────

@router.callback_query(F.data.startswith("dex:risk:"))
async def dex_risk_token_handler(
    callback: CallbackQuery, user: User, services: ServiceContainer
) -> None:
    token_address = callback.data.removeprefix("dex:risk:")
    if not token_address:
        await callback.answer("Invalid token address.")
        return

    await callback.answer("Analyzing…")

    # Use cached top-tokens list first to avoid an extra API call
    cached_tokens = await get_top_ton_tokens()
    token_data = next(
        (t for t in cached_tokens if t.get("address") == token_address), None
    )

    try:
        token, dev_data, risk = await services.risk.analyze_token(
            token_address=token_address if token_data is None else None,
            token_data=token_data,
        )
        text = services.risk.format_analysis(token, dev_data, risk)
    except Exception:
        text = (
            "<b>Risk Analysis</b>\n\n"
            "Unable to fetch token data at this time. Please try again."
        )

    await edit_panel(
        callback,
        text,
        dex_risk_detail_keyboard(user, token_address=token_address),
    )
