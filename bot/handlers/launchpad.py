from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from bot.database.models import User
from bot.handlers.common import edit_panel
from bot.keyboards.inline import (
    launchpad_listing_detail_keyboard,
    launchpad_listings_keyboard,
    launchpad_menu_keyboard,
    launchpad_risk_detail_keyboard,
    launchpad_risk_select_keyboard,
    launchpad_signals_keyboard,
    launchpad_strong_keyboard,
    launchpad_watchlist_add_keyboard,
    launchpad_watchlist_keyboard,
)
from bot.services.container import ServiceContainer

log = logging.getLogger(__name__)
router = Router(name="launchpad")

_CACHED_LISTINGS: dict[int, list] = {}  # chat_id -> last fetched listings for detail nav


class LaunchpadStates(StatesGroup):
    waiting_for_watchlist_address = State()


# ── /launchpad command ────────────────────────────────────────────────────────

@router.message(Command("launchpad"))
async def cmd_launchpad(message: Message, user: User) -> None:
    text = (
        "🚀 <b>Launchpad Assistant</b>\n\n"
        "Система анализа новых токенов TON:\n"
        "• New Listings — свежие пары\n"
        "• Strong Tokens — фильтр качества\n"
        "• Early Signals — ранний рост\n"
        "• Risk Analysis — оценка риска\n"
        "• Watchlist — список наблюдения"
    )
    await message.answer(
        text,
        reply_markup=launchpad_menu_keyboard(user),
        parse_mode="HTML",
        disable_web_page_preview=True,
    )


# ── dex:launchpad → Launchpad menu ────────────────────────────────────────────

@router.callback_query(F.data == "dex:launchpad")
async def launchpad_menu_callback(callback: CallbackQuery, user: User) -> None:
    text = (
        "🚀 <b>Launchpad Assistant</b>\n\n"
        "Система анализа новых токенов TON:\n"
        "• <b>New Listings</b> — свежие листинги (< 20 мин)\n"
        "• <b>Strong Tokens</b> — качественные токены\n"
        "• <b>Early Signals</b> — ранние сигналы роста\n"
        "• <b>Risk Analysis</b> — dev wallet + оценка риска\n"
        "• <b>Watchlist</b> — ваши токены"
    )
    await edit_panel(callback, text, launchpad_menu_keyboard(user))
    await callback.answer()


# ══════════════════════════════════════════════════════════════════════════════
# NEW LISTINGS
# ══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data.in_({"launchpad:listings", "launchpad:listings:refresh"}))
async def launchpad_listings_callback(
    callback: CallbackQuery, user: User, services: ServiceContainer
) -> None:
    await callback.answer("Загружаю…")
    tokens = await services.launchpad.get_new_tokens(max_items=10)
    _CACHED_LISTINGS[callback.message.chat.id] = tokens
    text = services.launchpad.format_summary(tokens)
    await edit_panel(callback, text, launchpad_listings_keyboard(user))


@router.message(Command("listing"))
async def cmd_listing(message: Message, services: ServiceContainer) -> None:
    tokens = await services.launchpad.get_new_tokens(max_items=10)
    _CACHED_LISTINGS[message.chat.id] = tokens
    await message.answer(
        services.launchpad.format_summary(tokens),
        reply_markup=launchpad_listings_keyboard(message),
        parse_mode="HTML",
        disable_web_page_preview=True,
    )


@router.callback_query(F.data.startswith("launchpad:listings:detail:"))
async def launchpad_listing_detail_callback(
    callback: CallbackQuery, user: User, services: ServiceContainer
) -> None:
    raw_index = callback.data.removeprefix("launchpad:listings:detail:")
    try:
        index = int(raw_index)
    except ValueError:
        await callback.answer("Некорректный индекс.")
        return

    await callback.answer("Загружаю…")
    tokens = _CACHED_LISTINGS.get(callback.message.chat.id) or await services.launchpad.get_new_tokens()
    if not tokens or index >= len(tokens):
        await edit_panel(
            callback,
            "<b>New Listings</b>\n\nТокен недоступен — список обновился.",
            launchpad_listings_keyboard(user),
        )
        return

    token = tokens[index]
    text = services.launchpad.format_single(token)
    await edit_panel(callback, text, launchpad_listing_detail_keyboard(user, index))


