from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.services.i18n import get_text


def main_menu_keyboard(subject: object) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text=get_text(subject, "button_wallet"), callback_data="wallet"),
        InlineKeyboardButton(text=get_text(subject, "button_analytics"), callback_data="analytics"),
    )
    builder.row(
        InlineKeyboardButton(text=get_text(subject, "button_price"), callback_data="price"),
        InlineKeyboardButton(text=get_text(subject, "button_whales"), callback_data="whales"),
    )
    builder.row(
        InlineKeyboardButton(text=get_text(subject, "button_portfolio"), callback_data="portfolio"),
        InlineKeyboardButton(text=get_text(subject, "button_leaderboard"), callback_data="leaderboard"),
    )
    builder.row(
        InlineKeyboardButton(text=get_text(subject, "button_dex"), callback_data="dex"),
        InlineKeyboardButton(text=get_text(subject, "button_alerts"), callback_data="alerts"),
    )
    builder.row(
        InlineKeyboardButton(text=get_text(subject, "button_ai"), callback_data="ai"),
        InlineKeyboardButton(text=get_text(subject, "button_trade"), callback_data="trade"),
    )
    builder.row(
        InlineKeyboardButton(text=get_text(subject, "button_watchlist"), callback_data="watchlist"),
        InlineKeyboardButton(text=get_text(subject, "button_settings"), callback_data="settings"),
    )
    builder.row(
        InlineKeyboardButton(text=get_text(subject, "button_profile"), callback_data="profile"),
    )
    return builder.as_markup()


def wallet_keyboard(subject: object, has_wallet: bool) -> InlineKeyboardMarkup:
    """Main wallet panel — full module grid for connected wallets."""
    builder = InlineKeyboardBuilder()
    if has_wallet:
        builder.row(
            InlineKeyboardButton(text=get_text(subject, "button_wallet_txs"), callback_data="wallet:txs"),
            InlineKeyboardButton(text=get_text(subject, "button_portfolio"), callback_data="wallet:portfolio"),
        )
        builder.row(
            InlineKeyboardButton(text=get_text(subject, "button_wallet_pnl"), callback_data="wallet:pnl"),
            InlineKeyboardButton(text=get_text(subject, "button_wallet_analysis"), callback_data="wallet:analysis"),
        )
        builder.row(
            InlineKeyboardButton(text=get_text(subject, "button_refresh_wallet"), callback_data="wallet"),
            InlineKeyboardButton(text=get_text(subject, "button_update_address"), callback_data="wallet:connect"),
        )
    else:
        builder.row(InlineKeyboardButton(text=get_text(subject, "button_connect_wallet"), callback_data="wallet:connect"))
    builder.row(InlineKeyboardButton(text=get_text(subject, "button_back_to_menu"), callback_data="menu"))
    return builder.as_markup()


def wallet_transactions_keyboard(subject: object, active_days: int = 7) -> InlineKeyboardMarkup:
    """Period filter keyboard for the transactions module."""
    builder = InlineKeyboardBuilder()

    def _mark(d: int) -> str:
        return f"[{d}D]" if d == active_days else f"{d}D"

    builder.row(
        InlineKeyboardButton(text=_mark(1), callback_data="wallet:txs:1"),
        InlineKeyboardButton(text=_mark(7), callback_data="wallet:txs:7"),
        InlineKeyboardButton(text=_mark(30), callback_data="wallet:txs:30"),
    )
    builder.row(InlineKeyboardButton(text=get_text(subject, "button_back_to_wallet"), callback_data="wallet"))
    builder.row(InlineKeyboardButton(text=get_text(subject, "button_back_to_menu"), callback_data="menu"))
    return builder.as_markup()


def wallet_pnl_detail_keyboard(subject: object, active_days: int = 7) -> InlineKeyboardMarkup:
    """Period filter keyboard for the PNL module."""
    builder = InlineKeyboardBuilder()

    def _mark(d: int) -> str:
        return f"[{d}D]" if d == active_days else f"{d}D"

    builder.row(
        InlineKeyboardButton(text=_mark(1), callback_data="wallet:pnl:1"),
        InlineKeyboardButton(text=_mark(7), callback_data="wallet:pnl:7"),
        InlineKeyboardButton(text=_mark(30), callback_data="wallet:pnl:30"),
    )
    builder.row(InlineKeyboardButton(text=get_text(subject, "button_back_to_wallet"), callback_data="wallet"))
    builder.row(InlineKeyboardButton(text=get_text(subject, "button_back_to_menu"), callback_data="menu"))
    return builder.as_markup()


