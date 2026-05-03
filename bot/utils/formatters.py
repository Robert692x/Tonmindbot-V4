from __future__ import annotations

from datetime import datetime, timezone
from html import escape

from bot.database.models import Subscription, User
from bot.services.algo import AlgoHolder
from bot.services.i18n import get_text
from bot.services.market import DexPoolSnapshot, TonMarketSnapshot, TokenSnapshot
from bot.services.tonapi import JettonHolding, TransactionRecord, WalletReport, WhaleTransfer
from bot.analytics.network_engine import NetworkReport
from bot.analytics.score_engine import WalletScore
from bot.services.wallet_analytics import WalletBehaviorReport, WalletPnL
from bot.utils.i18n import t
from bot.utils.links import address_link, address_url, tx_link


def _fmt_price(value: float) -> str:
    if value == 0:
        return "$0"
    if value >= 1:
        return f"${value:,.2f}"
    if value >= 0.001:
        return f"${value:.4f}"
    return f"${value:.8f}"


def _fmt_large_usd(value: float) -> str:
    if value >= 1e12:
        return f"${value / 1e12:.2f}T"
    if value >= 1e9:
        return f"${value / 1e9:.2f}B"
    if value >= 1e6:
        return f"${value / 1e6:.2f}M"
    return f"${value:,.0f}"


def _fmt_change(pct: float | None) -> str:
    if pct is None:
        return "n/a"
    sign = "+" if pct >= 0 else ""
    return f"{sign}{pct:.2f}%"


# ── Plain-text helpers (no emoji, no $ abbreviation) ─────────────────────────

def _fmt_price_plain(value: float) -> str:
    if value == 0:
        return "0 USD"
    if value >= 1:
        return f"{value:,.2f} USD"
    if value >= 0.01:
        return f"{value:.4f} USD"
    if value >= 0.0001:
        return f"{value:.6f} USD"
    return f"{value:.8f} USD"


def _fmt_change_plain(pct: float | None) -> str:
    if pct is None:
        return "n/a"
    sign = "+" if pct >= 0 else ""
    return f"{sign}{pct:.2f}%"


def shorten_address(address: str, *, head: int = 5, tail: int = 3) -> str:
    if len(address) <= head + tail + 3:
        return address
    return f"{address[:head]}...{address[-tail:]}"


def format_dt(subject: object, value: datetime | None) -> str:
    if value is None:
        return get_text(subject, "value_na")
    return value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _rank_emoji(index: int) -> str:
    return f"{index}."


def format_portfolio(subject: object, portfolio: list[JettonHolding]) -> str:
    from bot.utils.links import address_link
    lines = [f"<b>{t(subject, 'fmt_portfolio')}</b>", ""]
    if not portfolio:
        lines.append(t(subject, "fmt_no_tokens"))
        return "\n".join(lines)

    for holding in portfolio:
        balance_str = f"{holding.balance:,.0f}" if holding.balance >= 1 else f"{holding.balance:.6f}"
        lines.append(f"Token: <b>{escape(holding.symbol)}</b>")
        if holding.jetton_address:
            lines.append("Contract:")
            lines.append(address_link(holding.jetton_address))
        lines.append(f"Balance: {balance_str}")
        lines.append("")

    lines.append(f"{t(subject, 'fmt_total_tokens')}: {len(portfolio)}")
    return "\n".join(lines)


def format_wallet(subject: object, report: WalletReport) -> str:
    lines = [
        f"<b>{t(subject, 'fmt_wallet')}</b>",
        "",
        f"{t(subject, 'label_address')}: {address_link(report.address)}",
        f"{t(subject, 'fmt_balance')}: <b>{report.balance_ton:,.4f} TON</b>",
        f"{t(subject, 'fmt_last_activity')}: {format_dt(subject, report.last_activity)}",
        "",
        f"{t(subject, 'fmt_transactions')}: {len(report.transactions)}",
        f"{t(subject, 'fmt_tokens')}: {len(report.portfolio)}",
        f"{t(subject, 'fmt_risk')}: <b>{report.risk.level.upper()}</b>",
    ]
    return "\n".join(lines)


def format_wallet_report(subject: object, report: WalletReport) -> str:
    """Backward-compat alias for format_wallet."""
    return format_wallet(subject, report)


