from __future__ import annotations
import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import BigInteger, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    username: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    first_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    language: Mapped[str] = mapped_column(String(4), default="ru", nullable=False)

    ton_wallet: Mapped[Optional[str]] = mapped_column(String(68), nullable=True)
    algo_balance: Mapped[float] = mapped_column(Float, default=0.0)

    is_premium: Mapped[bool] = mapped_column(Boolean, default=False)
    premium_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    ai_requests_today: Mapped[int] = mapped_column(Integer, default=0)
    ai_reset_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    referral_code: Mapped[str] = mapped_column(
        String(16), unique=True, nullable=False,
        default=lambda: uuid.uuid4().hex[:6].upper()
    )
    referred_by_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    referral_count: Mapped[int] = mapped_column(Integer, default=0)

    price_alerts_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    whale_alerts_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    messages: Mapped[list["Message"]] = relationship("Message", back_populates="user")
    payments: Mapped[list["Payment"]] = relationship("Payment", back_populates="user")


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    response: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship("User", back_populates="messages")


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    tx_hash: Mapped[Optional[str]] = mapped_column(String(128), unique=True, nullable=True)
    amount_ton: Mapped[float] = mapped_column(Float, nullable=False)
    memo: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    premium_days: Mapped[int] = mapped_column(Integer, default=30)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="payments")