# ── backward-compat: old dex:listing callbacks ───────────────────────────────

@router.callback_query(F.data == "dex:listing")
async def dex_listing_compat(callback: CallbackQuery, user: User, services: ServiceContainer) -> None:
    await callback.answer("Загружаю…")
    tokens = await services.launchpad.get_new_tokens(max_items=10)
    _CACHED_LISTINGS[callback.message.chat.id] = tokens
    text = services.launchpad.format_summary(tokens)
    await edit_panel(callback, text, launchpad_listings_keyboard(user))


@router.callback_query(F.data == "dex:listing:refresh")
async def dex_listing_refresh_compat(callback: CallbackQuery, user: User, services: ServiceContainer) -> None:
    await callback.answer("Обновляю…")
    tokens = await services.launchpad.get_new_tokens(max_items=10)
    _CACHED_LISTINGS[callback.message.chat.id] = tokens
    text = services.launchpad.format_summary(tokens)
    await edit_panel(callback, text, launchpad_listings_keyboard(user))


@router.callback_query(F.data.startswith("dex:listing:detail:"))
async def dex_listing_detail_compat(
    callback: CallbackQuery, user: User, services: ServiceContainer
) -> None:
    raw_index = callback.data.removeprefix("dex:listing:detail:")
    try:
        index = int(raw_index)
    except ValueError:
        await callback.answer("Некорректный индекс.")
        return
    await callback.answer("Загружаю…")
    tokens = _CACHED_LISTINGS.get(callback.message.chat.id) or await services.launchpad.get_new_tokens()
    if not tokens or index >= len(tokens):
        await edit_panel(callback, "<b>New Listings</b>\n\nТокен недоступен.", launchpad_listings_keyboard(user))
        return
    text = services.launchpad.format_single(tokens[index])
    await edit_panel(callback, text, launchpad_listing_detail_keyboard(user, index))


# ══════════════════════════════════════════════════════════════════════════════
# STRONG TOKENS
# ══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data.in_({"launchpad:strong", "launchpad:strong:refresh"}))
async def launchpad_strong_callback(
    callback: CallbackQuery, user: User, services: ServiceContainer
) -> None:
    await callback.answer("Фильтрую…")
    tokens = await services.launchpad.get_new_tokens(max_items=50)
    strong = services.launchpad.get_strong_tokens(tokens)
    text = services.launchpad.format_strong_tokens(strong)
    await edit_panel(callback, text, launchpad_strong_keyboard(user))


# ══════════════════════════════════════════════════════════════════════════════
# EARLY SIGNALS
# ══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data.in_({"launchpad:signals", "launchpad:signals:refresh"}))
async def launchpad_signals_callback(
    callback: CallbackQuery, user: User, services: ServiceContainer
) -> None:
    await callback.answer("Анализирую сигналы…")
    tokens = await services.launchpad.get_new_tokens(max_items=50)
    signals = services.launchpad.get_early_signals(tokens)
    text = services.launchpad.format_signals(signals)
    await edit_panel(callback, text, launchpad_signals_keyboard(user))


# ══════════════════════════════════════════════════════════════════════════════
# RISK ANALYSIS
# ══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "launchpad:risk")
async def launchpad_risk_select_callback(
    callback: CallbackQuery, user: User, services: ServiceContainer
) -> None:
    await callback.answer()
    tokens = await services.launchpad.get_new_tokens(max_items=10)
    text = (
        "<b>⚠️ Risk Analysis</b>\n\n"
        "Выберите токен из последних листингов для полного анализа\n"
        "(dev wallet + risk score + вывод):"
    )
    await edit_panel(callback, text, launchpad_risk_select_keyboard(user, tokens))