def wallet_analysis_keyboard(subject: object) -> InlineKeyboardMarkup:
    """Controls for the deep wallet analysis panel."""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=get_text(subject, "button_refresh"), callback_data="wallet:analysis"))
    builder.row(InlineKeyboardButton(text=get_text(subject, "button_back_to_wallet"), callback_data="wallet"))
    builder.row(InlineKeyboardButton(text=get_text(subject, "button_back_to_menu"), callback_data="menu"))
    return builder.as_markup()


def analytics_keyboard(subject: object) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=get_text(subject, "button_refresh"), callback_data="analytics"))
    builder.row(
        InlineKeyboardButton(text="PnL 1D", callback_data="analytics:pnl:1"),
        InlineKeyboardButton(text="PnL 7D", callback_data="analytics:pnl:7"),
        InlineKeyboardButton(text="PnL 30D", callback_data="analytics:pnl:30"),
    )
    builder.row(InlineKeyboardButton(text=get_text(subject, "button_back_to_menu"), callback_data="menu"))
    return builder.as_markup()


def wallet_pnl_keyboard(subject: object) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="1D", callback_data="analytics:pnl:1"),
        InlineKeyboardButton(text="7D", callback_data="analytics:pnl:7"),
        InlineKeyboardButton(text="30D", callback_data="analytics:pnl:30"),
    )
    builder.row(InlineKeyboardButton(text=get_text(subject, "button_back_to_menu"), callback_data="menu"))
    return builder.as_markup()


def simple_refresh_keyboard(subject: object, callback_data: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=get_text(subject, "button_refresh"), callback_data=callback_data))
    builder.row(InlineKeyboardButton(text=get_text(subject, "button_back_to_menu"), callback_data="menu"))
    return builder.as_markup()


def ai_keyboard(subject: object, is_premium: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text=get_text(subject, "button_market_brief"), callback_data="ai:market"),
        InlineKeyboardButton(text=get_text(subject, "button_clear_chat"), callback_data="ai:clear"),
    )
    if is_premium:
        builder.row(InlineKeyboardButton(text=get_text(subject, "button_premium_signal"), callback_data="ai:signal"))
    builder.row(InlineKeyboardButton(text=get_text(subject, "button_back_to_menu"), callback_data="menu"))
    return builder.as_markup()


def premium_keyboard(subject: object, has_pending: bool, is_premium: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if not is_premium:
        builder.row(InlineKeyboardButton(text=get_text(subject, "button_generate_payment"), callback_data="premium:buy"))
    if has_pending:
        builder.row(InlineKeyboardButton(text=get_text(subject, "button_check_payment"), callback_data="premium:check"))
    builder.row(InlineKeyboardButton(text=get_text(subject, "button_back_to_menu"), callback_data="menu"))
    return builder.as_markup()


def alerts_keyboard(
    subject: object,
    *,
    price_enabled: bool,
    whale_enabled: bool,
    signals_enabled: bool,
    is_premium: bool,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=get_text(subject, "alerts_price_toggle", state=get_text(subject, "toggle_on" if price_enabled else "toggle_off")),
            callback_data="alerts:price",
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=get_text(subject, "alerts_whale_toggle", state=get_text(subject, "toggle_on" if whale_enabled else "toggle_off")),
            callback_data="alerts:whale",
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=get_text(subject, "alerts_signals_toggle", state=get_text(subject, "toggle_on" if signals_enabled else "toggle_off")),
            callback_data="alerts:signals",
        )
    )
    if not is_premium:
        builder.row(InlineKeyboardButton(text=get_text(subject, "button_unlock_premium"), callback_data="premium"))
    builder.row(InlineKeyboardButton(text=get_text(subject, "button_back_to_menu"), callback_data="menu"))
    return builder.as_markup()


