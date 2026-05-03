from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import User
from bot.database.repositories import UserRepository
from bot.handlers.common import edit_panel
from bot.keyboards.inline import alerts_keyboard, simple_refresh_keyboard
from bot.services.container import ServiceContainer
from bot.services.i18n import get_text

router = Router(name="alerts")

_THRESHOLD_CACHE_TTL = 60 * 60 * 24 * 30  # 30 days


def _alerts_text(subject: object) -> str:
    return f"{get_text(subject, 'alerts_title')}\n{get_text(subject, 'alerts_description')}"


@router.callback_query(F.data == "alerts")
async def alerts_handler(callback: CallbackQuery, user: User) -> None:
    await edit_panel(
        callback,
        _alerts_text(user),
        alerts_keyboard(
            user,
            price_enabled=user.price_alerts_enabled,
            whale_enabled=user.whale_alerts_enabled,
            signals_enabled=user.signals_enabled,
            is_premium=user.is_premium,
        ),
    )
    await callback.answer()


@router.callback_query(F.data.in_({"alerts:price", "alerts:whale", "alerts:signals"}))
async def alerts_toggle_handler(callback: CallbackQuery, session: AsyncSession, user: User) -> None:
    repository = UserRepository(session)

    if callback.data == "alerts:price":
        await repository.set_alert_preferences(user, price_alerts_enabled=not user.price_alerts_enabled)
    elif callback.data == "alerts:whale":
        if not user.is_premium:
            await callback.answer(get_text(user, "alerts_whale_premium_only"), show_alert=True)
            return
        await repository.set_alert_preferences(user, whale_alerts_enabled=not user.whale_alerts_enabled)
    elif callback.data == "alerts:signals":
        if not user.is_premium:
            await callback.answer(get_text(user, "alerts_signals_premium_only"), show_alert=True)
            return
        await repository.set_alert_preferences(user, signals_enabled=not user.signals_enabled)

    await edit_panel(
        callback,
        _alerts_text(user),
        alerts_keyboard(
            user,
            price_enabled=user.price_alerts_enabled,
            whale_enabled=user.whale_alerts_enabled,
            signals_enabled=user.signals_enabled,
            is_premium=user.is_premium,
        ),
    )
    await callback.answer(get_text(user, "alerts_updated"))


# ── /alerts_on ────────────────────────────────────────────────────────────────

@router.message(Command("alerts_on"))
async def cmd_alerts_on(message: Message, session: AsyncSession, user: User) -> None:
    repo = UserRepository(session)
    await repo.set_alert_preferences(user, price_alerts_enabled=True)
    if user.is_premium:
        await repo.set_alert_preferences(user, whale_alerts_enabled=True, signals_enabled=True)
    await message.answer(
        get_text(user, "cmd_alerts_on_ok"),
        reply_markup=simple_refresh_keyboard(user, "alerts"),
    )


# ── /alerts_off ───────────────────────────────────────────────────────────────

@router.message(Command("alerts_off"))
async def cmd_alerts_off(message: Message, session: AsyncSession, user: User) -> None:
    await UserRepository(session).set_alert_preferences(
        user,
        price_alerts_enabled=False,
        whale_alerts_enabled=False,
        signals_enabled=False,
    )
    await message.answer(
        get_text(user, "cmd_alerts_off_ok"),
        reply_markup=simple_refresh_keyboard(user, "alerts"),
    )


# ── /set_threshold <amount> ───────────────────────────────────────────────────

@router.message(Command("set_threshold"))
async def cmd_set_threshold(
    message: Message, user: User, services: ServiceContainer
) -> None:
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip().replace(".", "", 1).isdigit():
        await message.answer(get_text(user, "cmd_threshold_invalid"))
        return

    amount = float(parts[1].strip())
    if amount <= 0:
        await message.answer(get_text(user, "cmd_threshold_invalid"))
        return

    cache_key = f"alert_threshold:{user.id}"
    await services.cache.set_json(cache_key, {"threshold": amount}, _THRESHOLD_CACHE_TTL)
    await message.answer(
        get_text(user, "cmd_threshold_set", amount=f"{amount:,.0f}"),
        reply_markup=simple_refresh_keyboard(user, "alerts"),
    )


# ── /alerts_settings ──────────────────────────────────────────────────────────

@router.message(Command("alerts_settings"))
async def cmd_alerts_settings(
    message: Message, user: User, services: ServiceContainer
) -> None:
    cache_key = f"alert_threshold:{user.id}"
    cached = await services.cache.get_json(cache_key)
    threshold = cached["threshold"] if cached else services.settings.WHALE_THRESHOLD_TON

    text = "\n".join([
        get_text(user, "alerts_title"),
        get_text(user, "alerts_description"),
        "",
        f"Price alerts:   {'ON' if user.price_alerts_enabled else 'OFF'}",
        f"Whale alerts:   {'ON' if user.whale_alerts_enabled else 'OFF'}",
        f"Signals:        {'ON' if user.signals_enabled else 'OFF'}",
        f"Whale threshold: {threshold:,.0f} TON",
    ])
    await message.answer(text, reply_markup=simple_refresh_keyboard(user, "alerts"))