@router.callback_query(F.data.startswith("launchpad:risk:idx:"))
async def launchpad_risk_by_index_callback(
    callback: CallbackQuery, user: User, services: ServiceContainer
) -> None:
    raw_index = callback.data.removeprefix("launchpad:risk:idx:")
    try:
        index = int(raw_index)
    except ValueError:
        await callback.answer("Некорректный индекс.")
        return

    await callback.answer("Анализирую…")
    tokens = _CACHED_LISTINGS.get(callback.message.chat.id) or await services.launchpad.get_new_tokens()
    if not tokens or index >= len(tokens):
        await edit_panel(
            callback,
            "<b>Risk Analysis</b>\n\nТокен не найден в кэше. Обновите список.",
            launchpad_risk_select_keyboard(user, []),
        )
        return

    token = tokens[index]
    await _run_full_analysis(callback, user, services, token)


@router.callback_query(F.data.startswith("launchpad:risk:"))
async def launchpad_risk_token_callback(
    callback: CallbackQuery, user: User, services: ServiceContainer
) -> None:
    token_address = callback.data.removeprefix("launchpad:risk:")
    if not token_address or token_address.startswith("idx:"):
        return

    await callback.answer("Анализирую…")

    # Try cache first, then fall back to DexScreener lookup via RiskService
    cached_tokens = _CACHED_LISTINGS.get(callback.message.chat.id) or []
    token_data = next((t for t in cached_tokens if t.get("address") == token_address), None)

    try:
        if token_data:
            result = await services.launchpad.build_token_analysis(token_data)
        else:
            token_metrics, dev_data, risk = await services.risk.analyze_token(token_address=token_address)
            from bot.services.launchpad.signals import SignalsService
            _svc = SignalsService()
            signal_results = _svc.detect_early_signals([token_metrics])
            signal = signal_results[0][1] if signal_results else None
            is_strong = bool(_svc.filter_strong_tokens([token_metrics]))
            from bot.services.launchpad.service import _make_conclusion
            conclusion = _make_conclusion(signal, risk)
            result = {
                "token": token_metrics, "dev": dev_data, "risk": risk,
                "signal": signal, "is_strong": is_strong, "conclusion": conclusion,
            }
        text = services.launchpad.format_full_analysis(result)
    except Exception:
        log.exception("Full analysis failed for %s", token_address)
        text = "<b>Risk Analysis</b>\n\nНе удалось получить данные. Попробуйте позже."

    await edit_panel(callback, text, launchpad_risk_detail_keyboard(user, token_address=token_address))


async def _run_full_analysis(
    callback: CallbackQuery,
    user: User,
    services: ServiceContainer,
    token: dict,
) -> None:
    try:
        result = await services.launchpad.build_token_analysis(token)
        text = services.launchpad.format_full_analysis(result)
    except Exception:
        log.exception("Full analysis failed for token %s", token.get("address"))
        text = "<b>Risk Analysis</b>\n\nОшибка анализа. Попробуйте позже."
    addr = token.get("address") or ""
    await edit_panel(callback, text, launchpad_risk_detail_keyboard(user, token_address=addr))


# ══════════════════════════════════════════════════════════════════════════════
# WATCHLIST
# ══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "launchpad:watchlist")
async def launchpad_watchlist_callback(
    callback: CallbackQuery, user: User, services: ServiceContainer
) -> None:
    await callback.answer()
    addresses = services.launchpad.watchlist_list(user.id)
    count = len(addresses)
    text = (
        f"📌 <b>Watchlist</b>\n\n"
        f"Отслеживаемых токенов: <b>{count}</b>\n\n"
        + ("\n".join(f"• <code>{a}</code>" for a in addresses)
           if addresses else "<i>Список пуст. Добавьте токен для отслеживания.</i>")
    )
    await edit_panel(callback, text, launchpad_watchlist_keyboard(user, addresses))