def format_wallet_analytics(subject: object, report: WalletReport, market: TonMarketSnapshot) -> str:
    usd_value = report.balance_ton * market.price_usd
    inflow = sum(tx.amount_ton for tx in report.transactions if tx.direction == "IN")
    outflow = sum(tx.amount_ton for tx in report.transactions if tx.direction == "OUT")
    return "\n".join(
        [
            get_text(subject, "analytics_title"),
            f"{get_text(subject, 'label_address')}: {address_link(report.address)}",
            f"{get_text(subject, 'label_holdings')}: <b>{report.balance_ton:,.4f} TON</b> (${usd_value:,.2f})",
            f"{get_text(subject, 'label_change_24h')}: <b>{market.change_24h_pct:+.2f}%</b>",
            f"{get_text(subject, 'label_recent_inflow')}: <b>{inflow:,.3f} TON</b>",
            f"{get_text(subject, 'label_recent_outflow')}: <b>{outflow:,.3f} TON</b>",
            f"{get_text(subject, 'label_risk_profile')}: <b>{report.risk.level.upper()}</b>",
            f"{get_text(subject, 'label_signals')}:",
            *[f"- {escape(get_text(subject, reason) if reason.startswith('risk_') else reason)}" for reason in report.risk.reasons],
        ]
    )


def format_market_snapshot(subject: object, snapshot: TonMarketSnapshot) -> str:
    return "\n".join(
        [
            get_text(subject, "market_title"),
            f"{get_text(subject, 'label_price')}: <b>${snapshot.price_usd:,.4f}</b>",
            f"{get_text(subject, 'label_change_24h')}: <b>{snapshot.change_24h_pct:+.2f}%</b>",
            f"{get_text(subject, 'label_volume_24h')}: <b>${snapshot.volume_24h_usd:,.0f}</b>",
            f"{get_text(subject, 'label_market_cap')}: <b>${snapshot.market_cap_usd:,.0f}</b>",
        ]
    )


def format_whales(subject: object, whales: list[WhaleTransfer]) -> str:
    from bot.utils.links import address_link, tx_link
    lines = [get_text(subject, "whales_title"), ""]
    if not whales:
        lines.append(get_text(subject, "whales_empty"))
        return "\n".join(lines)
    for whale in whales[:8]:
        source_label = whale.source_label or ""
        dest_label = whale.destination_label or ""
        lines.append(f"<b>{whale.amount_ton:,.0f} TON</b>  {format_dt(subject, whale.timestamp)}")
        lines.append(f"From: {escape(source_label) + ' ' if source_label else ''}{address_link(whale.from_address)}")
        lines.append(f"To:   {escape(dest_label) + ' ' if dest_label else ''}{address_link(whale.to_address)}")
        lines.append("")
    return "\n".join(lines).rstrip()


def format_whale_alert(subject: object, whale: WhaleTransfer) -> str:
    from bot.utils.links import address_link, tx_link
    source_label = f"{escape(whale.source_label)} " if whale.source_label else ""
    dest_label = f"{escape(whale.destination_label)} " if whale.destination_label else ""
    return "\n".join([
        get_text(subject, "whale_alert_title"),
        "",
        f"{get_text(subject, 'label_amount')}: <b>{whale.amount_ton:,.0f} TON</b>",
        f"{get_text(subject, 'label_time')}: {format_dt(subject, whale.timestamp)}",
        "",
        "From:",
        f"{source_label}{address_link(whale.from_address)}",
        "",
        "To:",
        f"{dest_label}{address_link(whale.to_address)}",
        "",
        "Tx:",
        tx_link(whale.tx_hash),
    ])


def format_dex_pools(subject: object, pools: list[DexPoolSnapshot]) -> str:
    lines = [get_text(subject, "dex_title")]
    if not pools:
        lines.append(get_text(subject, "dex_empty"))
        return "\n".join(lines)
    for pool in pools:
        apy = f"{pool.apy_1d:.2f}%" if pool.apy_1d is not None else get_text(subject, "value_na")
        lines.append(
            f"- <b>{escape(pool.token0)}/{escape(pool.token1)}</b> | TVL ${pool.tvl_usd:,.0f} | APY 1d {apy}"
        )
    return "\n".join(lines)