def price_keyboard(subject: object) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text=get_text(subject, "button_refresh"), callback_data="price"),
        InlineKeyboardButton(text=get_text(subject, "button_search_token"), callback_data="price:search"),
    )
    builder.row(InlineKeyboardButton(text=get_text(subject, "button_trending"), callback_data="price:trending"))
    builder.row(InlineKeyboardButton(text=get_text(subject, "button_back_to_menu"), callback_data="menu"))
    return builder.as_markup()


def search_prompt_keyboard(subject: object) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=get_text(subject, "button_back_to_menu"), callback_data="menu"))
    return builder.as_markup()


def search_result_keyboard(subject: object) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text=get_text(subject, "button_search_token"), callback_data="price:search"),
        InlineKeyboardButton(text=get_text(subject, "button_back_to_menu"), callback_data="menu"),
    )
    return builder.as_markup()


def trade_menu_keyboard(subject: object) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=get_text(subject, "button_trade_add"), callback_data="trade:add"))
    builder.row(
        InlineKeyboardButton(text=get_text(subject, "button_trade_positions"), callback_data="trade:positions"),
        InlineKeyboardButton(text=get_text(subject, "button_trade_history"), callback_data="trade:history"),
    )
    builder.row(
        InlineKeyboardButton(text=get_text(subject, "button_trade_pnl"), callback_data="trade:pnl"),
        InlineKeyboardButton(text=get_text(subject, "button_trade_stats"), callback_data="trade:stats"),
    )
    builder.row(
        InlineKeyboardButton(text=get_text(subject, "button_summary_7d"), callback_data="trade:summary:7"),
        InlineKeyboardButton(text=get_text(subject, "button_summary_30d"), callback_data="trade:summary:30"),
    )
    builder.row(InlineKeyboardButton(text=get_text(subject, "button_back_to_menu"), callback_data="menu"))
    return builder.as_markup()


def trade_back_keyboard(subject: object) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=get_text(subject, "button_back_to_trade"), callback_data="trade"))
    builder.row(InlineKeyboardButton(text=get_text(subject, "button_back_to_menu"), callback_data="menu"))
    return builder.as_markup()


