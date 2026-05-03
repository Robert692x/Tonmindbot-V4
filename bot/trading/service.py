from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import Position, RealizedPnL, Trade
from bot.trading.fifo import match_fifo
from bot.trading.repository import (
    PositionRepository,
    RealizedPnLRepository,
    TradeRepository,
)


class InsufficientPositionError(ValueError):
    pass


@dataclass(slots=True)
class TradingStats:
    total_trades: int
    sell_trades: int
    profitable_trades: int
    losing_trades: int
    win_rate: float          # 0.0–1.0
    avg_profit_usd: float
    avg_loss_usd: float
    total_realized_pnl: float


class TradingService:

    # ── Write operations ──────────────────────────────────────────────────────

    async def add_trade(
        self,
        session: AsyncSession,
        *,
        user_id: int,
        token_id: str,
        symbol: str,
        side: str,       # "BUY" or "SELL"
        amount: float,
        price: float,
        fee: float = 0.0,
    ) -> Trade:
        trades_repo = TradeRepository(session)
        positions_repo = PositionRepository(session)
        pnl_repo = RealizedPnLRepository(session)
        now = datetime.now(timezone.utc)

        if side == "BUY":
            return await self._add_buy(
                trades_repo, positions_repo,
                user_id=user_id, token_id=token_id, symbol=symbol,
                amount=amount, price=price, fee=fee, now=now,
            )
        return await self._add_sell(
            trades_repo, positions_repo, pnl_repo,
            user_id=user_id, token_id=token_id, symbol=symbol,
            amount=amount, price=price, fee=fee, now=now,
        )

    async def _add_buy(
        self,
        trades_repo: TradeRepository,
        positions_repo: PositionRepository,
        *,
        user_id: int,
        token_id: str,
        symbol: str,
        amount: float,
        price: float,
        fee: float,
        now: datetime,
    ) -> Trade:
        trade = Trade(
            user_id=user_id, token_id=token_id, symbol=symbol,
            side="BUY", amount=amount, price=price, fee=fee,
            total_usd=amount * price + fee,
            remaining=amount,
            timestamp=now,
        )
        await trades_repo.add(trade)

        position = await positions_repo.get(user_id, token_id)
        if position is None or position.amount <= 1e-10:
            new_amount = amount
            new_avg = price
        else:
            new_amount = position.amount + amount
            new_avg = (position.amount * position.avg_price + amount * price) / new_amount

        await positions_repo.upsert(
            user_id, token_id, symbol, amount=new_amount, avg_price=new_avg
        )
        return trade

    async def _add_sell(
        self,
        trades_repo: TradeRepository,
        positions_repo: PositionRepository,
        pnl_repo: RealizedPnLRepository,
        *,
        user_id: int,
        token_id: str,
        symbol: str,
        amount: float,
        price: float,
        fee: float,
        now: datetime,
    ) -> Trade:
        position = await positions_repo.get(user_id, token_id)
        available = position.amount if position else 0.0
        if available < amount - 1e-10:
            raise InsufficientPositionError(
                f"Insufficient position for {symbol}: "
                f"have {available:.6f}, selling {amount:.6f}"
            )

        trade = Trade(
            user_id=user_id, token_id=token_id, symbol=symbol,
            side="SELL", amount=amount, price=price, fee=fee,
            total_usd=amount * price - fee,
            remaining=0.0,
            timestamp=now,
        )
        await trades_repo.add(trade)

        # FIFO matching
        open_buys = await trades_repo.get_open_buys(user_id, token_id)
        fifo_result = match_fifo(
            [(b.id, b.remaining, b.price) for b in open_buys],
            amount,
            price,
        )

        # Track new remaining for each buy lot
        remaining_map: dict[int, float] = {b.id: b.remaining for b in open_buys}
        for match in fifo_result.matches:
            remaining_map[match.buy_trade_id] -= match.amount
            proportionate_fee = fee * (match.amount / amount)
            await pnl_repo.add(
                RealizedPnL(
                    user_id=user_id, token_id=token_id, symbol=symbol,
                    sell_trade_id=trade.id,
                    amount=match.amount,
                    buy_price=match.buy_price,
                    sell_price=match.sell_price,
                    pnl=match.pnl,
                    fee=proportionate_fee,
                    timestamp=now,
                )
            )

        # Persist updated buy remainders
        for buy_id, new_remaining in remaining_map.items():
            await trades_repo.update_remaining(buy_id, new_remaining)

        # Recalculate position from remaining open-buy lots
        new_amount = available - amount
        if new_amount <= 1e-10:
            new_amount = 0.0
            new_avg = 0.0
        else:
            # Weighted avg of still-open lots
            remaining_lots = [
                (max(0.0, remaining_map.get(b.id, b.remaining)), b.price)
                for b in open_buys
            ]
            total_left = sum(r for r, _ in remaining_lots)
            new_avg = (
                sum(r * p for r, p in remaining_lots if r > 0) / total_left
                if total_left > 1e-10
                else (position.avg_price if position else 0.0)
            )

        await positions_repo.upsert(
            user_id, token_id, symbol, amount=new_amount, avg_price=new_avg
        )
        return trade

    # ── Read operations ───────────────────────────────────────────────────────

    async def get_positions(
        self, session: AsyncSession, user_id: int
    ) -> list[Position]:
        return await PositionRepository(session).get_all_open(user_id)

    async def get_trade_history(
        self, session: AsyncSession, user_id: int, *, limit: int = 50
    ) -> list[Trade]:
        return await TradeRepository(session).get_history(user_id, limit=limit)

    async def get_realized_pnl_records(
        self,
        session: AsyncSession,
        user_id: int,
        *,
        token_id: str | None = None,
    ) -> list[RealizedPnL]:
        return await RealizedPnLRepository(session).get_for_user(
            user_id, token_id=token_id
        )

    @staticmethod
    def unrealized_pnl(position: Position, current_price: float) -> float:
        return (current_price - position.avg_price) * position.amount

    async def get_trading_stats(
        self, session: AsyncSession, user_id: int
    ) -> TradingStats:
        trades_repo = TradeRepository(session)
        pnl_repo = RealizedPnLRepository(session)

        total_trades = await trades_repo.count_for_user(user_id)
        records = await pnl_repo.get_for_user(user_id)

        if not records:
            return TradingStats(
                total_trades=total_trades, sell_trades=0,
                profitable_trades=0, losing_trades=0,
                win_rate=0.0, avg_profit_usd=0.0, avg_loss_usd=0.0,
                total_realized_pnl=0.0,
            )

        # Group by sell_trade_id to get per-sell-trade net PnL
        sell_pnls: dict[int, float] = {}
        for r in records:
            sell_pnls[r.sell_trade_id] = (
                sell_pnls.get(r.sell_trade_id, 0.0) + r.pnl - r.fee
            )

        sell_results = list(sell_pnls.values())
        profits = [v for v in sell_results if v > 0]
        losses = [v for v in sell_results if v <= 0]
        n = len(sell_results)

        return TradingStats(
            total_trades=total_trades,
            sell_trades=n,
            profitable_trades=len(profits),
            losing_trades=len(losses),
            win_rate=len(profits) / n if n else 0.0,
            avg_profit_usd=sum(profits) / len(profits) if profits else 0.0,
            avg_loss_usd=sum(losses) / len(losses) if losses else 0.0,
            total_realized_pnl=sum(sell_results),
        )