def format_profile(subject: object, user: User, referral_count: int, bot_username: str) -> str:
    referral_link = f"https://t.me/{bot_username}?start=ref_{user.referral_code}"
    return "\n".join(
        [
            get_text(subject, "profile_title"),
            f"{get_text(subject, 'label_telegram_id')}: <code>{user.telegram_id}</code>",
            f"{get_text(subject, 'label_wallet')}: <code>{escape(user.wallet_address or get_text(subject, 'value_not_connected'))}</code>",
            f"{get_text(subject, 'label_premium')}: <b>{get_text(subject, 'value_premium_active' if user.is_premium else 'value_premium_free')}</b>",
            f"{get_text(subject, 'label_premium_until')}: {format_dt(subject, user.premium_expires_at)}",
            f"{get_text(subject, 'label_referral_count')}: <b>{referral_count}</b>",
            f"{get_text(subject, 'label_referral_link')}: <code>{escape(referral_link)}</code>",
        ]
    )


def format_premium(subject: object, subscription: Subscription | None, payment_wallet: str, price_ton: float, duration_days: int) -> str:
    lines = [
        get_text(subject, "premium_title"),
        f"{get_text(subject, 'label_plan')}: <b>{duration_days} days</b>",
        f"{get_text(subject, 'label_price')}: <b>{price_ton:.2f} TON</b>",
        "",
        get_text(subject, "premium_unlocks"),
        f"- {get_text(subject, 'premium_unlock_unlimited_ai')}",
        f"- {get_text(subject, 'premium_unlock_whale_alerts')}",
        f"- {get_text(subject, 'premium_unlock_signals')}",
    ]
    if subscription is not None:
        lines.extend(
            [
                "",
                get_text(subject, "premium_payment_instructions"),
                f"{get_text(subject, 'premium_send_exactly')} <b>{price_ton:.2f} TON</b> to",
                f"<code>{escape(payment_wallet)}</code>",
                f"{get_text(subject, 'label_comment')}: <code>{escape(subscription.payment_comment)}</code>",
                "",
                get_text(subject, "premium_after_payment"),
            ]
        )
    return "\n".join(lines)


def format_ai_landing(subject: object, used: int, limit: int | None, is_premium: bool) -> str:
    quota = get_text(subject, "ai_quota_unlimited") if is_premium or limit is None else get_text(subject, "ai_quota_used", used=used, limit=limit)
    return "\n".join(
        [
            get_text(subject, "ai_title"),
            get_text(subject, "ai_intro"),
            f"{get_text(subject, 'label_daily_quota')}: <b>{quota}</b>",
            "",
            f"{get_text(subject, 'label_examples')}:",
            f"- {get_text(subject, 'ai_example_1')}",
            f"- {get_text(subject, 'ai_example_2')}",
            f"- {get_text(subject, 'ai_example_3')}",
        ]
    )


def format_settings(subject: object) -> str:
    return "\n".join(
        [
            get_text(subject, "settings_title"),
            get_text(subject, "settings_language_prompt"),
        ]
    )


def format_leaderboard(subject: object, holders: list[AlgoHolder], total_supply: float | None) -> str:
    lines = [get_text(subject, "leaderboard_title"), ""]
    if not holders:
        lines.append(get_text(subject, "leaderboard_unavailable"))
        return "\n".join(lines)
    for holder in holders:
        percent = (
            f" ({holder.percent_of_supply:.2f}%)"
            if holder.percent_of_supply is not None
            else f" ({get_text(subject, 'leaderboard_supply_missing')})"
        )
        lines.append(f"{holder.rank}.")
        lines.append(address_link(holder.owner_address))
        lines.append(f"{holder.balance:,.3f} ALGO{percent}")
        lines.append("")
    if total_supply is not None:
        lines.extend(["", f"{get_text(subject, 'label_total_supply')}: {total_supply:,.3f} ALGO"])
    return "\n".join(lines)


def format_token_leaderboard(
    subject: object,
    token_address: str,
    symbol: str,
    total_supply: float | None,
    holders: list,
) -> str:
    """Full-address leaderboard — URL-per-line format, no address truncation."""
    from bot.utils.links import address_link

    lines = [
        f"<b>{get_text(subject, 'lb_top_holders')}</b>",
        "",
    ]

    if not holders:
        lines.append(get_text(subject, "leaderboard_unavailable"))
    else:
        for h in holders:
            pct = f"{h.percent_of_supply:.4f}%" if h.percent_of_supply is not None else "n/a"
            bal = f"{h.balance:,.2f}" if h.balance >= 1 else f"{h.balance:.6f}"
            lines.append(f"{h.rank}.")
            lines.append(address_link(h.owner_address))
            lines.append("")
            lines.append(f"{bal} {escape(symbol)}")
            lines.append(pct)
            lines.append("")

    if total_supply is not None:
        lines.append(f"Total supply: {total_supply:,.2f} {escape(symbol)}")

    lines.append("")
    lines.append("Token:")
    lines.append(address_link(token_address))

    return "\n".join(lines).rstrip()


