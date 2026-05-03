from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from bot.services.algo import AlgoService
from bot.services.ai import AIService
from bot.services.cache import CacheService
from bot.services.i18n import I18nService
from bot.services.market import MarketService
from bot.services.premium import PremiumService
from bot.services.launchpad.service import LaunchpadService
from bot.services.risk import RiskService
from bot.services.tonapi import TonApiService
from bot.trading.service import TradingService
from bot.services.wallet_manager import WalletManagerService
from bot.services.wallet_service import WalletService
from bot.services.watchlist import WatchlistService
from config import Settings


@dataclass(slots=True)
class ServiceContainer:
    settings: Settings
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    cache: CacheService
    i18n: I18nService
    tonapi: TonApiService
    market: MarketService
    algo: AlgoService
    ai: AIService
    premium: PremiumService
    trading: TradingService
    watchlist: WatchlistService
    wallet: WalletService
    wallet_manager: WalletManagerService
    risk: RiskService
    launchpad: LaunchpadService

    async def close(self) -> None:
        await self.ai.close()
        await self.algo.close()
        await self.market.close()
        await self.tonapi.close()
        await self.cache.close()
        await self.engine.dispose()
