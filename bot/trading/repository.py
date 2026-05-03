from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import Position, RealizedPnL, Trade


class TradeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, trade: Trade) -> Trade:
        self.session.add(trade)
        await self.session.flush()
        return trade

    async def get_open_buys(self, user_id: int, token_id: str) -> list[Trade]:
        """BUY trades with remaining > 0, sorted oldest-first for FIFO matching."""
        result = await self.session.execute(
            select(Trade)
            .where(
                Trade.user_id == user_id,
                Trade.token_id == token_id,
                Trade.side == "BUY",
                Trade.remaining > 1e-10,
            )
            .order_by(Trade.timestamp.asc(), Trade.id.asc())
        )
        return list(result.scalars().all())

    async def update_remaining(self, trade_id: int, new_remaining: float) -> None:
        trade = await self.session.get(Trade, trade_id)
        if trade is not None:
            trade.remaining = max(0.0, new_remaining)

    async def get_history(self, user_id: int, *, limit: int = 50) -> list[Trade]:
        result = await self.session.execute(
            select(Trade)
            .where(Trade.user_id == user_id)
            .order_by(Trade.timestamp.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def count_for_user(self, user_id: int) -> int:
        result = await self.session.execute(
            select(func.count(Trade.id)).where(Trade.user_id == user_id)
        )
        return int(result.scalar() or 0)

    async def get_history_since(
        self, user_id: int, since: datetime, *, limit: int = 100
    ) -> list[Trade]:
        result = await self.session.execute(
            select(Trade)
            .where(Trade.user_id == user_id, Trade.timestamp >= since)
            .order_by(Trade.timestamp.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def volume_since(self, user_id: int, since: datetime) -> float:
        result = await self.session.execute(
            select(func.sum(Trade.total_usd)).where(
                Trade.user_id == user_id, Trade.timestamp >= since
            )
        )
        return float(result.scalar() or 0.0)


class PositionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, user_id: int, token_id: str) -> Position | None:
        result = await self.session.execute(
            select(Position).where(
                Position.user_id == user_id,
                Position.token_id == token_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_all_open(self, user_id: int) -> list[Position]:
        """Return positions with amount > 0, newest updated first."""
        result = await self.session.execute(
            select(Position)
            .where(Position.user_id == user_id, Position.amount > 1e-10)
            .order_by(Position.updated_at.desc())
        )
        return list(result.scalars().all())

    async def upsert(
        self,
        user_id: int,
        token_id: str,
        symbol: str,
        *,
        amount: float,
        avg_price: float,
    ) -> Position:
        position = await self.get(user_id, token_id)
        if position is None:
            position = Position(
                user_id=user_id,
                token_id=token_id,
                symbol=symbol,
                amount=amount,
                avg_price=avg_price,
            )
            self.session.add(position)
        else:
            position.amount = amount
            position.avg_price = avg_price
        return position


class RealizedPnLRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, record: RealizedPnL) -> RealizedPnL:
        self.session.add(record)
        await self.session.flush()
        return record

    async def get_for_user(
        self, user_id: int, *, token_id: str | None = None
    ) -> list[RealizedPnL]:
        stmt = select(RealizedPnL).where(RealizedPnL.user_id == user_id)
        if token_id is not None:
            stmt = stmt.where(RealizedPnL.token_id == token_id)
        result = await self.session.execute(stmt.order_by(RealizedPnL.timestamp.desc()))
        return list(result.scalars().all())

    async def get_for_user_since(
        self, user_id: int, since: datetime
    ) -> list[RealizedPnL]:
        result = await self.session.execute(
            select(RealizedPnL)
            .where(RealizedPnL.user_id == user_id, RealizedPnL.timestamp >= since)
            .order_by(RealizedPnL.timestamp.desc())
        )
        return list(result.scalars().all())
