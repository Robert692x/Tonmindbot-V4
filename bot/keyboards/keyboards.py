from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


# ── MAIN MENU — matches /start screenshot exactly ─────────────

def main_menu_kb(lang: str = "ru") -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    if lang == "ru":
        b.row(
            InlineKeyboardButton(text="💼 Кошелёк", callback_data="wallet"),
            InlineKeyboardButton(text="📊 Аналитика", callback_data="analytics"),
        )
        b.row(
            InlineKeyboardButton(text="💰 Цена", callback_data="price"),
            InlineKeyboardButton(text="🐋 Киты", callback_data="whales"),
        )
        b.row(
            InlineKeyboardButton(text="🔄 DEX", callback_data="dex"),
            InlineKeyboardButton(text="🔔 Алерты", callback_data="alerts"),
        )
        b.row(
            InlineKeyboardButton(text="🤖 AI Аналитик", callback_data="ai"),
            InlineKeyboardButton(text="⭐ Premium", callback_data="premium"),
        )
        b.row(
            InlineKeyboardButton(text="👤 Профиль", callback_data="profile"),
            InlineKeyboardButton(text="🌐 English", callback_data="lang_en"),
        )
    else:
        b.row(
            InlineKeyboardButton(text="💼 Wallet", callback_data="wallet"),
            InlineKeyboardButton(text="📊 Analytics", callback_data="analytics"),
        )
        b.row(
            InlineKeyboardButton(text="💰 Price", callback_data="price"),
            InlineKeyboardButton(text="🐋 Whales", callback_data="whales"),
        )
        b.row(
            InlineKeyboardButton(text="🔄 DEX", callback_data="dex"),
            InlineKeyboardButton(text="🔔 Alerts", callback_data="alerts"),
        )
        b.row(
            InlineKeyboardButton(text="🤖 AI Analytics", callback_data="ai"),
            InlineKeyboardButton(text="⭐ Premium", callback_data="premium"),
        )
        b.row(
            InlineKeyboardButton(text="👤 Profile", callback_data="profile"),
            InlineKeyboardButton(text="🌐 Русский", callback_data="lang_ru"),
        )
    return b.as_markup()


# ── WALLET ────────────────────────────────────────────────────

def wallet_kb(lang="ru") -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    if lang == "ru":
        b.row(
            InlineKeyboardButton(text="💼 Кошелёк", callback_data="wallet"),
            InlineKeyboardButton(text="📊 Аналитика", callback_data="analytics"),
        )
        b.row(InlineKeyboardButton(text="◀️ Меню", callback_data="menu"))
    else:
        b.row(
            InlineKeyboardButton(text="💼 Wallet", callback_data="wallet"),
            InlineKeyboardButton(text="📊 Analytics", callback_data="analytics"),
        )
        b.row(InlineKeyboardButton(text="◀️ Menu", callback_data="menu"))
    return b.as_markup()


def wallet_connect_kb(lang="ru") -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    label = "🔗 Подключить кошелёк" if lang == "ru" else "🔗 Connect Wallet"
    b.row(InlineKeyboardButton(text=label, callback_data="wallet_connect"))
    b.row(InlineKeyboardButton(text="◀️ Меню" if lang == "ru" else "◀️ Menu", callback_data="menu"))
    return b.as_markup()


# ── PRICE ─────────────────────────────────────────────────────

def price_kb(lang="ru") -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    if lang == "ru":
        b.row(
            InlineKeyboardButton(text="💰 Цена", callback_data="price"),
            InlineKeyboardButton(text="🔔 Алерты", callback_data="alerts"),
        )
        b.row(InlineKeyboardButton(text="◀️ Меню", callback_data="menu"))
    else:
        b.row(
            InlineKeyboardButton(text="💰 Price", callback_data="price"),
            InlineKeyboardButton(text="🔔 Alerts", callback_data="alerts"),
        )
        b.row(InlineKeyboardButton(text="◀️ Menu", callback_data="menu"))
    return b.as_markup()


# ── PROFILE ───────────────────────────────────────────────────

def profile_kb(lang="ru") -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    if lang == "ru":
        b.row(
            InlineKeyboardButton(text="👤 Профиль", callback_data="profile"),
            InlineKeyboardButton(text="⭐ Premium", callback_data="premium"),
        )
        b.row(InlineKeyboardButton(text="◀️ Меню", callback_data="menu"))
    else:
        b.row(
            InlineKeyboardButton(text="👤 Profile", callback_data="profile"),
            InlineKeyboardButton(text="⭐ Premium", callback_data="premium"),
        )
        b.row(InlineKeyboardButton(text="◀️ Menu", callback_data="menu"))
    return b.as_markup()


# ── PREMIUM ───────────────────────────────────────────────────

def premium_kb(lang="ru") -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    if lang == "ru":
        b.row(InlineKeyboardButton(text="🔍 Проверить $ALGO", callback_data="check_algo"))
        b.row(InlineKeyboardButton(text="◀️ Меню", callback_data="menu"))
    else:
        b.row(InlineKeyboardButton(text="🔍 Check $ALGO", callback_data="check_algo"))
        b.row(InlineKeyboardButton(text="◀️ Menu", callback_data="menu"))
    return b.as_markup()