def format_price_card(subject: object, token: TokenSnapshot) -> str:
    lines = [
        "TOKEN",
        "",
        f"Name: {escape(token.name)}",
        f"Symbol: {escape(token.symbol)}",
        "",
        f"Price: {_fmt_price_plain(token.price_usd)}",
        f"Change 1h: {_fmt_change_plain(token.change_1h_pct)}",
        f"Change 24h: {_fmt_change_plain(token.change_24h_pct)}",
        f"Market Cap: {int(token.market_cap_usd):,} USD",
    ]
    return "\n".join(lines)


def format_market_overview(subject: object, tokens: list[TokenSnapshot]) -> str:
    lines = ["MARKET OVERVIEW", ""]
    for token in tokens:
        lines += [
            escape(token.name.upper()),
            f"Price: {_fmt_price_plain(token.price_usd)}",
            f"Change 1h: {_fmt_change_plain(token.change_1h_pct)}",
            f"Change 24h: {_fmt_change_plain(token.change_24h_pct)}",
            "",
        ]
    return "\n".join(lines).rstrip()


def format_trending(subject: object, tokens: list[TokenSnapshot]) -> str:
    if not tokens:
        return get_text(subject, "price_trending_empty")
    lines = ["TRENDING", ""]
    for i, token in enumerate(tokens, 1):
        lines.append(
            f"{i}. {escape(token.name)} ({escape(token.symbol)})"
            f" — {_fmt_price_plain(token.price_usd)}"
            f" | 24h: {_fmt_change_plain(token.change_24h_pct)}"
        )
    return "\n".join(lines)


def format_wallet_pnl(pnl: WalletPnL) -> str:
    sign = "+" if pnl.profit >= 0 else ""
    return "\n".join([
        f"WALLET SUMMARY ({pnl.period_days}D)",
        "",
        f"Total Inflow:  {pnl.inflow:,.4f} TON",
        f"Total Outflow: {pnl.outflow:,.4f} TON",
        f"Net Result:    {sign}{pnl.profit:,.4f} TON",
        "",
        f"Fees Paid:     {pnl.fees:,.4f} TON",
        f"Transactions:  {pnl.tx_count}",
    ])


def format_watchlist(wallets: list) -> str:
    from bot.utils.links import address_link
    if not wallets:
        return "WATCHED WALLETS\n\nNo wallets added yet."
    lines = ["<b>WATCHED WALLETS</b>", ""]
    for i, w in enumerate(wallets, 1):
        status = "ON" if w.alerts_enabled else "OFF"
        lines.append(f"{i}.")
        lines.append(address_link(w.address))
        if w.label:
            lines.append(f"Label: {escape(w.label)}")
        lines.append(f"Alerts: {status}")
        lines.append("")
    return "\n".join(lines).rstrip()


_SEP = "━━━━━━━━━━━━━━━━━━━━━"

_RISK_EMOJI = {
    "LOW": "",
    "MEDIUM": "",
    "HIGH": "",
    "CRITICAL": "",
}

_FLIPPER_EMOJI = {
    "Investor": "",
    "Trader": "",
    "Flipper": "",
}


def format_transactions(
    subject: object,
    transactions: list[TransactionRecord],
    total_in: float,
    total_out: float,
    tx_count: int,
    days: int,
    wallet_address: str = "",
) -> str:
    from bot.utils.links import address_link, tx_link
    net = total_in - total_out
    net_sign = "+" if net >= 0 else ""

    lines = [
        f"<b>{t(subject, 'fmt_transactions')} ({days}D)</b>",
        "",
    ]

    if not transactions:
        lines.append(t(subject, "fmt_no_transactions"))
    else:
        for tx in transactions[:10]:
            sign = "+" if tx.direction == "IN" else "-"
            label = t(subject, "fmt_in") if tx.direction == "IN" else t(subject, "fmt_out")
            lines.append(f"<b>{label} {sign}{tx.amount_ton:,.4f} TON</b>")
            lines.append("")

            if tx.direction == "IN":
                lines.append("From:")
                lines.append(address_link(tx.counterparty))
                if wallet_address:
                    lines.append("To:")
                    lines.append(address_link(wallet_address))
            else:
                if wallet_address:
                    lines.append("From:")
                    lines.append(address_link(wallet_address))
                lines.append("To:")
                lines.append(address_link(tx.counterparty))

            lines.append("")
            lines.append(f"Time: {format_dt(subject, tx.timestamp)}")

            if tx.tx_hash:
                lines.append("Tx:")
                lines.append(tx_link(tx.tx_hash))

            lines.append("")

    summary = (
        f"{tx_count} {t(subject, 'fmt_tx')} | "
        f"{t(subject, 'fmt_in')} +{total_in:,.2f} | "
        f"{t(subject, 'fmt_out')} -{total_out:,.2f} | "
        f"{t(subject, 'fmt_net')} {net_sign}{net:,.2f} TON"
    )
    lines.append(summary)

    if tx_count > 10:
        lines.append(f"<i>+{tx_count - 10} more</i>")

    return "\n".join(lines)


