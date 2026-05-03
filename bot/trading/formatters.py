from __future__ import annotations

from html import escape

from bot.database.models import Position, RealizedPnL, Trade
from bot.trading.analytics import TradingSummary
from bot.trading.service import TradingStats


# ── Helpers ───────────────────────────────────────────────────────────────────

def _pnl(value: float) -> str:
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:,.2f} USD"


def _pct(value: float) -> str:
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:.2f}%"


def _price(value: float) -> str:
    if value == 0:
        return "0 USD"
    if value >= 1:
        return f"{value:,.2f} USD"
    if value >= 0.0001:
        return f"{value:.4f} USD"
    return f"{value:.8f} USD"


def _ts(trade: Trade) -> str:
    return trade.timestamp.strftime("%b %d %H:%M")


# ── Write confirmation ────────────────────────────────────────────────────────

def format_trade_added(trade: Trade) -> str:
    fee_line = f"\nFee: {trade.fee:.2f} USD" if trade.fee else ""
    return (
        f"{trade.side} {escape(trade.symbol)}\n"
        f"Amount: {trade.amount:.6g}\n"
        f"Price: {_price(trade.price)}\n"
        f"Total: {_price(abs(trade.total_usd))}"
        f"{fee_line}"
    )


# ── Positions ─────────────────────────────────────────────────────────────────

def format_positions(
    positions: list[Position],
    price_map: dict[str, float],
) -> str:
    if not positions:
        return "No open positions."

    lines = ["POSITIONS", ""]
    for pos in positions:
        current = price_map.get(pos.token_id)
        lines.append(escape(pos.symbol))
        lines.append(f"Amount: {pos.amount:.6g}")
        lines.append(f"Avg price: {_price(pos.avg_price)}")
        if current is not None:
            upnl = (current - pos.avg_price) * pos.amount
            pct = (current - pos.avg_price) / pos.avg_price * 100 if pos.avg_price else 0.0
            lines.append(f"Current: {_price(current)}")
            lines.append(f"Unrealized PnL: {_pnl(upnl)} ({_pct(pct)})")
        else:
            lines.append("Current: n/a")
        lines.append("")
    return "\n".join(lines).rstrip()


# ── History ───────────────────────────────────────────────────────────────────

def format_trade_history(trades: list[Trade], *, period_label: str = "") -> str:
    if not trades:
        return "No trades recorded."

    header = f"HISTORY{(' ' + period_label) if period_label else ''}"
    lines = [header, ""]
    for trade in trades:
        fee_part = f" | Fee {trade.fee:.2f}" if trade.fee else ""
        lines.append(
            f"{trade.side} {escape(trade.symbol)} "
            f"{trade.amount:.6g} @ {trade.price:,.2f}"
            f"  {_ts(trade)}{fee_part}"
        )
    return "\n".join(lines)


# ── PnL summary ───────────────────────────────────────────────────────────────

def format_pnl_summary(
    records: list[RealizedPnL],
    positions: list[Position],
    price_map: dict[str, float],
) -> str:
    lines = ["PNL SUMMARY", ""]

    realized_by_token: dict[str, float] = {}
    for r in records:
        net = r.pnl - r.fee
        realized_by_token[r.symbol] = realized_by_token.get(r.symbol, 0.0) + net
    total_realized = sum(realized_by_token.values())

    unrealized_by_token: dict[str, float] = {}
    for pos in positions:
        current = price_map.get(pos.token_id)
        if current is not None:
            unrealized_by_token[pos.symbol] = (current - pos.avg_price) * pos.amount
    total_unrealized = sum(unrealized_by_token.values())

    if realized_by_token:
        lines.append("Realized:")
        for sym, val in sorted(realized_by_token.items()):
            lines.append(f"  {escape(sym)}: {_pnl(val)}")
        lines.append(f"  Total: {_pnl(total_realized)}")
        lines.append("")

    if unrealized_by_token:
        lines.append("Unrealized:")
        for sym, val in sorted(unrealized_by_token.items()):
            lines.append(f"  {escape(sym)}: {_pnl(val)}")
        lines.append(f"  Total: {_pnl(total_unrealized)}")
        lines.append("")

    lines.append(f"Grand Total: {_pnl(total_realized + total_unrealized)}")
    return "\n".join(lines)


# ── Trading summary (time-based) ──────────────────────────────────────────────

def format_trading_summary(summary: TradingSummary) -> str:
    sign = "+" if summary.realized_pnl >= 0 else ""
    return "\n".join([
        f"TRADING SUMMARY ({summary.period_days} DAYS)",
        "",
        f"Trades: {summary.total_trades}",
        f"Volume: {summary.total_volume_usd:,.0f} USD",
        f"Realized PnL: {sign}{summary.realized_pnl:,.2f} USD",
        f"Win rate: {summary.win_rate * 100:.0f}%",
        f"Win / Loss: {summary.win_trades} / {summary.loss_trades}",
    ])


# ── All-time stats ────────────────────────────────────────────────────────────

def format_trading_stats(stats: TradingStats) -> str:
    return "\n".join([
        "TRADING STATS",
        "",
        f"Total trades: {stats.total_trades}",
        f"Sell trades: {stats.sell_trades}",
        f"Win rate: {stats.win_rate * 100:.1f}%",
        f"Profitable / Losing: {stats.profitable_trades} / {stats.losing_trades}",
        "",
        f"Avg profit: {_pnl(stats.avg_profit_usd)}",
        f"Avg loss: {_pnl(stats.avg_loss_usd)}",
        "",
        f"Total Realized PnL: {_pnl(stats.total_realized_pnl)}",
    ])