def premium_pay_kb(memo: str, lang="ru") -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    label = "✅ Я отправил" if lang == "ru" else "✅ I've sent it"
    b.row(InlineKeyboardButton(text=label, callback_data=f"verify_pay:{memo}"))
    b.row(InlineKeyboardButton(text="◀️ Назад" if lang == "ru" else "◀️ Back",
                                callback_data="premium"))
    return b.as_markup()


# ── AI ────────────────────────────────────────────────────────

def ai_kb(lang="ru") -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    if lang == "ru":
        b.row(
            InlineKeyboardButton(text="📈 Анализ рынка", callback_data="ai_market"),
            InlineKeyboardButton(text="🔍 Анализ кошелька", callback_data="ai_wallet"),
        )
        b.row(InlineKeyboardButton(text="🗑 Очистить чат", callback_data="ai_clear"))
        b.row(InlineKeyboardButton(text="◀️ Меню", callback_data="menu"))
    else:
        b.row(
            InlineKeyboardButton(text="📈 Market Analysis", callback_data="ai_market"),
            InlineKeyboardButton(text="🔍 Wallet Analysis", callback_data="ai_wallet"),
        )
        b.row(InlineKeyboardButton(text="🗑 Clear Chat", callback_data="ai_clear"))
        b.row(InlineKeyboardButton(text="◀️ Menu", callback_data="menu"))
    return b.as_markup()


# ── WHALES ────────────────────────────────────────────────────

def whales_kb(subscribed=False, lang="ru") -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    if lang == "ru":
        label = "🔕 Отписаться" if subscribed else "🔔 Подписаться на алерты"
        b.row(InlineKeyboardButton(text=label, callback_data="whale_toggle"))
        b.row(InlineKeyboardButton(text="◀️ Меню", callback_data="menu"))
    else:
        label = "🔕 Unsubscribe" if subscribed else "🔔 Subscribe to alerts"
        b.row(InlineKeyboardButton(text=label, callback_data="whale_toggle"))
        b.row(InlineKeyboardButton(text="◀️ Menu", callback_data="menu"))
    return b.as_markup()


# ── DEX ───────────────────────────────────────────────────────

def dex_kb(lang="ru") -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    if lang == "ru":
        b.row(
            InlineKeyboardButton(text="🔄 Обновить", callback_data="dex"),
            InlineKeyboardButton(text="🌐 STON.fi", url="https://app.ston.fi"),
        )
        b.row(InlineKeyboardButton(text="◀️ Меню", callback_data="menu"))
    else:
        b.row(
            InlineKeyboardButton(text="🔄 Refresh", callback_data="dex"),
            InlineKeyboardButton(text="🌐 STON.fi", url="https://app.ston.fi"),
        )
        b.row(InlineKeyboardButton(text="◀️ Menu", callback_data="menu"))
    return b.as_markup()


# ── ALERTS ────────────────────────────────────────────────────

def alerts_kb(price_on=False, whale_on=False, lang="ru") -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    if lang == "ru":
        b.row(InlineKeyboardButton(
            text=f"💰 Ценовые алерты: {'✅' if price_on else '❌'}",
            callback_data="toggle_price_alert"
        ))
        b.row(InlineKeyboardButton(
            text=f"🐋 Кит-алерты: {'✅' if whale_on else '❌'}",
            callback_data="toggle_whale_alert"
        ))
        b.row(InlineKeyboardButton(text="◀️ Меню", callback_data="menu"))
    else:
        b.row(InlineKeyboardButton(
            text=f"💰 Price Alerts: {'✅' if price_on else '❌'}",
            callback_data="toggle_price_alert"
        ))
        b.row(InlineKeyboardButton(
            text=f"🐋 Whale Alerts: {'✅' if whale_on else '❌'}",
            callback_data="toggle_whale_alert"
        ))
        b.row(InlineKeyboardButton(text="◀️ Menu", callback_data="menu"))
    return b.as_markup()


# ── ANALYTICS ────────────────────────────────────────────────

def analytics_kb(lang="ru") -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    if lang == "ru":
        b.row(
            InlineKeyboardButton(text="💼 Кошелёк", callback_data="wallet"),
            InlineKeyboardButton(text="📊 Обновить", callback_data="analytics"),
        )
        b.row(InlineKeyboardButton(text="◀️ Меню", callback_data="menu"))
    else:
        b.row(
            InlineKeyboardButton(text="💼 Wallet", callback_data="wallet"),
            InlineKeyboardButton(text="📊 Refresh", callback_data="analytics"),
        )
        b.row(InlineKeyboardButton(text="◀️ Menu", callback_data="menu"))
    return b.as_markup()


def back_kb(lang="ru") -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(
        text="◀️ Меню" if lang == "ru" else "◀️ Menu",
        callback_data="menu"
    ))
    return b.as_markup()
