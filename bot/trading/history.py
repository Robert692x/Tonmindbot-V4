from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import Trade
from bot.services.tonapi import TransactionRecord
from bot.trading.repository import TradeRepository

_TON_ID = "the-open-network"
_MIN_AMOUNT = 0.01  # ignore dust transfers


@dataclass(slots=True)
class DetectedTrade:
    """Candidate trade derived from a wallet transaction (price unknown)."""
    side: str        # BUY / SELL
    symbol: str      # TON
    token_id: str    # the-open-network
    amount: float
    timestamp: datetime
    tx_hash: str


async def get_trade_history(
    session: AsyncSession,
    user_id: int,
    *,
    days: int | None = None,
    limit: int = 100,
) -> list[Trade]:
    repo = TradeRepository(session)
    if days is not None:
        since = datetime.now(timezone.utc) - timedelta(days=days)
        return await repo.get_history_since(user_id, since, limit=limit)
    return await repo.get_history(user_id, limit=limit)


def detect_trades_from_transactions(
    transactions: list[TransactionRecord],
) -> list[DetectedTrade]:
    """Map wallet transactions to candidate BUY/SELL trades.

    Incoming TON → BUY, outgoing TON → SELL.
    Dust transfers (< 0.01 TON) are skipped.
    Price is not available from on-chain data and is set to zero.
    """
    detected: list[DetectedTrade] = []
    for tx in transactions:
        if tx.amount_ton < _MIN_AMOUNT:
            continue
        detected.append(
            DetectedTrade(
                side="BUY" if tx.direction == "IN" else "SELL",
                symbol="TON",
                token_id=_TON_ID,
                amount=tx.amount_ton,
                timestamp=tx.timestamp,
                tx_hash=tx.tx_hash,
            )
        )
    return detected