def format_wallet_transactions(
    subject: object,
    transactions: list[TransactionRecord],
    total_in: float,
    total_out: float,
    tx_count: int,
    days: int,
) -> str:
    """Backward-compat alias for format_transactions."""
    return format_transactions(subject, transactions, total_in, total_out, tx_count, days)


def format_pnl(subject: object, pnl: WalletPnL) -> str:
    sign = "+" if pnl.profit >= 0 else ""

    return "\n".join([
        f"<b>{t(subject, 'fmt_pnl')} ({pnl.period_days}D)</b>",
        "",
        f"{t(subject, 'fmt_in')}: +{pnl.inflow:,.4f} TON",
        f"{t(subject, 'fmt_out')}: -{pnl.outflow:,.4f} TON",
        f"{t(subject, 'fmt_net')}: <b>{sign}{pnl.profit:,.4f} TON</b>",
        f"Fees: {pnl.fees:,.4f} TON",
        f"{t(subject, 'fmt_tx')}: {pnl.tx_count}",
    ])


def format_wallet_pnl_detail(subject: object, pnl: WalletPnL) -> str:
    """Backward-compat alias for format_pnl."""
    return format_pnl(subject, pnl)


def format_analysis(subject: object, behavior: WalletBehaviorReport) -> str:
    from bot.utils.links import address_link
    age = f"{behavior.wallet_age_days}d" if behavior.wallet_age_days is not None else "n/a"
    net_sign = "+" if behavior.net_flow >= 0 else ""
    tx_per_day = behavior.flipper.trades_per_day
    hold = (
        f"{behavior.flipper.avg_hold_hours:.0f}h"
        if behavior.flipper.avg_hold_hours is not None else "n/a"
    )
    top = behavior.frequent_addresses[0] if behavior.frequent_addresses else None

    lines = [
        f"<b>{t(subject, 'fmt_analysis')}</b>",
        "",
        address_link(behavior.address),
        f"Age: {age}",
        "",
        f"{t(subject, 'fmt_flow')} ({behavior.period_days}D)",
        f"+{behavior.total_in:,.2f} / -{behavior.total_out:,.2f} TON",
        f"{t(subject, 'fmt_net')}: <b>{net_sign}{behavior.net_flow:,.2f} TON</b>",
        "",
        t(subject, "fmt_activity"),
        f"{behavior.total_tx_count} {t(subject, 'fmt_tx')} | "
        f"{behavior.unique_addresses} {t(subject, 'fmt_addr')} | "
        f"{tx_per_day:.1f}/{t(subject, 'fmt_day')}",
        "",
        t(subject, "fmt_behavior"),
        f"{t(subject, 'fmt_type')}: <b>{behavior.flipper.label}</b>",
        f"{t(subject, 'fmt_hold')}: {hold}",
        f"IN/OUT: {behavior.flipper.in_out_ratio:.2f}",
        "",
        f"{t(subject, 'fmt_risk')}: <b>{behavior.risk.level}</b>",
        "",
        "Top interaction:",
    ]

    if top:
        lines += [
            address_link(top.address),
            f"tx: {top.tx_count}",
            f"volume: {top.total_volume:,.0f} TON",
        ]
    else:
        lines.append(t(subject, "fmt_no_data"))

    lines += [
        "",
        t(subject, "fmt_insight"),
        behavior.ai_conclusion,
    ]

    return "\n".join(lines)


