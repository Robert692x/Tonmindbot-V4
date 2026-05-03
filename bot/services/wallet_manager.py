from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import User, WatchedWallet

log = logging.getLogger(__name__)

_MAX_WALLETS = 10
DEFAULT_ALERT_TYPES: dict[str, bool] = {
    "tx": True,
    "whale": True,
    "risk": False,
    "behavior": False,
}


class WalletAlreadyExistsError(ValueError):
    pass


class WalletLimitError(ValueError):
    pass


@dataclass(slots=True)
class AlertConfig:
    enabled: bool
    threshold: float | None
    types: dict[str, bool]


class WalletManagerService:

    # ── User wallet management ────────────────────────────────────────────────

    async def add_wallet(
        self,
        session: AsyncSession,
        user_id: int,
        address: str,
        name: str | None = None,
    ) -> WatchedWallet:
        existing = await self.list_wallets(session, user_id)
        if len(existing) >= _MAX_WALLETS:
            raise WalletLimitError(f"Maximum {_MAX_WALLETS} wallets per account.")

        wallet = WatchedWallet(
            user_id=user_id,
            address=address.strip(),
            label=(name.strip() if name else None),
            alerts_enabled=True,
            alert_types=json.dumps(DEFAULT_ALERT_TYPES),
            flagged=False,
        )
        session.add(wallet)
        try:
            await session.flush()
        except IntegrityError:
            await session.rollback()
            raise WalletAlreadyExistsError(f"{address} is already in your list.")
        return wallet

    async def remove_wallet(
        self, session: AsyncSession, user_id: int, wallet_id: int
    ) -> bool:
        wallet = await self.get_wallet(session, user_id, wallet_id)
        if wallet is None:
            return False
        await session.delete(wallet)
        return True

    async def list_wallets(
        self, session: AsyncSession, user_id: int
    ) -> list[WatchedWallet]:
        result = await session.execute(
            select(WatchedWallet)
            .where(WatchedWallet.user_id == user_id)
            .order_by(WatchedWallet.created_at.asc())
        )
        return list(result.scalars().all())

    async def get_wallet(
        self, session: AsyncSession, user_id: int, wallet_id: int
    ) -> WatchedWallet | None:
        result = await session.execute(
            select(WatchedWallet).where(
                WatchedWallet.id == wallet_id,
                WatchedWallet.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def toggle_alerts(
        self, session: AsyncSession, user_id: int, wallet_id: int
    ) -> WatchedWallet | None:
        wallet = await self.get_wallet(session, user_id, wallet_id)
        if wallet is None:
            return None
        wallet.alerts_enabled = not wallet.alerts_enabled
        return wallet

    async def toggle_alert_type(
        self,
        session: AsyncSession,
        user_id: int,
        wallet_id: int,
        alert_type: str,
    ) -> WatchedWallet | None:
        wallet = await self.get_wallet(session, user_id, wallet_id)
        if wallet is None:
            return None
        types = self._parse_types(wallet)
        if alert_type in types:
            types[alert_type] = not types[alert_type]
        wallet.alert_types = json.dumps(types)
        return wallet

    async def set_threshold(
        self,
        session: AsyncSession,
        user_id: int,
        wallet_id: int,
        threshold: float,
    ) -> WatchedWallet | None:
        wallet = await self.get_wallet(session, user_id, wallet_id)
        if wallet is None:
            return None
        wallet.alert_threshold = threshold
        return wallet

    async def rename_wallet(
        self,
        session: AsyncSession,
        user_id: int,
        wallet_id: int,
        name: str,
    ) -> WatchedWallet | None:
        wallet = await self.get_wallet(session, user_id, wallet_id)
        if wallet is None:
            return None
        wallet.label = name.strip() or None
        return wallet

    # ── Alert helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _parse_types(wallet: WatchedWallet) -> dict[str, bool]:
        if not wallet.alert_types:
            return dict(DEFAULT_ALERT_TYPES)
        try:
            return json.loads(wallet.alert_types)
        except Exception:
            return dict(DEFAULT_ALERT_TYPES)

    def get_alert_config(self, wallet: WatchedWallet) -> AlertConfig:
        return AlertConfig(
            enabled=wallet.alerts_enabled,
            threshold=wallet.alert_threshold,
            types=self._parse_types(wallet),
        )

    # ── Admin functions ───────────────────────────────────────────────────────

    async def admin_list_wallets(
        self,
        session: AsyncSession,
        *,
        flagged_only: bool = False,
        limit: int = 30,
    ) -> list[tuple[WatchedWallet, int, str | None]]:
        """Returns (wallet, telegram_id, username) for admin view."""
        stmt = (
            select(WatchedWallet, User.telegram_id, User.username)
            .join(User, User.id == WatchedWallet.user_id)
            .order_by(WatchedWallet.created_at.desc())
            .limit(limit)
        )
        if flagged_only:
            stmt = stmt.where(WatchedWallet.flagged.is_(True))
        result = await session.execute(stmt)
        return [(row[0], row[1], row[2]) for row in result.all()]

    async def admin_get_wallet_by_id(
        self, session: AsyncSession, wallet_id: int
    ) -> tuple[WatchedWallet, int, str | None] | None:
        result = await session.execute(
            select(WatchedWallet, User.telegram_id, User.username)
            .join(User, User.id == WatchedWallet.user_id)
            .where(WatchedWallet.id == wallet_id)
        )
        row = result.first()
        return (row[0], row[1], row[2]) if row else None

    async def admin_toggle_flag(
        self, session: AsyncSession, wallet_id: int
    ) -> WatchedWallet | None:
        result = await session.execute(
            select(WatchedWallet).where(WatchedWallet.id == wallet_id)
        )
        wallet = result.scalar_one_or_none()
        if wallet is None:
            return None
        wallet.flagged = not wallet.flagged
        return wallet

    async def admin_set_note(
        self, session: AsyncSession, wallet_id: int, note: str
    ) -> WatchedWallet | None:
        result = await session.execute(
            select(WatchedWallet).where(WatchedWallet.id == wallet_id)
        )
        wallet = result.scalar_one_or_none()
        if wallet is None:
            return None
        wallet.moderator_note = note.strip() or None
        return wallet

    async def admin_set_risk_override(
        self, session: AsyncSession, wallet_id: int, level: str | None
    ) -> WatchedWallet | None:
        result = await session.execute(
            select(WatchedWallet).where(WatchedWallet.id == wallet_id)
        )
        wallet = result.scalar_one_or_none()
        if wallet is None:
            return None
        wallet.risk_override = level
        return wallet

    async def admin_remove_wallet(
        self, session: AsyncSession, wallet_id: int
    ) -> bool:
        result = await session.execute(
            select(WatchedWallet).where(WatchedWallet.id == wallet_id)
        )
        wallet = result.scalar_one_or_none()
        if wallet is None:
            return False
        await session.delete(wallet)
        return True
