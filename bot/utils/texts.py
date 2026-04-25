"""
Message texts matching the visual design in screenshots.
Dark theme with monospace formatting via HTML.
"""
from datetime import datetime, timezone
from typing import Optional
from config import settings


def _fmt_addr(addr: str) -> str:
    """EQAbC...xYz9"""
    if not addr or len(addr) < 12:
        return addr
    return f"{addr[:6]}...{addr[-4:]}"


def _premium_until(dt: Optional[datetime]) -> str:
    if not dt:
        return "—"
    return dt.strftime("%Y-%m-%d")


def _remaining(dt: Optional[datetime]) -> str:
    if not dt:
        return ""
    delta = dt - datetime.now(timezone.utc)
    if delta.total_seconds() <= 0:
        return " (истёк)" if True else " (expired)"
    return f" (+{delta.days}д)"


# ─────────────────────────────────────────────────────────────
#  START
# ─────────────────────────────────────────────────────────────

START_RU = (
    "🧠 <b>TON Mind Bot</b>\n\n"
    "AI-аналитика TON блокчейна.\n"
    "Выбери действие:"
)

START_EN = (
    "🧠 <b>TON Mind Bot</b>\n\n"
    "AI analytics for the TON blockchain.\n"
    "Choose an action:"
)


# ─────────────────────────────────────────────────────────────
#  WALLET — matches screenshot 6
# ─────────────────────────────────────────────────────────────

def wallet_text(wallet: str, balance: float, txs: list, lang="ru") -> str:
    addr = _fmt_addr(wallet)
    if lang == "ru":
        lines = [
            f"💼 <b>Кошелёк</b>",
            f"<code>{addr}</code>\n",
            f"💰 <b>Баланс: <code>{balance:,.2f} TON</code></b>\n",
        ]
        if txs:
            lines.append("📋 <b>Последние TX:</b>")
            for tx in txs[:5]:
                direction = "⬇️ IN" if tx.get("in") else "⬆️ OUT"
                amount = tx.get("amount", 0)
                date = tx.get("date", "")
                lines.append(
                    f"<code>{date}</code>  {direction}  "
                    f"<code>{amount:,.2f} TON</code>"
                )
    else:
        lines = [
            f"💼 <b>Wallet</b>",
            f"<code>{addr}</code>\n",
            f"💰 <b>Balance: <code>{balance:,.2f} TON</code></b>\n",
        ]
        if txs:
            lines.append("📋 <b>Recent TX:</b>")
            for tx in txs[:5]:
                direction = "⬇️ IN" if tx.get("in") else "⬆️ OUT"
                amount = tx.get("amount", 0)
                date = tx.get("date", "")
                lines.append(
                    f"<code>{date}</code>  {direction}  "
                    f"<code>{amount:,.2f} TON</code>"
                )
    return "\n".join(lines)


WALLET_NOT_CONNECTED_RU = (
    "💼 <b>Кошелёк</b>\n\n"
    "Кошелёк не подключён.\n\n"
    "Отправь свой TON-адрес (начинается с EQ или UQ):"
)

WALLET_NOT_CONNECTED_EN = (
    "💼 <b>Wallet</b>\n\n"
    "No wallet connected.\n\n"
    "Send your TON address (starts with EQ or UQ):"
)


# ─────────────────────────────────────────────────────────────
#  PRICE — matches screenshot 5
# ─────────────────────────────────────────────────────────────

