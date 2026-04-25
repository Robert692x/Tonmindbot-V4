import logging
from aiogram import F, Router
from aiogram.types import CallbackQuery
from bot.database.crud import (get_user, check_premium, create_payment,
                                get_pending_payments, set_language)
from bot.database.db import get_session
from bot.keyboards.keyboards import (
    main_menu_kb, profile_kb, premium_kb, premium_pay_kb,
    whales_kb, dex_kb, alerts_kb, analytics_kb, price_kb, back_kb
)
from bot.services.ton_service import ton_service
from bot.services.price_service import get_ston_pools
from bot.utils.texts import (
    profile_text, premium_text, whales_text, dex_text,
    price_text, analytics_text, START_RU, START_EN
)
from config import settings

log = logging.getLogger(__name__)
router = Router()


# ── MENU ──────────────────────────────────────────────────────

@router.callback_query(F.data == "menu")
async def cb_menu(cb: CallbackQuery):
    async with get_session() as session:
        user = await get_user(session, cb.from_user.id)
    lang = user.language if user else "ru"
    text = START_RU if lang == "ru" else START_EN
    await cb.message.edit_text(text, reply_markup=main_menu_kb(lang))
    await cb.answer()


# ── LANGUAGE ──────────────────────────────────────────────────

@router.callback_query(F.data.in_({"lang_ru", "lang_en"}))
async def cb_lang(cb: CallbackQuery):
    lang = "en" if cb.data == "lang_en" else "ru"
    async with get_session() as session:
        await set_language(session, cb.from_user.id, lang)
    text = START_RU if lang == "ru" else START_EN
    await cb.message.edit_text(text, reply_markup=main_menu_kb(lang))
    await cb.answer("🌐 Language changed" if lang == "en" else "🌐 Язык изменён")


# ── PROFILE ───────────────────────────────────────────────────

@router.callback_query(F.data == "profile")
async def cb_profile(cb: CallbackQuery):
    async with get_session() as session:
        user = await get_user(session, cb.from_user.id)
        user = await check_premium(session, user)
    lang = user.language
    await cb.message.edit_text(profile_text(user, lang), reply_markup=profile_kb(lang))
    await cb.answer()


# ── PREMIUM ───────────────────────────────────────────────────

@router.callback_query(F.data == "premium")
async def cb_premium(cb: CallbackQuery):
    async with get_session() as session:
        user = await get_user(session, cb.from_user.id)
        payment = await create_payment(session, user)
    lang = user.language
    text = premium_text(payment.memo, lang)
    await cb.message.edit_text(text, reply_markup=premium_pay_kb(payment.memo, lang))
    await cb.answer()


@router.callback_query(F.data.startswith("verify_pay:"))
async def cb_verify_pay(cb: CallbackQuery):
    memo = cb.data.split(":", 1)[1]
    async with get_session() as session:
        user = await get_user(session, cb.from_user.id)
    lang = user.language if user else "ru"
    tx = await ton_service.find_payment(
        settings.TON_WALLET, memo, settings.PREMIUM_PRICE_TON
    )
    if tx:
        await cb.answer("✅ Найдено! Активирую...", show_alert=True)
    else:
        msg = (
            "⏳ Транзакция не найдена.\nПроверь что указал комментарий!"
            if lang == "ru" else
            "⏳ Transaction not found.\nMake sure you included the comment!"
        )
        await cb.answer(msg, show_alert=True)


@router.callback_query(F.data == "check_algo")
async def cb_check_algo(cb: CallbackQuery):
    async with get_session() as session:
        user = await get_user(session, cb.from_user.id)
    lang = user.language
    if not user.ton_wallet:
        msg = "Подключи кошелёк сначала" if lang == "ru" else "Connect wallet first"
        await cb.answer(msg, show_alert=True)
        return
    # In production: check $ALGO balance via DEX API
    await cb.answer(
        "🔍 Проверка $ALGO баланса..." if lang == "ru" else "🔍 Checking $ALGO balance...",
        show_alert=True
    )


# ── PRICE ─────────────────────────────────────────────────────

@router.callback_query(F.data == "price")
async def cb_price(cb: CallbackQuery):
    async with get_session() as session:
        user = await get_user(session, cb.from_user.id)
    lang = user.language if user else "ru"
    await cb.answer("📊 Загружаю..." if lang == "ru" else "📊 Loading...")
    data = await ton_service.get_ton_price()
    if not data:
        await cb.message.edit_text("❌ Нет данных", reply_markup=back_kb(lang))
        return
    text = price_text(data, lang)
    await cb.message.edit_text(text, reply_markup=price_kb(lang))


