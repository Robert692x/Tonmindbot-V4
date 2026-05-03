from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from bot.database.models import Base


def create_engine(database_url: str) -> AsyncEngine:
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    return create_async_engine(
        database_url,
        pool_pre_ping=not database_url.startswith("sqlite"),
        connect_args=connect_args,
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False, autoflush=False)


async def init_database(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    await _migrate_database(engine)


async def _migrate_database(engine: AsyncEngine) -> None:
    """Add new columns to existing tables — safe to run repeatedly."""
    new_columns = [
        ("watched_wallets", "alert_threshold", "REAL"),
        ("watched_wallets", "alert_types",     "VARCHAR(256)"),
        ("watched_wallets", "flagged",          "BOOLEAN DEFAULT 0 NOT NULL"),
        ("watched_wallets", "moderator_note",   "VARCHAR(500)"),
        ("watched_wallets", "risk_override",    "VARCHAR(16)"),
        ("users",           "dex_alerts_enabled", "BOOLEAN DEFAULT 0 NOT NULL"),
    ]
    async with engine.begin() as conn:
        for table, col, col_type in new_columns:
            try:
                await conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}"))
            except Exception:
                pass  # column already exists — ignore
