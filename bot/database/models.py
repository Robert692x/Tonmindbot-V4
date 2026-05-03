from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import BigInteger, Boolean, Date, DateTime, Float, ForeignKey, Integer, JSON, String, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    language_code: Mapped[str] = mapped_column(String(8), default="en")
    wallet_address: Mapped[str | None] = mapped_column(String(128), nullable=True)
    referral_code: Mapped[str] = mapped_column(String(16), unique=True, index=True, default=lambda: uuid.uuid4().hex[:8].upper())
    price_alerts_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    whale_alerts_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    signals_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    dex_alerts_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    is_premium: Mapped[bool] = mapped_column(Boolean, default=False)
    premium_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    subscriptions: Mapped[list["Subscription"]] = relationship(back_populates="user")
    usage_limits: Mapped[list["UsageLimit"]] = relationship(back_populates="user")
    referrals_sent: Mapped[list["Referral"]] = relationship(
        back_populates="referrer",
        foreign_keys="Referral.referrer_user_id",
    )
    referral_source: Mapped[list["Referral"]] = relationship(
        back_populates="referred_user",
        foreign_keys="Referral.referred_user_id",
    )


class Subscription(TimestampMixin, Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    plan_name: Mapped[str] = mapped_column(String(32), default="premium")
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    amount_ton: Mapped[float] = mapped_column(Float)
    duration_days: Mapped[int] = mapped_column(Integer, default=30)
    payment_comment: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    payment_tx_hash: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True)
    features: Mapped[dict[str, bool]] = mapped_column(JSON, default=dict)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship(back_populates="subscriptions")


class UsageLimit(TimestampMixin, Base):
    __tablename__ = "usage_limits"
    __table_args__ = (UniqueConstraint("user_id", "feature", "period_date", name="uq_usage_limits_scope"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    feature: Mapped[str] = mapped_column(String(64), index=True)
    period_date: Mapped[date] = mapped_column(Date, index=True)
    usage_count: Mapped[int] = mapped_column(Integer, default=0)
    last_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship(back_populates="usage_limits")


class Referral(TimestampMixin, Base):
    __tablename__ = "referrals"
    __table_args__ = (UniqueConstraint("referred_user_id", name="uq_referrals_referred_user_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    referrer_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    referred_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)

    referrer: Mapped["User"] = relationship(
        back_populates="referrals_sent",
        foreign_keys=[referrer_user_id],
    )
    referred_user: Mapped["User"] = relationship(
        back_populates="referral_source",
        foreign_keys=[referred_user_id],
    )


# ── Trading ledger ────────────────────────────────────────────────────────────

class Trade(Base):
    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_id: Mapped[str] = mapped_column(String(64), index=True)
    symbol: Mapped[str] = mapped_column(String(16))
    side: Mapped[str] = mapped_column(String(4))          # BUY / SELL
    amount: Mapped[float] = mapped_column(Float)
    price: Mapped[float] = mapped_column(Float)
    fee: Mapped[float] = mapped_column(Float, default=0.0)
    total_usd: Mapped[float] = mapped_column(Float)
    remaining: Mapped[float] = mapped_column(Float, default=0.0)  # BUY only: unmatched lot size
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class Position(Base):
    __tablename__ = "positions"
    __table_args__ = (UniqueConstraint("user_id", "token_id", name="uq_positions_user_token"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_id: Mapped[str] = mapped_column(String(64))
    symbol: Mapped[str] = mapped_column(String(16))
    amount: Mapped[float] = mapped_column(Float, default=0.0)
    avg_price: Mapped[float] = mapped_column(Float, default=0.0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class RealizedPnL(Base):
    __tablename__ = "realized_pnl"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_id: Mapped[str] = mapped_column(String(64), index=True)
    symbol: Mapped[str] = mapped_column(String(16))
    sell_trade_id: Mapped[int] = mapped_column(ForeignKey("trades.id", ondelete="CASCADE"), index=True)
    amount: Mapped[float] = mapped_column(Float)
    buy_price: Mapped[float] = mapped_column(Float)
    sell_price: Mapped[float] = mapped_column(Float)
    pnl: Mapped[float] = mapped_column(Float)
    fee: Mapped[float] = mapped_column(Float, default=0.0)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


# ── Wallet watchlist ──────────────────────────────────────────────────────────

class WatchedWallet(TimestampMixin, Base):
    __tablename__ = "watched_wallets"
    __table_args__ = (UniqueConstraint("user_id", "address", name="uq_watched_wallets_user_address"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    address: Mapped[str] = mapped_column(String(128), index=True)
    label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    alerts_enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    # Per-wallet alert configuration
    alert_threshold: Mapped[float | None] = mapped_column(Float, nullable=True)
    alert_types: Mapped[str | None] = mapped_column(String(256), nullable=True)  # JSON

    # Admin moderation fields
    flagged: Mapped[bool] = mapped_column(Boolean, default=False)
    moderator_note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    risk_override: Mapped[str | None] = mapped_column(String(16), nullable=True)

    events: Mapped[list["WalletEvent"]] = relationship(back_populates="wallet", cascade="all, delete-orphan")


class WalletEvent(Base):
    __tablename__ = "wallet_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    wallet_id: Mapped[int] = mapped_column(ForeignKey("watched_wallets.id", ondelete="CASCADE"), index=True)
    tx_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    type: Mapped[str] = mapped_column(String(4))            # IN / OUT
    amount: Mapped[float] = mapped_column(Float)
    token: Mapped[str] = mapped_column(String(16), default="TON")
    counterparty: Mapped[str] = mapped_column(String(128))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

    wallet: Mapped["WatchedWallet"] = relationship(back_populates="events")


# ── Launchpad token watchlist ─────────────────────────────────────────────────

class LaunchpadWatchlist(TimestampMixin, Base):
    __tablename__ = "launchpad_watchlist"
    __table_args__ = (UniqueConstraint("user_id", "token_address", name="uq_launchpad_watchlist_user_token"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_address: Mapped[str] = mapped_column(String(128), index=True)
    token_symbol: Mapped[str] = mapped_column(String(16), nullable=True)
    alerts_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    risk_threshold: Mapped[int | None] = mapped_column(Integer, nullable=True)  # Alert if risk >= threshold
