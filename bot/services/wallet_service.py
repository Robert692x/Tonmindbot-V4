from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime

from bot.services.tonapi import JettonHolding, TonApiService, TransactionRecord

log = logging.getLogger(__name__)

_DUST_TON = 0.001


@dataclass(slots=True)
class WalletBalance:
    address: str
    balance_ton: float
    last_activity: datetime | None


@dataclass
class WalletData:
    """Complete wallet snapshot fetched directly from the blockchain."""
    address: str
    balance: WalletBalance
    transactions: list[TransactionRecord]
    jettons: list[JettonHolding]
    total_in: float    # sum of all incoming TON (non-dust)
    total_out: float   # sum of all outgoing TON (non-dust)

    @property
    def pnl(self) -> float:
        """Flow-based PNL = total_in - total_out."""
        return self.total_in - self.total_out

    @property
    def tx_count(self) -> int:
        return len(self.transactions)

    @property
    def avg_tx_volume(self) -> float:
        if not self.transactions:
            return 0.0
        total = sum(tx.amount_ton for tx in self.transactions if tx.amount_ton >= _DUST_TON)
        count = sum(1 for tx in self.transactions if tx.amount_ton >= _DUST_TON)
        return total / count if count else 0.0

    def top_addresses(self, n: int = 5) -> list[tuple[str, int]]:
        """Return top N counterparty addresses by interaction count."""
        from collections import Counter
        counter: Counter[str] = Counter()
        for tx in self.transactions:
            if tx.counterparty != "unknown":
                counter[tx.counterparty] += 1
        return counter.most_common(n)


class WalletService:
    """Pure data-fetching layer for wallet information from TON blockchain."""

    def __init__(self, tonapi: TonApiService) -> None:
        self._tonapi = tonapi

    async def get_balance(self, address: str) -> WalletBalance:
        """Fetch current on-chain balance and last activity timestamp."""
        report = await self._tonapi.get_wallet_report(address, limit=1)
        return WalletBalance(
            address=report.address,
            balance_ton=report.balance_ton,
            last_activity=report.last_activity,
        )

    async def get_transactions(
        self,
        address: str,
        *,
        limit: int = 200,
    ) -> list[TransactionRecord]:
        """Fetch up to `limit` recent transactions from the blockchain.

        Direction is determined by the TON API: IN when the wallet receives,
        OUT when it sends.
        """
        raw = await self._tonapi.get_pnl_transactions(address, limit=limit)
        return [record for record, _fee in raw]

    async def get_jettons(self, address: str) -> list[JettonHolding]:
        """Fetch all non-spam jetton (token) balances for the wallet."""
        return await self._tonapi.get_wallet_portfolio(address, limit=50)

    async def get_wallet_data(self, address: str) -> WalletData:
        """Fetch complete wallet state in parallel: balance + transactions + tokens.

        All values come directly from tonapi.io / TON blockchain — no placeholders.
        """
        address = address.strip()

        balance, transactions, jettons = await asyncio.gather(
            self.get_balance(address),
            self.get_transactions(address),
            self.get_jettons(address),
        )

        total_in = sum(
            tx.amount_ton for tx in transactions
            if tx.direction == "IN" and tx.amount_ton >= _DUST_TON
        )
        total_out = sum(
            tx.amount_ton for tx in transactions
            if tx.direction == "OUT" and tx.amount_ton >= _DUST_TON
        )

        return WalletData(
            address=address,
            balance=balance,
            transactions=transactions,
            jettons=jettons,
            total_in=total_in,
            total_out=total_out,
        )
