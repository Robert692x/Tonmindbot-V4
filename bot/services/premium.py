from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import Subscription, User
from bot.database.repositories import SubscriptionRepository
from bot.services.tonapi import TonApiService
from config import Settings


class PremiumService:
    def __init__(self, settings: Settings, tonapi: TonApiService) -> None:
        self.settings = settings
        self.tonapi = tonapi

    @staticmethod
    def feature_set() -> dict[str, bool]:
        return {
            "unlimited_ai": True,
            "whale_alerts": True,
            "signals": True,
        }

    async def get_or_create_checkout(self, session: AsyncSession, user: User) -> Subscription:
        repository = SubscriptionRepository(session)
        pending = await repository.get_pending_for_user(user.id)
        if pending is not None:
            return pending
        return await repository.create_pending(
            user,
            amount_ton=self.settings.PREMIUM_PRICE_TON,
            duration_days=self.settings.PREMIUM_DAYS,
            features=self.feature_set(),
        )

    async def verify_user_payment(self, session: AsyncSession, user: User) -> Subscription | None:
        repository = SubscriptionRepository(session)
        pending = await repository.get_pending_for_user(user.id)
        if pending is None:
            return None
        return await self.verify_subscription_payment(session, pending)

    async def verify_subscription_payment(
        self,
        session: AsyncSession,
        subscription: Subscription,
    ) -> Subscription | None:
        payment = await self.tonapi.find_payment_transaction(
            self.settings.payment_wallet,
            subscription.payment_comment,
            subscription.amount_ton,
        )
        if payment is None:
            return None
        repository = SubscriptionRepository(session)
        await repository.mark_confirmed(subscription, payment.tx_hash)
        user = await session.get(User, subscription.user_id)
        if user is not None:
            await repository.sync_user_state(user)
        return subscription

    async def grant_referral_bonus(self, session: AsyncSession, user: User, days: int) -> Subscription:
        repository = SubscriptionRepository(session)
        bonus = await repository.create_pending(
            user,
            amount_ton=0.0,
            duration_days=days,
            features={"referral_bonus": True},
        )
        bonus.payment_comment = f"REF{user.referral_code}{int(datetime.now(timezone.utc).timestamp())}"
        await repository.mark_confirmed(bonus, tx_hash=f"referral-{bonus.payment_comment.lower()}")
        await repository.sync_user_state(user)
        return bonus