# ── WHALES ────────────────────────────────────────────────────

@router.callback_query(F.data == "whales")
async def cb_whales(cb: CallbackQuery):
    async with get_session() as session:
        user = await get_user(session, cb.from_user.id)
    lang = user.language if user else "ru"
    subscribed = user.whale_alerts_enabled if user else False
    await cb.answer("🐋 Загружаю..." if lang == "ru" else "🐋 Loading...")
    txs = await ton_service.get_whale_txs()
    text = whales_text(txs, lang)
    await cb.message.edit_text(text, reply_markup=whales_kb(subscribed, lang))


@router.callback_query(F.data == "whale_toggle")
async def cb_whale_toggle(cb: CallbackQuery):
    async with get_session() as session:
        user = await get_user(session, cb.from_user.id)
        new_state = not user.whale_alerts_enabled
        user.whale_alerts_enabled = new_state
    lang = user.language
    status = "🔔 Подписан!" if new_state else "🔕 Отписан"
    await cb.answer(status, show_alert=True)
    txs = await ton_service.get_whale_txs()
    text = whales_text(txs, lang)
    await cb.message.edit_text(text, reply_markup=whales_kb(new_state, lang))


# ── DEX ───────────────────────────────────────────────────────

@router.callback_query(F.data == "dex")
async def cb_dex(cb: CallbackQuery):
    async with get_session() as session:
        user = await get_user(session, cb.from_user.id)
    lang = user.language if user else "ru"
    await cb.answer("🔄 Загружаю..." if lang == "ru" else "🔄 Loading...")
    pools = await get_ston_pools(5)
    text = dex_text(pools, lang)
    await cb.message.edit_text(text, reply_markup=dex_kb(lang))


# ── ALERTS ────────────────────────────────────────────────────

@router.callback_query(F.data == "alerts")
async def cb_alerts(cb: CallbackQuery):
    async with get_session() as session:
        user = await get_user(session, cb.from_user.id)
    lang = user.language if user else "ru"
    title = "🔔 <b>Алерты</b>" if lang == "ru" else "🔔 <b>Alerts</b>"
    await cb.message.edit_text(
        title,
        reply_markup=alerts_kb(user.price_alerts_enabled, user.whale_alerts_enabled, lang)
    )
    await cb.answer()


@router.callback_query(F.data == "toggle_price_alert")
async def cb_toggle_price(cb: CallbackQuery):
    async with get_session() as session:
        user = await get_user(session, cb.from_user.id)
        user.price_alerts_enabled = not user.price_alerts_enabled
        new = user.price_alerts_enabled
        lang = user.language
    await cb.message.edit_text(
        "🔔 <b>Алерты</b>" if lang == "ru" else "🔔 <b>Alerts</b>",
        reply_markup=alerts_kb(new, user.whale_alerts_enabled, lang)
    )
    await cb.answer("✅" if new else "❌")


@router.callback_query(F.data == "toggle_whale_alert")
async def cb_toggle_whale(cb: CallbackQuery):
    async with get_session() as session:
        user = await get_user(session, cb.from_user.id)
        user.whale_alerts_enabled = not user.whale_alerts_enabled
        new = user.whale_alerts_enabled
        lang = user.language
    await cb.message.edit_text(
        "🔔 <b>Алерты</b>" if lang == "ru" else "🔔 <b>Alerts</b>",
        reply_markup=alerts_kb(user.price_alerts_enabled, new, lang)
    )
    await cb.answer("✅" if new else "❌")


# ── ANALYTICS ─────────────────────────────────────────────────

@router.callback_query(F.data == "analytics")
async def cb_analytics(cb: CallbackQuery):
    async with get_session() as session:
        user = await get_user(session, cb.from_user.id)
    lang = user.language if user else "ru"

    if not user or not user.ton_wallet:
        msg = "Подключи кошелёк в разделе 💼" if lang == "ru" else "Connect wallet in 💼 section"
        await cb.answer(msg, show_alert=True)
        return

    await cb.answer("📊 Загружаю..." if lang == "ru" else "📊 Loading...")
    try:
        info = await ton_service.get_wallet_info(user.ton_wallet)
        price_data = await ton_service.get_ton_price()
        ton_price = price_data["usd"] if price_data else 0
        usd_value = info["balance"] * ton_price
        text = analytics_text(user.ton_wallet, info["balance"], ton_price, usd_value, lang)
        await cb.message.edit_text(text, reply_markup=analytics_kb(lang))
    except Exception as e:
        log.error("Analytics error: %s", e)
        await cb.message.answer("❌ Ошибка загрузки аналитики.")
