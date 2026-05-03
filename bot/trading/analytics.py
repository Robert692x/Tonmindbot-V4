from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from bot.trading.repository import RealizedPnLRepository, TradeRepository


@dataclass(slots=True)
class TradingSummary:
    period_days: int
    total_trades: int
    total_volume_usd: float
    realized_pnl: float
    win_trades: int
    loss_trades: int
    win_rate: float  # 0.0–1.0


async def get_trading_summary(
    session: AsyncSession, user_id: int, days: int
) -> TradingSummary:
    since: datetime = datetime.now(timezone.utc) - timedelta(days=days)

    trades_repo = TradeRepository(session)
    pnl_repo = RealizedPnLRepository(session)

    trades = await trades_repo.get_history_since(user_id, since, limit=1000)
    pnl_records = await pnl_repo.get_for_user_since(user_id, since)

    total_volume = sum(abs(t.total_usd) for t in trades)

    # Group PnL per sell trade to get one result per completed sell
    sell_pnls: dict[int, float] = {}
    for r in pnl_records:
        sell_pnls[r.sell_trade_id] = (
            sell_pnls.get(r.sell_trade_id, 0.0) + r.pnl - r.fee
        )

    results = list(sell_pnls.values())
    wins = [v for v in results if v > 0]
    losses = [v for v in results if v <= 0]
    n = len(results)

    return TradingSummary(
        period_days=days,
        total_trades=len(trades),
        total_volume_usd=total_volume,
        realized_pnl=sum(results),
        win_trades=len(wins),
        loss_trades=len(losses),
        win_rate=len(wins) / n if n else 0.0,
    )
