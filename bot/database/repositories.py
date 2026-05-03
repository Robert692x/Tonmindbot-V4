from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone

from aiogram.types import User as TelegramUser
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import Referral, Subscription, UsageLimit, User, LaunchpadWatchlist


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        result = await self.session.execute(select(User).where(User.telegram_id == telegram_id))
        return result.scalar_one_or_none()

    async def get_by_id(self, user_id: int) -> User | None:
        result = await self.session.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def get_by_referral_code(self, referral_code: str) -> User | None:
        result = await self.session.execute(select(User).where(User.referral_code == referral_code))
        return result.scalar_one_or_none()

    async def get_or_create_from_telegram(self, telegram_user: TelegramUser) -> User:
        user = await self.get_by_telegram_id(telegram_user.id)
        now = datetime.now(timezone.utc)
        if user is None:
            user = User(
                telegram_id=telegram_user.id,
                username=telegram_user.username,
                first_name=telegram_user.first_name,
                last_name=telegram_user.last_name,
                language_code=telegram_user.language_code or "en",
                referral_code=uuid.uuid4().hex[:8].upper(),
                last_seen_at=now,
            )
            self.session.add(user)
            try:
                await self.session.flush()
                return user
            except IntegrityError:
                await self.session.rollback()
                user = await self.get_by_telegram_id(telegram_user.id)
                if user is None:
                    raise

        user.username = telegram_user.username
        user.first_name = telegram_user.first_name
        user.last_name = telegram_user.last_name
        if not user.language_code and telegram_user.language_code:
            user.language_code = telegram_user.language_code
        user.last_seen_at = now
        return user

    async def set_wallet_address(self, user: User, wallet_address: str) -> User:
        user.wallet_address = wallet_address
        return user

    async def set_language(self, user: User, language_code: str) -> User:
        user.language_code = language_code
        return user

    async def set_alert_preferences(
        self,
        user: User,
        *,
        price_alerts_enabled: bool | None = None,
        whale_alerts_enabled: bool | None = None,
        signals_enabled: bool | None = None,
    ) -> User:
        if price_alerts_enabled is not None:
            user.price_alerts_enabled = price_alerts_enabled
        if whale_alerts_enabled is not None:
            user.whale_alerts_enabled = whale_alerts_enabled
        if signals_enabled is not None:
            user.signals_enabled = signals_enabled
        return user

    async def list_whale_alert_subscribers(self) -> list[User]:
        result = await self.session.execute(
            select(User).where(User.whale_alerts_enabled.is_(True))
        )
        return list(result.scalars().all())

    async def list_dex_alert_subscribers(self) -> list[User]:
        result = await self.session.execute(
            select(User).where(User.dex_alerts_enabled.is_(True))
        )
        return list(result.scalars().all())

    async def set_dex_alerts_enabled(self, user: User, enabled: bool) -> User:
        user.dex_alerts_enabled = enabled
        return user


class SubscriptionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def expire_outdated(self, user: User | None = None) -> None:
        now = datetime.now(timezone.utc)
        statement = select(Subscription).where(
            Subscription.status == "active",
            Subscription.expires_at.is_not(None),
            Subscription.expires_at <= now,
        )
        if user is not None:
            statement = statement.where(Subscription.user_id == user.id)
        result = await self.session.execute(statement)
        for subscription in result.scalars().all():
            subscription.status = "expired"

    async def get_active_for_user(self, user_id: int) -> Subscription | None:
        now = datetime.now(timezone.utc)
        result = await self.session.execute(
            select(Subscription)
            .where(
                Subscription.user_id == user_id,
                Subscription.status == "active",
                Subscription.expires_at.is_not(None),
                Subscription.expires_at > now,
            )
            .order_by(Subscription.expires_at.desc())
        )
        return result.scalars().first()

    async def get_pending_for_user(self, user_id: int) -> Subscription | None:
        result = await self.session.execute(
            select(Subscription)
            .where(Subscription.user_id == user_id, Subscription.status == "pending")
            .order_by(Subscription.created_at.desc())
        )
        return result.scalars().first()

    async def get_by_comment(self, payment_comment: str) -> Subscription | None:
        result = await self.session.execute(
            select(Subscription).where(Subscription.payment_comment == payment_comment)
        )
        return result.scalar_one_or_none()

    async def list_pending(self) -> list[Subscription]:
        result = await self.session.execute(
            select(Subscription).where(Subscription.status == "pending").order_by(Subscription.created_at.asc())
        )
        return list(result.scalars().all())

    async def create_pending(
        self,
        user: User,
        *,
        amount_ton: float,
        duration_days: int,
        features: dict[str, bool],
    ) -> Subscription:
        subscription = Subscription(
            user_id=user.id,
            amount_ton=amount_ton,
            duration_days=duration_days,
            payment_comment=f"TM{uuid.uuid4().hex[:10].upper()}",
            features=features,
        )
        self.session.add(subscription)
        await self.session.flush()
        return subscription

    async def mark_confirmed(self, subscription: Subscription, tx_hash: str) -> Subscription:
        now = datetime.now(timezone.utc)
        current_active = await self.get_active_for_user(subscription.user_id)
        if current_active and current_active.id != subscription.id:
            current_active.status = "extended"
        base_time = max(
            now,
            current_active.expires_at if current_active and current_active.expires_at else now,
        )
        subscription.status = "active"
        subscription.payment_tx_hash = tx_hash
        subscription.confirmed_at = now
        subscription.started_at = now
        subscription.expires_at = base_time + timedelta(days=subscription.duration_days)
        return subscription

    async def sync_user_state(self, user: User) -> User:
        await self.expire_outdated(user)
        active = await self.get_active_for_user(user.id)
        user.is_premium = active is not None
        user.premium_expires_at = active.expires_at if active else None
        return user


class UsageLimitRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_today_usage(self, user_id: int, feature: str, period_date: date | None = None) -> UsageLimit | None:
        scope_date = period_date or datetime.now(timezone.utc).date()
        result = await self.session.execute(
            select(UsageLimit).where(
                UsageLimit.user_id == user_id,
                UsageLimit.feature == feature,
                UsageLimit.period_date == scope_date,
            )
        )
        return result.scalar_one_or_none()

    async def get_usage_count(self, user_id: int, feature: str) -> int:
        usage = await self.get_today_usage(user_id, feature)
        return usage.usage_count if usage else 0

    async def increment(self, user_id: int, feature: str) -> UsageLimit:
        now = datetime.now(timezone.utc)
        usage = await self.get_today_usage(user_id, feature, now.date())
        if usage is None:
            usage = UsageLimit(
                user_id=user_id,
                feature=feature,
                period_date=now.date(),
                usage_count=0,
            )
            self.session.add(usage)
            await self.session.flush()
        usage.usage_count += 1
        usage.last_requested_at = now
        return usage


class ReferralRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def attach_referral(self, referrer: User, referred_user: User) -> bool:
        if referrer.id == referred_user.id:
            return False
        existing = await self.session.execute(
            select(Referral).where(Referral.referred_user_id == referred_user.id)
        )
        if existing.scalar_one_or_none() is not None:
            return False
        referral = Referral(referrer_user_id=referrer.id, referred_user_id=referred_user.id)
        self.session.add(referral)
        await self.session.flush()
        return True

    async def count_for_user(self, user_id: int) -> int:
        result = await self.session.execute(
            select(func.count(Referral.id)).where(Referral.referrer_user_id == user_id)
        )
        return int(result.scalar() or 0)


class LaunchpadWatchlistRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add_token(self, user_id: int, token_address: str, token_symbol: str | None = None) -> bool:
        """Add token to watchlist. Returns True if added, False if already exists."""
        try:
            entry = LaunchpadWatchlist(
                user_id=user_id,
                token_address=token_address,
                token_symbol=token_symbol,
            )
            self.session.add(entry)
            await self.session.flush()
            return True
        except IntegrityError:
            await self.session.rollback()
            return False

    async def remove_token(self, user_id: int, token_address: str) -> bool:
        """Remove token from watchlist. Returns True if removed."""
        result = await self.session.execute(
            select(LaunchpadWatchlist).where(
                LaunchpadWatchlist.user_id == user_id,
                LaunchpadWatchlist.token_address == token_address,
            )
        )
        entry = result.scalar_one_or_none()
        if entry:
            await self.session.delete(entry)
            await self.session.flush()
            return True
        return False

    async def get_user_watchlist(self, user_id: int) -> list[LaunchpadWatchlist]:
        """Get all tokens in user's watchlist."""
        result = await self.session.execute(
            select(LaunchpadWatchlist)
            .where(LaunchpadWatchlist.user_id == user_id)
            .order_by(LaunchpadWatchlist.created_at.desc())
        )
        return list(result.scalars().all())

    async def is_in_watchlist(self, user_id: int, token_address: str) -> bool:
        """Check if token is in user's watchlist."""
        result = await self.session.execute(
            select(LaunchpadWatchlist).where(
                LaunchpadWatchlist.user_id == user_id,
                LaunchpadWatchlist.token_address == token_address,
            )
        )
        return result.scalar_one_or_none() is not None

    async def count_watchlist(self, user_id: int) -> int:
        """Count tokens in user's watchlist."""
        result = await self.session.execute(
            select(func.count(LaunchpadWatchlist.id)).where(LaunchpadWatchlist.user_id == user_id)
        )
        return int(result.scalar() or 0)