def price_text(data: dict, lang="ru") -> str:
    price = data.get("usd", 0)
    h1 = data.get("change_1h", 0)
    h24 = data.get("change_24h", 0)
    d7 = data.get("change_7d", 0)
    vol = data.get("volume_24h", 0)
    mcap = data.get("market_cap", 0)

    def sign(v): return "+" if v >= 0 else ""
    def color_dot(v): return "🟢" if v >= 0 else "🔴"

    if lang == "ru":
        return (
            f"💰 <b>TON</b>\n\n"
            f"💵 Цена: <code>${price:.2f}</code>\n"
            f"1h:  <code>{sign(h1)}{h1:.2f}%</code>\n"
            f"24h: {color_dot(h24)} <code>{sign(h24)}{h24:.2f}%</code>\n"
            f"7d:  <code>{sign(d7)}{d7:.2f}%</code>\n\n"
            f"📦 Объём 24h: <code>${vol:,.0f}</code>\n"
            f"🏦 Капитализация: <code>${mcap/1e9:.1f}B</code>"
        )
    else:
        return (
            f"💰 <b>TON</b>\n\n"
            f"💵 Price: <code>${price:.2f}</code>\n"
            f"1h:  <code>{sign(h1)}{h1:.2f}%</code>\n"
            f"24h: {color_dot(h24)} <code>{sign(h24)}{h24:.2f}%</code>\n"
            f"7d:  <code>{sign(d7)}{d7:.2f}%</code>\n\n"
            f"📦 Volume 24h: <code>${vol:,.0f}</code>\n"
            f"🏦 Market Cap: <code>${mcap/1e9:.1f}B</code>"
        )


# ─────────────────────────────────────────────────────────────
#  WHALES — matches screenshot 4
# ─────────────────────────────────────────────────────────────

def whales_text(txs: list, lang="ru") -> str:
    threshold = int(settings.WHALE_THRESHOLD_TON)
    if lang == "ru":
        lines = [f"🐋 <b>Крупные TX (>{threshold:,} TON)</b>\n"]
    else:
        lines = [f"🐋 <b>Large TX (>{threshold:,} TON)</b>\n"]

    if not txs:
        lines.append("Нет данных" if lang == "ru" else "No data")
        return "\n".join(lines)

    for tx in txs[:5]:
        from_addr = _fmt_addr(tx.get("from", ""))
        to_addr = _fmt_addr(tx.get("to", ""))
        amount = tx.get("amount", 0)
        date = tx.get("date", "")
        lines.append(
            f"💎 <code>{amount:,.0f} TON</code>\n"
            f"<code>{from_addr}</code> → <code>{to_addr}</code>\n"
            f"<i>{date}</i>\n"
        )
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────
#  PROFILE — matches screenshot 2
# ─────────────────────────────────────────────────────────────

def profile_text(user, lang="ru") -> str:
    wallet = _fmt_addr(user.ton_wallet) if user.ton_wallet else ("Не подключён" if lang == "ru" else "Not connected")
    status = f"⭐ Premium" if user.is_premium else ("Бесплатный" if lang == "ru" else "Free")
    until = _premium_until(user.premium_until) if user.is_premium else "—"
    ref_link = f"t.me/{settings.BOT_USERNAME}?start={user.referral_code}"

    if lang == "ru":
        return (
            f"👤 <b>Профиль</b>\n\n"
            f"💼 Кошелёк: <code>{wallet}</code>\n"
            f"⭐ Статус: {status}\n"
            f"📅 Premium до: <code>{until}</code>\n"
            f"👥 Рефералов: <b>{user.referral_count}</b>\n\n"
            f"🔗 Реф. ссылка:\n"
            f"<code>{ref_link}</code>\n\n"
            f"<i>Приведи друга → +{settings.REFERRAL_BONUS_DAYS} дней Premium</i>"
        )
    else:
        return (
            f"👤 <b>Profile</b>\n\n"
            f"💼 Wallet: <code>{wallet}</code>\n"
            f"⭐ Status: {status}\n"
            f"📅 Premium until: <code>{until}</code>\n"
            f"👥 Referrals: <b>{user.referral_count}</b>\n\n"
            f"🔗 Referral link:\n"
            f"<code>{ref_link}</code>\n\n"
            f"<i>Invite a friend → +{settings.REFERRAL_BONUS_DAYS} days Premium</i>"
        )


# ─────────────────────────────────────────────────────────────
#  PREMIUM — matches screenshot 1
# ─────────────────────────────────────────────────────────────