def trade_period_keyboard(subject: object, section: str) -> InlineKeyboardMarkup:
    """Keyboard for history / summary screens with 7d / 30d filter buttons."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="7 days", callback_data=f"trade:{section}:7"),
        InlineKeyboardButton(text="30 days", callback_data=f"trade:{section}:30"),
    )
    builder.row(InlineKeyboardButton(text=get_text(subject, "button_back_to_trade"), callback_data="trade"))
    return builder.as_markup()


def watchlist_keyboard(subject: object, wallets: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="Add wallet", callback_data="watchlist:add"))
    for w in wallets:
        name = (w.label or w.address[:12] + "...")[:20]
        toggle = "Alerts: ON" if w.alerts_enabled else "Alerts: OFF"
        builder.row(
            InlineKeyboardButton(text=name, callback_data=f"watchlist:info:{w.id}"),
            InlineKeyboardButton(text=toggle, callback_data=f"watchlist:toggle:{w.id}"),
            InlineKeyboardButton(text="Remove", callback_data=f"watchlist:remove:{w.id}"),
        )
    builder.row(InlineKeyboardButton(text=get_text(subject, "button_back_to_menu"), callback_data="menu"))
    return builder.as_markup()


def watchlist_add_keyboard(subject: object) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=get_text(subject, "button_back_to_menu"), callback_data="menu"))
    return builder.as_markup()


def settings_keyboard(subject: object) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text=get_text(subject, "button_language_en"), callback_data="settings:lang:en"),
        InlineKeyboardButton(text=get_text(subject, "button_language_ru"), callback_data="settings:lang:ru"),
    )
    builder.row(InlineKeyboardButton(text=get_text(subject, "button_back_to_menu"), callback_data="menu"))
    return builder.as_markup()


# ── Wallet Manager keyboards ──────────────────────────────────────────────────

def wm_main_keyboard(subject: object, wallets: list) -> InlineKeyboardMarkup:
    """Main Wallet Manager screen — list of wallets + actions."""
    builder = InlineKeyboardBuilder()
    for w in wallets:
        name = (w.label or w.address[:12] + "...")[:24]
        status = get_text(subject, "wm_alerts_on") if w.alerts_enabled else get_text(subject, "wm_alerts_off")
        builder.row(
            InlineKeyboardButton(text=f"{name}  {status}", callback_data=f"wm:w:{w.id}"),
        )
    builder.row(InlineKeyboardButton(text=get_text(subject, "wm_add_wallet"), callback_data="wm:add"))
    builder.row(InlineKeyboardButton(text=get_text(subject, "button_back_to_menu"), callback_data="menu"))
    return builder.as_markup()


def wm_wallet_keyboard(subject: object, wallet_id: int, alerts_enabled: bool) -> InlineKeyboardMarkup:
    """Per-wallet actions."""
    builder = InlineKeyboardBuilder()
    toggle_text = get_text(subject, "wm_disable_alerts") if alerts_enabled else get_text(subject, "wm_enable_alerts")
    builder.row(InlineKeyboardButton(text=toggle_text, callback_data=f"wm:toggle:{wallet_id}"))
    builder.row(
        InlineKeyboardButton(text=get_text(subject, "wm_alert_settings"), callback_data=f"wm:alerts:{wallet_id}"),
        InlineKeyboardButton(text=get_text(subject, "wm_view_analysis"), callback_data=f"wm:analyze:{wallet_id}"),
    )
    builder.row(InlineKeyboardButton(text=get_text(subject, "wm_remove_wallet"), callback_data=f"wm:rm_confirm:{wallet_id}"))
    builder.row(
        InlineKeyboardButton(text=get_text(subject, "wm_back_to_list"), callback_data="wm"),
        InlineKeyboardButton(text=get_text(subject, "button_back_to_menu"), callback_data="menu"),
    )
    return builder.as_markup()


def wm_alert_settings_keyboard(
    subject: object,
    wallet_id: int,
    types: dict[str, bool],
    threshold: float | None,
    global_threshold: float,
) -> InlineKeyboardMarkup:
    """Alert type toggles + threshold."""
    builder = InlineKeyboardBuilder()

    def _label(key: str, label: str) -> str:
        state = "ON" if types.get(key, False) else "OFF"
        return f"{label}: {state}"

    builder.row(
        InlineKeyboardButton(text=_label("tx", "TX"), callback_data=f"wm:at:{wallet_id}:tx"),
        InlineKeyboardButton(text=_label("whale", "Whale"), callback_data=f"wm:at:{wallet_id}:whale"),
    )
    builder.row(
        InlineKeyboardButton(text=_label("risk", "Risk"), callback_data=f"wm:at:{wallet_id}:risk"),
        InlineKeyboardButton(text=_label("behavior", "Behavior"), callback_data=f"wm:at:{wallet_id}:behavior"),
    )
    thr_display = f"{threshold:,.0f}" if threshold else f"{global_threshold:,.0f}*"
    builder.row(
        InlineKeyboardButton(
            text=get_text(subject, "wm_set_threshold", amount=thr_display),
            callback_data=f"wm:threshold:{wallet_id}",
        )
    )
    builder.row(InlineKeyboardButton(text=get_text(subject, "wm_back_to_wallet", id=wallet_id), callback_data=f"wm:w:{wallet_id}"))
    return builder.as_markup()


def wm_confirm_remove_keyboard(subject: object, wallet_id: int) -> InlineKeyboardMarkup:
    """Confirm wallet removal."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text=get_text(subject, "wm_confirm_yes"), callback_data=f"wm:rm:{wallet_id}"),
        InlineKeyboardButton(text=get_text(subject, "wm_confirm_no"), callback_data=f"wm:w:{wallet_id}"),
    )
    return builder.as_markup()


# ── Admin keyboards ───────────────────────────────────────────────────────────

def admin_wm_list_keyboard(subject: object, flagged_only: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=get_text(subject, "admin_all_wallets" if not flagged_only else "admin_flagged_wallets"),
            callback_data="admin:wm:flagged" if not flagged_only else "admin:wm",
        )
    )
    builder.row(InlineKeyboardButton(text=get_text(subject, "button_back_to_menu"), callback_data="menu"))
    return builder.as_markup()


