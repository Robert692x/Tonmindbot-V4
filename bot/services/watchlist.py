from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import User, WalletEvent, WatchedWallet

log = logging.getLogger(__name__)

_MAX_WALLETS_PER_USER = 10


class WalletAlreadyExistsError(ValueError):
    pass


class WatchlistLimitError(ValueError):
    pass


class WatchlistService:

    async def add_wallet(
        self,
        session: AsyncSession,
        user_id: int,
        address: str,
        label: str | None = None,
    ) -> WatchedWallet:
        existing = await self.get_user_wallets(session, user_id)
        if len(existing) >= _MAX_WALLETS_PER_USER:
            raise WatchlistLimitError(f"Maximum {_MAX_WALLETS_PER_USER} wallets per user")

        wallet = WatchedWallet(
            user_id=user_id,
            address=address.strip(),
            label=label or None,
            alerts_enabled=True,
        )
        session.add(wallet)
        try:
            await session.flush()
        except IntegrityError:
            await session.rollback()
            raise WalletAlreadyExistsError(f"{address} is already in your watchlist")
        return wallet

    async def remove_wallet(
        self, session: AsyncSession, user_id: int, wallet_id: int
    ) -> bool:
        result = await session.execute(
            select(WatchedWallet).where(
                WatchedWallet.id == wallet_id,
                WatchedWallet.user_id == user_id,
            )
        )
        wallet = result.scalar_one_or_none()
        if wallet is None:
            return False
        await session.delete(wallet)
        return True

    async def toggle_alerts(
        self, session: AsyncSession, user_id: int, wallet_id: int, enabled: bool
    ) -> WatchedWallet | None:
        result = await session.execute(
            select(WatchedWallet).where(
                WatchedWallet.id == wallet_id,
                WatchedWallet.user_id == user_id,
            )
        )
        wallet = result.scalar_one_or_none()
        if wallet is None:
            return None
        wallet.alerts_enabled = enabled
        return wallet

    async def get_user_wallets(
        self, session: AsyncSession, user_id: int
    ) -> list[WatchedWallet]:
        result = await session.execute(
            select(WatchedWallet)
            .where(WatchedWallet.user_id == user_id)
            .order_by(WatchedWallet.created_at.asc())
        )
        return list(result.scalars().all())

    async def remove_by_address(
        self, session: AsyncSession, user_id: int, address: str
    ) -> bool:
        result = await session.execute(
            select(WatchedWallet).where(
                WatchedWallet.user_id == user_id,
                WatchedWallet.address == address.strip(),
            )
        )
        wallet = result.scalar_one_or_none()
        if wallet is None:
            return False
        await session.delete(wallet)
        return True

    async def rename_wallet(
        self, session: AsyncSession, user_id: int, address: str, label: str
    ) -> WatchedWallet | None:
        result = await session.execute(
            select(WatchedWallet).where(
                WatchedWallet.user_id == user_id,
                WatchedWallet.address == address.strip(),
            )
        )
        wallet = result.scalar_one_or_none()
        if wallet is None:
            return None
        wallet.label = label.strip() or None
        return wallet

    async def get_all_active_with_telegram_id(
        self, session: AsyncSession
    ) -> list[tuple[WatchedWallet, int]]:
        """Returns (wallet, telegram_id) for all wallets with alerts enabled."""
        result = await session.execute(
            select(WatchedWallet, User.telegram_id)
            .join(User, User.id == WatchedWallet.user_id)
            .where(WatchedWallet.alerts_enabled.is_(True))
        )
        return list(result.all())

    async def get_last_tx_hash(
        self, session: AsyncSession, wallet_id: int
    ) -> str | None:
        result = await session.execute(
            select(WalletEvent.tx_hash)
            .where(WalletEvent.wallet_id == wallet_id)
            .order_by(WalletEvent.timestamp.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def record_event(
        self,
        session: AsyncSession,
        *,
        wallet_id: int,
        tx_hash: str,
        event_type: str,
        amount: float,
        token: str,
        counterparty: str,
        timestamp: datetime,
    ) -> WalletEvent | None:
        """Insert a WalletEvent. Returns None if tx_hash already recorded (duplicate)."""
        existing = await session.execute(
            select(WalletEvent.id).where(WalletEvent.tx_hash == tx_hash)
        )
        if existing.scalar_one_or_none() is not None:
            return None

        event = WalletEvent(
            wallet_id=wallet_id,
            tx_hash=tx_hash,
            type=event_type,
            amount=amount,
            token=token,
            counterparty=counterparty,
            timestamp=timestamp,
        )
        session.add(event)
        await session.flush()
        return event