def premium_text(memo: str, lang="ru") -> str:
    if lang == "ru":
        return (
            f"⭐ <b>TON Mind Premium</b>\n\n"
            f"✅ Безлимитные AI запросы\n"
            f"✅ DEX сигналы STON.fi + DeDust\n"
            f"✅ Неограниченные алерты\n\n"
            f"───────────────\n\n"
            f"<b>1️⃣ TON подписка</b>\n"
            f"Отправь <b>{settings.PREMIUM_PRICE_TON} TON</b> на:\n"
            f"<code>{settings.TON_WALLET}</code>\n"
            f"Комментарий: <code>{memo}</code>\n\n"
            f"<b>2️⃣ $ALGO токен</b>\n"
            f"Держи >{settings.ALGO_PREMIUM_THRESHOLD:,} $ALGO\n\n"
            f"<b>3️⃣ Реферал</b> = +{settings.REFERRAL_BONUS_DAYS} дней"
        )
    else:
        return (
            f"⭐ <b>TON Mind Premium</b>\n\n"
            f"✅ Unlimited AI requests\n"
            f"✅ DEX signals STON.fi + DeDust\n"
            f"✅ Unlimited alerts\n\n"
            f"───────────────\n\n"
            f"<b>1️⃣ TON subscription</b>\n"
            f"Send <b>{settings.PREMIUM_PRICE_TON} TON</b> to:\n"
            f"<code>{settings.TON_WALLET}</code>\n"
            f"Comment: <code>{memo}</code>\n\n"
            f"<b>2️⃣ $ALGO token</b>\n"
            f"Hold >{settings.ALGO_PREMIUM_THRESHOLD:,} $ALGO\n\n"
            f"<b>3️⃣ Referral</b> = +{settings.REFERRAL_BONUS_DAYS} days"
        )


# ─────────────────────────────────────────────────────────────
#  AI — matches screenshot 3
# ─────────────────────────────────────────────────────────────

def ai_intro_text(used: int, limit: int, model: str, lang="ru") -> str:
    remaining = limit - used
    if lang == "ru":
        return (
            f"🤖 <b>AI Аналитик</b> ({model})\n\n"
            f"Осталось запросов: <b>{remaining}/{limit}</b>\n\n"
            f"Задай вопрос про TON, крипту, DeFi:"
        )
    else:
        return (
            f"🤖 <b>AI Analytics</b> ({model})\n\n"
            f"Requests remaining: <b>{remaining}/{limit}</b>\n\n"
            f"Ask about TON, crypto, DeFi:"
        )


# ─────────────────────────────────────────────────────────────
#  DEX
# ─────────────────────────────────────────────────────────────

def dex_text(pools: list, lang="ru") -> str:
    if lang == "ru":
        lines = ["🔄 <b>STON.fi — Топ пулы</b>\n"]
    else:
        lines = ["🔄 <b>STON.fi — Top Pools</b>\n"]

    if not pools:
        lines.append("Нет данных" if lang == "ru" else "No data")
        return "\n".join(lines)

    for p in pools[:5]:
        t0 = p.get("token0", "?")
        t1 = p.get("token1", "?")
        tvl = p.get("tvl_usd", 0)
        apy = p.get("apy", None)
        apy_str = f"  APY: <code>{apy:.1f}%</code>" if apy else ""
        lines.append(f"• <b>{t0}/{t1}</b> — TVL: <code>${tvl:,.0f}</code>{apy_str}")

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────
#  ANALYTICS
# ─────────────────────────────────────────────────────────────

def analytics_text(wallet: str, balance: float, ton_price: float,
                   usd_value: float, lang="ru") -> str:
    addr = _fmt_addr(wallet)
    if lang == "ru":
        return (
            f"📊 <b>Аналитика кошелька</b>\n\n"
            f"📍 <code>{addr}</code>\n\n"
            f"💰 Баланс: <code>{balance:,.4f} TON</code>\n"
            f"💵 В USD: <code>${usd_value:,.2f}</code>\n"
            f"📈 Цена TON: <code>${ton_price:.2f}</code>"
        )
    else:
        return (
            f"📊 <b>Wallet Analytics</b>\n\n"
            f"📍 <code>{addr}</code>\n\n"
            f"💰 Balance: <code>{balance:,.4f} TON</code>\n"
            f"💵 USD Value: <code>${usd_value:,.2f}</code>\n"
            f"📈 TON Price: <code>${ton_price:.2f}</code>"
        )