def format_wallet_deep_analysis(subject: object, behavior: WalletBehaviorReport) -> str:
    """Backward-compat alias for format_analysis."""
    return format_analysis(subject, behavior)


# ── Command-output helpers ────────────────────────────────────────────────────

def _wallet_type(balance_ton: float, behavior: WalletBehaviorReport) -> str:
    if balance_ton >= 10_000:
        return "Whale"
    return behavior.flipper.label


def _activity_label(tx_per_day: float) -> str:
    if tx_per_day > 10:
        return "High"
    if tx_per_day > 2:
        return "Moderate"
    if tx_per_day > 0.2:
        return "Low"
    return "Minimal"


# ── Compact /wallet command output ────────────────────────────────────────────

def format_wallet_brief(
    address: str,
    balance_ton: float,
    behavior: WalletBehaviorReport,
) -> str:
    from bot.utils.links import address_link
    w_type = _wallet_type(balance_ton, behavior)
    activity = _activity_label(behavior.flipper.trades_per_day)
    first_date = behavior.first_tx_date.strftime("%Y-%m-%d") if behavior.first_tx_date else "unknown"

    return "\n".join([
        "<b>Wallet</b>",
        "",
        address_link(address),
        "",
        f"Balance:   <b>{balance_ton:,.4f} TON</b>",
        f"Activity:  <b>{activity}</b>",
        f"Type:      <b>{w_type}</b>",
        f"Risk:      <b>{behavior.risk.level}</b>",
        "",
        f"Created:   {first_date}",
        f"Txs (30d): {behavior.total_tx_count}",
        f"Unique:    {behavior.unique_addresses} addresses",
    ])


# ── /score command output ─────────────────────────────────────────────────────

def format_wallet_score(address: str, score: WalletScore) -> str:
    from bot.utils.links import address_link
    sign = "+" if score.risk_penalty >= 0 else ""

    return "\n".join([
        "<b>Wallet Score</b>",
        "",
        address_link(address),
        "",
        f"Score:    <b>{score.total}/100</b>  ({score.grade})",
        "",
        f"Activity:     {score.activity_score:>2}/30  — {score.activity_label}",
        f"Volume:       {score.volume_score:>2}/25",
        f"Age:          {score.age_score:>2}/20",
        f"Diversity:    {score.diversity_score:>2}/15",
        f"Balance:      {score.balance_bonus:>2}/10",
        f"Risk penalty: {sign}{score.risk_penalty}",
        "",
        f"Behavior: <b>{score.behavior_type}</b>",
        f"Risk:     <b>{score.risk_level}</b>",
    ])


# ── /network command output ───────────────────────────────────────────────────

def format_network_report(address: str, report: NetworkReport) -> str:
    from bot.utils.links import address_link

    lines = [
        "<b>Network Analysis</b>",
        "",
        address_link(address),
        "",
        f"Total connections: <b>{report.total_connections}</b>",
        f"Mutual wallets:    <b>{report.mutual_count}</b>",
    ]

    if report.cluster_detected:
        lines.append("Cluster detected — multiple recurring mutual relationships")

    lines += ["", "<b>Top connected wallets:</b>"]

    for i, node in enumerate(report.nodes, 1):
        mutual_tag = " (mutual)" if node.is_mutual else ""
        label = f" [{escape(node.label)}]" if node.label else ""
        lines.append(f"{i}.{label}{mutual_tag}")
        lines.append(address_link(node.address))
        lines.append(
            f"{node.tx_count} txs | {node.total_volume:,.1f} TON | "
            f"IN:{node.in_count} OUT:{node.out_count}"
        )
        lines.append("")

    if not report.nodes:
        lines.append("No connections found in this transaction window.")

    return "\n".join(lines).rstrip()


# ── /activity command output ──────────────────────────────────────────────────

def format_activity_report(address: str, activity: dict[str, int]) -> str:
    from bot.utils.links import address_link
    today = activity.get("today", 0)
    yesterday = activity.get("yesterday", 0)
    week = activity.get("week", 0)
    trend = " (up)" if today > yesterday else (" (down)" if today < yesterday else "")

    return "\n".join([
        "<b>Activity</b>",
        "",
        address_link(address),
        "",
        f"Today:     <b>{today} txs</b>{trend}",
        f"Yesterday: <b>{yesterday} txs</b>",
        f"7 days:    <b>{week} txs</b>",
    ])


# ── /pnl command (brief) ──────────────────────────────────────────────────────

