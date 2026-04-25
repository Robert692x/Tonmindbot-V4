from contextlib import asynccontextmanager
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from bot.database.models import Base
from config import settings

_engine = None
_factory = None


def get_engine():
    global _engine
    if not _engine:
        _engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True, echo=False)
    return _engine


def get_factory():
    global _factory
    if not _factory:
        _factory = async_sessionmaker(bind=get_engine(), class_=AsyncSession,
                                       expire_on_commit=False, autoflush=False)
    return _factory


async def init_db():
    async with get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with get_factory()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