def admin_wm_wallet_keyboard(
    subject: object, wallet_id: int, flagged: bool
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    flag_text = get_text(subject, "admin_unflag") if flagged else get_text(subject, "admin_flag")
    builder.row(InlineKeyboardButton(text=flag_text, callback_data=f"admin:wm:flag:{wallet_id}"))
    builder.row(InlineKeyboardButton(text=get_text(subject, "admin_add_note"), callback_data=f"admin:wm:note:{wallet_id}"))
    builder.row(
        InlineKeyboardButton(text="Risk: LOW", callback_data=f"admin:wm:risk:{wallet_id}:LOW"),
        InlineKeyboardButton(text="Risk: MED", callback_data=f"admin:wm:risk:{wallet_id}:MEDIUM"),
        InlineKeyboardButton(text="Risk: HIGH", callback_data=f"admin:wm:risk:{wallet_id}:HIGH"),
        InlineKeyboardButton(text="Risk: CRIT", callback_data=f"admin:wm:risk:{wallet_id}:CRITICAL"),
    )
    builder.row(InlineKeyboardButton(text=get_text(subject, "admin_clear_override"), callback_data=f"admin:wm:risk:{wallet_id}:CLEAR"))
    builder.row(InlineKeyboardButton(text=get_text(subject, "admin_remove_wallet"), callback_data=f"admin:wm:rm:{wallet_id}"))
    builder.row(InlineKeyboardButton(text=get_text(subject, "admin_back"), callback_data="admin:wm"))
    return builder.as_markup()


# ── Chart keyboards ──────────────────────────────────────────────────────────

def chart_keyboard(subject: object, active_interval: str = "1h") -> InlineKeyboardMarkup:
    """Timeframe switcher shown below the candlestick chart."""
    builder = InlineKeyboardBuilder()

    def _label(iv: str) -> str:
        return f"[{iv}]" if iv == active_interval else iv

    builder.row(
        InlineKeyboardButton(text=_label("1m"),  callback_data="chart:1m"),
        InlineKeyboardButton(text=_label("5m"),  callback_data="chart:5m"),
        InlineKeyboardButton(text=_label("30m"), callback_data="chart:30m"),
        InlineKeyboardButton(text=_label("1h"),  callback_data="chart:1h"),
    )
    builder.row(
        InlineKeyboardButton(text="Обновить", callback_data=f"chart:refresh:{active_interval}"),
    )
    builder.row(InlineKeyboardButton(text=get_text(subject, "button_back_to_menu"), callback_data="menu"))
    return builder.as_markup()


# ── DEX Screener keyboards ────────────────────────────────────────────────────

def dex_keyboard(subject: object, *, alerts_enabled: bool = False) -> InlineKeyboardMarkup:
    """DEX Screener main menu."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📊 Top tokens", callback_data="dex:top"),
        InlineKeyboardButton(text="🚀 Launchpad",  callback_data="dex:launchpad"),
    )
    builder.row(InlineKeyboardButton(text="⚠️ Risk Analysis", callback_data="dex:risk"))
    alert_label = "🔔 Alerts: [ON]" if alerts_enabled else "🔕 Alerts: [OFF]"
    alert_data = "dex:alert_off" if alerts_enabled else "dex:alert_on"
    builder.row(InlineKeyboardButton(text=alert_label, callback_data=alert_data))
    builder.row(InlineKeyboardButton(text=get_text(subject, "button_back_to_menu"), callback_data="menu"))
    return builder.as_markup()


def dex_top_keyboard(subject: object) -> InlineKeyboardMarkup:
    """Controls shown below the DEX top-tokens list."""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=get_text(subject, "button_refresh"), callback_data="dex:top"))
    builder.row(
        InlineKeyboardButton(text="Risk Analysis", callback_data="dex:risk"),
        InlineKeyboardButton(text="← DEX Menu", callback_data="dex"),
    )
    builder.row(InlineKeyboardButton(text=get_text(subject, "button_back_to_menu"), callback_data="menu"))
    return builder.as_markup()


def dex_risk_select_keyboard(subject: object, tokens: list[dict]) -> InlineKeyboardMarkup:
    """Token selector for risk analysis — one button per token, 2 per row."""
    builder = InlineKeyboardBuilder()
    row: list[InlineKeyboardButton] = []
    for token in tokens:
        symbol = str(token.get("symbol") or "?")[:12]
        address = str(token.get("address") or "")
        if not address:
            continue
        btn = InlineKeyboardButton(text=symbol, callback_data=f"dex:risk:{address}")
        row.append(btn)
        if len(row) == 2:
            builder.row(*row)
            row = []
    if row:
        builder.row(*row)
    builder.row(InlineKeyboardButton(text="← DEX Menu", callback_data="dex"))
    builder.row(InlineKeyboardButton(text=get_text(subject, "button_back_to_menu"), callback_data="menu"))
    return builder.as_markup()


def dex_risk_detail_keyboard(subject: object, token_address: str = "") -> InlineKeyboardMarkup:
    """Controls shown below a risk analysis result."""
    builder = InlineKeyboardBuilder()
    if token_address:
        builder.row(
            InlineKeyboardButton(text="Refresh", callback_data=f"dex:risk:{token_address}"),
        )
    builder.row(
        InlineKeyboardButton(text="← Select Token", callback_data="dex:risk"),
        InlineKeyboardButton(text="← DEX Menu", callback_data="dex"),
    )
    builder.row(InlineKeyboardButton(text=get_text(subject, "button_back_to_menu"), callback_data="menu"))
    return builder.as_markup()


# ── Launchpad keyboards ───────────────────────────────────────────────────────

def launchpad_menu_keyboard(subject: object) -> InlineKeyboardMarkup:
    """Launchpad Assistant main submenu."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🆕 New Listings",  callback_data="launchpad:listings"),
        InlineKeyboardButton(text="💪 Strong Tokens", callback_data="launchpad:strong"),
    )
    builder.row(
        InlineKeyboardButton(text="📡 Early Signals", callback_data="launchpad:signals"),
        InlineKeyboardButton(text="⚠️ Risk Analysis", callback_data="launchpad:risk"),
    )
    builder.row(InlineKeyboardButton(text="📌 Watchlist", callback_data="launchpad:watchlist"))
    builder.row(
        InlineKeyboardButton(text="← DEX Menu", callback_data="dex"),
        InlineKeyboardButton(text=get_text(subject, "button_back_to_menu"), callback_data="menu"),
    )
    return builder.as_markup()