def format_pnl_brief(address: str, pnl: WalletPnL) -> str:
    from bot.utils.links import address_link
    sign = "+" if pnl.profit >= 0 else ""
    pct = (pnl.profit / max(pnl.outflow, 0.001)) * 100 if pnl.outflow else 0

    return "\n".join([
        f"<b>PNL ({pnl.period_days}D)</b>",
        "",
        address_link(address),
        "",
        f"<b>{sign}{pnl.profit:,.4f} TON ({sign}{pct:.1f}%)</b>",
        "",
        f"IN:   +{pnl.inflow:,.4f} TON",
        f"OUT:  -{pnl.outflow:,.4f} TON",
        f"Fees:  {pnl.fees:,.4f} TON",
        f"Txs:   {pnl.tx_count}",
    ])


# ── /tx command (brief) ───────────────────────────────────────────────────────

def format_txs_brief(
    address: str,
    transactions: list[TransactionRecord],
    total_in: float,
    total_out: float,
    count: int,
    days: int,
) -> str:
    from bot.utils.links import address_link, tx_link
    net = total_in - total_out
    sign = "+" if net >= 0 else ""

    lines = [
        f"<b>Transactions ({days}D)</b>",
        "",
        address_link(address),
        "",
        f"Total: {count} | IN: +{total_in:,.2f} | OUT: -{total_out:,.2f} | Net: {sign}{net:,.2f} TON",
        "",
    ]

    for tx in transactions[:8]:
        dir_label = "IN" if tx.direction == "IN" else "OUT"
        sign_tx = "+" if tx.direction == "IN" else "-"
        lines.append(f"{dir_label} {sign_tx}{tx.amount_ton:,.4f} TON")
        if tx.direction == "IN":
            lines.append("From:")
        else:
            lines.append("To:")
        lines.append(address_link(tx.counterparty))
        if tx.tx_hash:
            lines.append("Tx:")
            lines.append(tx_link(tx.tx_hash))
        lines.append("")

    if count > 8:
        lines.append(f"<i>+{count - 8} more in this window</i>")

    return "\n".join(lines).rstrip()


# ── Smart alert formats ───────────────────────────────────────────────────────

def format_smart_alert(address: str, tx_count: int, total_vol: float, window_minutes: int) -> str:
    from bot.utils.links import address_link
    return "\n".join([
        "<b>Smart Alert</b>",
        "",
        address_link(address),
        "",
        f"{tx_count} transactions in <b>{window_minutes} min</b>",
        f"Total volume: <b>{total_vol:,.1f} TON</b>",
    ])


def format_dump_alert(address: str, amount_ton: float) -> str:
    from bot.utils.links import address_link
    return "\n".join([
        "<b>Dump Alert</b>",
        "",
        address_link(address),
        "",
        f"Sudden large outflow: <b>{amount_ton:,.1f} TON</b>",
    ])


def format_whale_alert_brief(address: str, amount_ton: float, direction: str) -> str:
    from bot.utils.links import address_link
    arrow = "IN" if direction == "IN" else "OUT"
    return "\n".join([
        "<b>Whale Alert</b>",
        "",
        address_link(address),
        "",
        f"{arrow}: <b>{amount_ton:,.0f} TON</b>",
    ])


# ── Wallet Manager formatters ─────────────────────────────────────────────────

def format_wallet_manager(subject: object, wallets: list) -> str:
    lines = [f"<b>{t(subject, 'wm_title')}</b>", ""]
    if not wallets:
        lines.append(t(subject, "wm_no_wallets"))
        return "\n".join(lines)

    lines.append(f"{t(subject, 'wm_wallets_count')}: {len(wallets)}")
    lines.append("")
    from bot.utils.links import address_link
    for i, w in enumerate(wallets, 1):
        status = t(subject, "wm_alerts_on") if w.alerts_enabled else t(subject, "wm_alerts_off")
        flag = " [!]" if getattr(w, "flagged", False) else ""
        label = f"  {escape(w.label)}" if w.label else ""
        lines.append(f"{i}.{label}{flag}")
        lines.append(address_link(w.address))
        lines.append(f"Alerts: {status}")
        lines.append("")

    return "\n".join(lines)


