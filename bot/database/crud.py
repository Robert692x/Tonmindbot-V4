from __future__ import annotations
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from bot.database.models import Message, Payment, User
from config import settings


async def get_user(session: AsyncSession, telegram_id: int) -> Optional[User]:
    r = await session.execute(select(User).where(User.telegram_id == telegram_id))
    return r.scalar_one_or_none()


async def get_or_create_user(session, telegram_id, username=None,
                              first_name=None, ref_code=None) -> tuple[User, bool]:
    user = await get_user(session, telegram_id)
    if user:
        user.username = username
        user.first_name = first_name
        return user, False

    ref_by = None
    if ref_code:
        r = await session.execute(select(User).where(User.referral_code == ref_code))
        referrer = r.scalar_one_or_none()
        if referrer and referrer.telegram_id != telegram_id:
            ref_by = referrer.id
            referrer.referral_count += 1
            referrer.premium_until = (
                max(referrer.premium_until or datetime.now(timezone.utc), datetime.now(timezone.utc))
                + timedelta(days=settings.REFERRAL_BONUS_DAYS)
            )
            referrer.is_premium = True

    user = User(
        telegram_id=telegram_id, username=username, first_name=first_name,
        referral_code=uuid.uuid4().hex[:6].upper(), referred_by_id=ref_by,
    )
    session.add(user)
    await session.flush()
    return user, True


async def set_wallet(session, telegram_id, wallet):
    user = await get_user(session, telegram_id)
    if user:
        user.ton_wallet = wallet
    return user


async def activate_premium(session, telegram_id, days=30):
    user = await get_user(session, telegram_id)
    if not user:
        return None
    now = datetime.now(timezone.utc)
    base = max(user.premium_until or now, now)
    user.premium_until = base + timedelta(days=days)
    user.is_premium = True
    return user


async def check_premium(session, user: User) -> User:
    if user.is_premium and user.premium_until:
        if user.premium_until < datetime.now(timezone.utc):
            user.is_premium = False
    return user


async def get_ai_used(user: User) -> int:
    now = datetime.now(timezone.utc)
    if user.ai_reset_at and user.ai_reset_at.date() == now.date():
        return user.ai_requests_today
    return 0


async def increment_ai(session, user: User) -> int:
    now = datetime.now(timezone.utc)
    if not user.ai_reset_at or user.ai_reset_at.date() < now.date():
        user.ai_requests_today = 0
        user.ai_reset_at = now
    user.ai_requests_today += 1
    return user.ai_requests_today


async def save_message(session, user_id, prompt, response, model=None):
    msg = Message(user_id=user_id, prompt=prompt, response=response, model=model)
    session.add(msg)
    await session.flush()
    return msg


async def create_payment(session, user: User) -> Payment:
    memo = uuid.uuid4().hex[:8].upper()
    p = Payment(
        user_id=user.id, telegram_id=user.telegram_id,
        amount_ton=settings.PREMIUM_PRICE_TON, memo=memo,
        premium_days=settings.PREMIUM_DAYS,
    )
    session.add(p)
    await session.flush()
    return p


async def get_pending_payments(session):
    r = await session.execute(select(Payment).where(Payment.status == "pending"))
    return list(r.scalars().all())


async def confirm_payment(session, payment: Payment, tx_hash: str):
    payment.tx_hash = tx_hash
    payment.status = "confirmed"
    payment.confirmed_at = datetime.now(timezone.utc)


async def set_language(session, telegram_id, lang):
    user = await get_user(session, telegram_id)
    if user:
        user.language = lang
    return user