def launchpad_listings_keyboard(subject: object) -> InlineKeyboardMarkup:
    """Controls below the new-listings summary."""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔄 Обновить", callback_data="launchpad:listings:refresh"))
    builder.row(
        InlineKeyboardButton(text="← Launchpad", callback_data="dex:launchpad"),
        InlineKeyboardButton(text=get_text(subject, "button_back_to_menu"), callback_data="menu"),
    )
    return builder.as_markup()


def launchpad_listing_detail_keyboard(subject: object, index: int = 0) -> InlineKeyboardMarkup:
    """Controls below a single new-listing card."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🔄 Обновить",      callback_data=f"launchpad:listings:detail:{index}"),
        InlineKeyboardButton(text="⚠️ Risk Analysis", callback_data=f"launchpad:risk:idx:{index}"),
    )
    builder.row(
        InlineKeyboardButton(text="← Список",   callback_data="launchpad:listings"),
        InlineKeyboardButton(text="← Launchpad", callback_data="dex:launchpad"),
    )
    builder.row(InlineKeyboardButton(text=get_text(subject, "button_back_to_menu"), callback_data="menu"))
    return builder.as_markup()


def launchpad_strong_keyboard(subject: object) -> InlineKeyboardMarkup:
    """Controls below the strong-tokens list."""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔄 Обновить", callback_data="launchpad:strong:refresh"))
    builder.row(
        InlineKeyboardButton(text="← Launchpad", callback_data="dex:launchpad"),
        InlineKeyboardButton(text=get_text(subject, "button_back_to_menu"), callback_data="menu"),
    )
    return builder.as_markup()


def launchpad_signals_keyboard(subject: object) -> InlineKeyboardMarkup:
    """Controls below the early-signals list."""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔄 Обновить", callback_data="launchpad:signals:refresh"))
    builder.row(
        InlineKeyboardButton(text="← Launchpad", callback_data="dex:launchpad"),
        InlineKeyboardButton(text=get_text(subject, "button_back_to_menu"), callback_data="menu"),
    )
    return builder.as_markup()


def launchpad_risk_select_keyboard(subject: object, tokens: list[dict]) -> InlineKeyboardMarkup:
    """Token selector for risk analysis — 2 per row, based on current listings."""
    builder = InlineKeyboardBuilder()
    row: list[InlineKeyboardButton] = []
    for token in tokens:
        symbol = str(token.get("symbol") or "?")[:10]
        address = str(token.get("address") or "")
        if not address:
            continue
        btn = InlineKeyboardButton(text=symbol, callback_data=f"launchpad:risk:{address}")
        row.append(btn)
        if len(row) == 2:
            builder.row(*row)
            row = []
    if row:
        builder.row(*row)
    builder.row(InlineKeyboardButton(text="← Launchpad", callback_data="dex:launchpad"))
    builder.row(InlineKeyboardButton(text=get_text(subject, "button_back_to_menu"), callback_data="menu"))
    return builder.as_markup()


def launchpad_risk_detail_keyboard(subject: object, token_address: str = "") -> InlineKeyboardMarkup:
    """Controls below a full analysis card."""
    builder = InlineKeyboardBuilder()
    if token_address:
        builder.row(InlineKeyboardButton(text="🔄 Обновить", callback_data=f"launchpad:risk:{token_address}"))
    builder.row(
        InlineKeyboardButton(text="← Выбрать токен", callback_data="launchpad:risk"),
        InlineKeyboardButton(text="← Launchpad",     callback_data="dex:launchpad"),
    )
    builder.row(InlineKeyboardButton(text=get_text(subject, "button_back_to_menu"), callback_data="menu"))
    return builder.as_markup()


def launchpad_watchlist_keyboard(subject: object, addresses: list[str]) -> InlineKeyboardMarkup:
    """Watchlist panel — one row per token with Remove button."""
    builder = InlineKeyboardBuilder()
    for addr in addresses:
        short = addr[:12] + "…"
        builder.row(
            InlineKeyboardButton(text=short,    callback_data=f"launchpad:wl:info:{addr}"),
            InlineKeyboardButton(text="❌ Удалить", callback_data=f"launchpad:wl:rm:{addr}"),
        )
    builder.row(InlineKeyboardButton(text="➕ Добавить токен", callback_data="launchpad:wl:add"))
    builder.row(
        InlineKeyboardButton(text="← Launchpad", callback_data="dex:launchpad"),
        InlineKeyboardButton(text=get_text(subject, "button_back_to_menu"), callback_data="menu"),
    )
    return builder.as_markup()


def launchpad_back_keyboard(subject: object) -> InlineKeyboardMarkup:
    """Back button to launchpad menu."""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="← Launchpad", callback_data="dex:launchpad"))
    builder.row(InlineKeyboardButton(text=get_text(subject, "button_back_to_menu"), callback_data="menu"))
    return builder.as_markup()


def launchpad_main_keyboard(subject: object) -> InlineKeyboardMarkup:
    """Alias for launchpad_menu_keyboard."""
    return launchpad_menu_keyboard(subject)


def launchpad_watchlist_add_keyboard(subject: object) -> InlineKeyboardMarkup:
    """Shown while waiting for user to send a token address."""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="← Watchlist", callback_data="launchpad:watchlist"))
    return builder.as_markup()


# Backward-compat aliases kept for any external references
def launchpad_keyboard(subject: object) -> InlineKeyboardMarkup:
    return launchpad_listings_keyboard(subject)


def launchpad_detail_keyboard(subject: object, index: int = 0) -> InlineKeyboardMarkup:
    return launchpad_listing_detail_keyboard(subject, index)


# ── Leaderboard keyboards ─────────────────────────────────────────────────────

def leaderboard_keyboard(subject: object) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text=get_text(subject, "button_refresh"), callback_data="leaderboard"),
        InlineKeyboardButton(text=get_text(subject, "lb_search_token"), callback_data="leaderboard:search"),
    )
    builder.row(InlineKeyboardButton(text=get_text(subject, "button_back_to_menu"), callback_data="menu"))
    return builder.as_markup()


def leaderboard_search_keyboard(subject: object) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=get_text(subject, "button_back_to_menu"), callback_data="menu"))
    return builder.as_markup()