def format_wallet_detail(
    subject: object,
    wallet: object,
    balance_ton: float,
    last_activity: object,
    tx_count: int,
    risk_level: str,
    behavior: str,
    alert_config: object,
) -> str:
    from bot.utils.links import address_link
    raw_addr = getattr(wallet, "address", "unknown")
    name = escape(getattr(wallet, "label", None) or "")
    flag_note = f"[!] {escape(wallet.moderator_note)}" if getattr(wallet, "moderator_note", None) else ""
    risk = getattr(wallet, "risk_override", None) or risk_level
    status = t(subject, "wm_alerts_on") if getattr(alert_config, "enabled", False) else t(subject, "wm_alerts_off")
    thr = getattr(alert_config, "threshold", None)
    thr_str = f"{thr:,.0f} TON" if thr else t(subject, "wm_global_threshold")
    types = getattr(alert_config, "types", {})

    lines = [
        f"<b>{t(subject, 'wm_wallet_title')}</b>",
    ]
    if name:
        lines.append(f"Label: {name}")
    lines += [
        "",
        address_link(raw_addr),
        "",
        f"{t(subject, 'fmt_balance')}: <b>{balance_ton:,.4f} TON</b>",
        f"{t(subject, 'fmt_last_activity')}: {last_activity}",
        "",
        f"{t(subject, 'fmt_transactions')}: {tx_count}",
        f"{t(subject, 'fmt_risk')}: <b>{risk}</b>",
        f"{t(subject, 'fmt_behavior')}: {behavior}",
        "",
        f"Alerts: <b>{status}</b>",
        f"Threshold: {thr_str}",
        f"TX: {'ON' if types.get('tx') else 'OFF'}  "
        f"Whale: {'ON' if types.get('whale') else 'OFF'}  "
        f"Risk: {'ON' if types.get('risk') else 'OFF'}  "
        f"Behavior: {'ON' if types.get('behavior') else 'OFF'}",
    ]
    if flag_note:
        lines.append(flag_note)
    return "\n".join(lines)


def format_admin_wallet_list(
    subject: object,
    entries: list[tuple],
    flagged_only: bool,
) -> str:
    title = t(subject, "admin_flagged_title") if flagged_only else t(subject, "admin_wallets_title")
    lines = [f"<b>{title}</b>", f"{len(entries)} {t(subject, 'fmt_tx')}s", ""]

    from bot.utils.links import address_link
    for wallet, tg_id, username in entries:
        user_str = f"@{username}" if username else f"#{tg_id}"
        flag = " [!]" if wallet.flagged else ""
        lines.append(f"{escape(user_str)}{flag}  /awm_{wallet.id}")
        lines.append(address_link(wallet.address))
        lines.append("")

    return "\n".join(lines)


def format_admin_wallet_detail(
    subject: object,
    wallet: object,
    tg_id: int,
    username: str | None,
) -> str:
    addr = escape(wallet.address)
    user_str = f"@{username}" if username else f"#{tg_id}"
    flag_str = "[FLAGGED]" if wallet.flagged else "clean"
    risk_ov = wallet.risk_override or "none"
    note = escape(wallet.moderator_note or "—")
    thr = f"{wallet.alert_threshold:,.0f} TON" if wallet.alert_threshold else "global"

    lines = [
        f"<b>{t(subject, 'admin_wallet_title')}</b>",
        "",
        address_link(wallet.address),
        f"User: {escape(user_str)}",
        "",
        f"Status: {flag_str}",
        f"Risk override: {risk_ov}",
        f"Note: {note}",
        "",
        f"Threshold: {thr}",
        f"Alert types: {wallet.alert_types or 'default'}",
    ]
    return "\n".join(lines)


def format_wallet_alert(wallet: object, tx: TransactionRecord) -> str:
    addr = getattr(wallet, "address", "unknown")
    label = getattr(wallet, "label", None)
    name = escape(label) if label else escape(addr)
    sign = "+" if tx.direction == "IN" else "-"

    lines = [
        "<b>WALLET ALERT</b>",
        "",
        f"Name: {name}",
        f"Address:",
        address_link(addr),
        "",
        f"Action: <b>{tx.direction}</b>",
        f"Amount: <b>{sign}{tx.amount_ton:,.4f} TON</b>",
        "",
    ]

    if tx.direction == "IN":
        lines += ["From:", address_link(tx.counterparty)]
    else:
        lines += ["To:", address_link(tx.counterparty)]

    lines += [
        "",
        f"Time: {tx.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}",
    ]

    if tx.tx_hash:
        lines += ["", "Transaction:", tx_link(tx.tx_hash)]

    return "\n".join(lines)