@router.callback_query(F.data == "launchpad:wl:add")
async def launchpad_wl_add_prompt(
    callback: CallbackQuery, user: User, state: FSMContext
) -> None:
    await callback.answer()
    await state.set_state(LaunchpadStates.waiting_for_watchlist_address)
    await callback.message.answer(
        "📌 <b>Добавить токен в Watchlist</b>\n\n"
        "Отправьте адрес контракта токена TON:",
        reply_markup=launchpad_watchlist_add_keyboard(user),
        parse_mode="HTML",
    )


@router.message(StateFilter(LaunchpadStates.waiting_for_watchlist_address))
async def launchpad_wl_add_receive(
    message: Message, user: User, services: ServiceContainer, state: FSMContext
) -> None:
    await state.clear()
    address = (message.text or "").strip()

    if not address:
        await message.answer("Некорректный адрес. Операция отменена.")
        return

    added = services.launchpad.watchlist_add(user.id, address)
    if not added:
        await message.answer(
            "❌ Достигнут лимит Watchlist (20 токенов). Удалите неиспользуемые адреса.",
            parse_mode="HTML",
        )
        return

    addresses = services.launchpad.watchlist_list(user.id)
    text = (
        f"✅ <b>Токен добавлен</b>\n\n"
        f"<code>{address}</code>\n\n"
        f"Всего в списке: {len(addresses)}"
    )
    await message.answer(
        text,
        reply_markup=launchpad_watchlist_keyboard(user, addresses),
        parse_mode="HTML",
        disable_web_page_preview=True,
    )


@router.callback_query(F.data.startswith("launchpad:wl:rm:"))
async def launchpad_wl_remove_callback(
    callback: CallbackQuery, user: User, services: ServiceContainer
) -> None:
    address = callback.data.removeprefix("launchpad:wl:rm:")
    removed = services.launchpad.watchlist_remove(user.id, address)
    if removed:
        await callback.answer("Удалено.")
    else:
        await callback.answer("Адрес не найден.", show_alert=True)
        return

    addresses = services.launchpad.watchlist_list(user.id)
    count = len(addresses)
    text = (
        f"📌 <b>Watchlist</b>\n\n"
        f"Отслеживаемых токенов: <b>{count}</b>\n\n"
        + ("\n".join(f"• <code>{a}</code>" for a in addresses)
           if addresses else "<i>Список пуст.</i>")
    )
    await edit_panel(callback, text, launchpad_watchlist_keyboard(user, addresses))


@router.callback_query(F.data.startswith("launchpad:wl:info:"))
async def launchpad_wl_info_callback(
    callback: CallbackQuery, user: User, services: ServiceContainer
) -> None:
    address = callback.data.removeprefix("launchpad:wl:info:")
    await callback.answer("Анализирую…")
    try:
        token_metrics, dev_data, risk = await services.risk.analyze_token(token_address=address)
        from bot.services.launchpad.service import _make_conclusion
        from bot.services.launchpad.signals import SignalsService
        _svc = SignalsService()
        signal_results = _svc.detect_early_signals([token_metrics])
        signal = signal_results[0][1] if signal_results else None
        is_strong = bool(_svc.filter_strong_tokens([token_metrics]))
        conclusion = _make_conclusion(signal, risk)
        result = {
            "token": token_metrics, "dev": dev_data, "risk": risk,
            "signal": signal, "is_strong": is_strong, "conclusion": conclusion,
        }
        text = services.launchpad.format_full_analysis(result)
    except Exception:
        log.exception("Watchlist analysis failed for %s", address)
        text = "<b>Analysis</b>\n\nНе удалось получить данные."
    await edit_panel(callback, text, launchpad_risk_detail_keyboard(user, token_address=address))
