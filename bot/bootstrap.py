from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import sys
from pathlib import Path

import uvicorn
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramConflictError
from aiogram import Dispatcher
from aiogram.fsm.storage.base import BaseStorage
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.redis import RedisStorage

from bot.database.db import create_engine, create_session_factory, init_database
from bot.handlers import include_routers
from bot.middlewares.db import DatabaseSessionMiddleware
from bot.middlewares.logging import LoggingMiddleware
from bot.middlewares.rate_limit import RateLimitMiddleware
from bot.middlewares.subscription import SubscriptionMiddleware
from bot.middlewares.user_context import UserContextMiddleware
from bot.services.algo import AlgoService
from bot.services.ai import AIService
from bot.services.ai_tools import ToolExecutor
from bot.services.background import BackgroundWorkers
from bot.services.cache import build_cache_service
from bot.services.container import ServiceContainer
from bot.services.dev_wallet import DevWalletAnalyzer
from bot.services.launchpad.service import LaunchpadService
from bot.services.i18n import I18nService, configure_i18n
from bot.services.market import MarketService
from bot.services.premium import PremiumService
from bot.services.risk import RiskService
from bot.services.tonapi import TonApiService
from bot.trading.service import TradingService
from bot.services.wallet_manager import WalletManagerService
from bot.services.wallet_service import WalletService
from bot.services.watchlist import WatchlistService
from config import Settings, get_settings

log = logging.getLogger(__name__)


def build_storage(settings: Settings) -> BaseStorage:
    if settings.REDIS_URL:
        return RedisStorage.from_url(settings.REDIS_URL)
    return MemoryStorage()


async def build_service_container(settings: Settings) -> ServiceContainer:
    engine = create_engine(settings.DATABASE_URL)
    await init_database(engine)
    session_factory = create_session_factory(engine)
    cache = await build_cache_service(settings.REDIS_URL)
    i18n = I18nService()
    configure_i18n(i18n)
    tonapi = TonApiService(settings=settings, cache=cache)
    market = MarketService(settings=settings, cache=cache)
    algo = AlgoService(settings=settings, cache=cache, tonapi=tonapi)
    ai = AIService(settings=settings)

    # ToolExecutor calls the local FastAPI backend — no direct service coupling
    tool_executor = ToolExecutor(backend_url=settings.BACKEND_URL)
    ai.set_tool_executor(tool_executor)
    
    premium = PremiumService(settings=settings, tonapi=tonapi)
    trading = TradingService()
    watchlist = WatchlistService()
    wallet = WalletService(tonapi=tonapi)
    wallet_manager = WalletManagerService()
    dev_analyzer = DevWalletAnalyzer(tonapi=tonapi, cache=cache, settings=settings)
    risk = RiskService(dev_analyzer=dev_analyzer, cache=cache, settings=settings)
    launchpad = LaunchpadService(risk=risk)
    return ServiceContainer(
        settings=settings,
        engine=engine,
        session_factory=session_factory,
        cache=cache,
        i18n=i18n,
        tonapi=tonapi,
        market=market,
        algo=algo,
        ai=ai,
        premium=premium,
        trading=trading,
        watchlist=watchlist,
        wallet=wallet,
        wallet_manager=wallet_manager,
        risk=risk,
        launchpad=launchpad,
    )


def build_dispatcher(
    settings: Settings,
    services: ServiceContainer,
    storage: BaseStorage,
) -> Dispatcher:
    dispatcher = Dispatcher(storage=storage)
    dispatcher.update.outer_middleware(LoggingMiddleware())
    dispatcher.update.outer_middleware(DatabaseSessionMiddleware(services.session_factory))
    dispatcher.update.outer_middleware(UserContextMiddleware())
    dispatcher.update.outer_middleware(SubscriptionMiddleware())
    dispatcher.update.outer_middleware(RateLimitMiddleware(services.cache, settings))
    include_routers(dispatcher)
    return dispatcher


# ── Public synchronous entry point ────────────────────────────────────────────

def start_bot() -> None:
    """
    Synchronous entry point called by main.py after the single-instance
    guard is acquired.

    Runs the full async lifecycle:
      1. Start FastAPI data backend.
      2. Validate OpenAI key.
      3. Build services, dispatcher, workers.
      4. Run aiogram long-poll.
      5. Graceful shutdown.
    """
    settings = get_settings()
    log.info(
        "TON Mind Bot starting | PID=%d | Python=%s | CWD=%s",
        os.getpid(), sys.version.split()[0], Path.cwd(),
    )
    asyncio.run(_run_bot(settings))


# ── Private async helpers ──────────────────────────────────────────────────────

async def _run_backend(settings: Settings) -> None:
    config = uvicorn.Config(
        "server:app",
        host="127.0.0.1",
        port=settings.BACKEND_PORT,
        log_level="warning",
        access_log=False,
    )
    server = uvicorn.Server(config)
    log.info("FastAPI backend starting on http://127.0.0.1:%d", settings.BACKEND_PORT)
    await server.serve()


async def _wait_for_backend(settings: Settings, timeout: float = 8.0) -> bool:
    import httpx
    url = f"{settings.BACKEND_URL}/health"
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        try:
            async with httpx.AsyncClient(timeout=1.0) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    log.info("Backend ready at %s", settings.BACKEND_URL)
                    return True
        except Exception:
            pass
        await asyncio.sleep(0.4)
    log.warning("Backend did not respond within %.0f s — AI tools may fail.", timeout)
    return False


async def _validate_openai_key(settings: Settings) -> None:
    from openai import AsyncOpenAI
    from openai import AuthenticationError as OpenAIAuthError

    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY, timeout=10.0)
    try:
        await client.models.list()
        log.info("OpenAI API key validated successfully.")
    except OpenAIAuthError:
        log.critical(
            "OpenAI API key is INVALID (401). "
            "Update OPENAI_API_KEY in .env — https://platform.openai.com/api-keys"
        )
    except Exception:
        log.warning("Could not validate OpenAI key at startup (network issue). Proceeding.")
    finally:
        with contextlib.suppress(Exception):
            await client.close()


async def _evict_conflict(bot: Bot) -> None:
    try:
        await bot.get_updates(timeout=0, limit=1)
    except TelegramConflictError:
        log.debug("Telegram conflict — previous session still closing, waiting 2 s.")
        await asyncio.sleep(2.0)
    except Exception as exc:
        log.debug("Conflict eviction skipped: %s", exc)
    else:
        await asyncio.sleep(0.5)


async def _run_bot(settings: Settings) -> None:
    backend_task = asyncio.create_task(_run_backend(settings))
    await _wait_for_backend(settings)

    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    await _validate_openai_key(settings)

    services = await build_service_container(settings)
    dispatcher = build_dispatcher(settings, services, build_storage(settings))
    workers = BackgroundWorkers(bot=bot, services=services)

    await bot.delete_webhook(drop_pending_updates=True)
    await _evict_conflict(bot)

    log.info("Bot is online and polling.")
    await workers.start()
    try:
        await dispatcher.start_polling(bot, services=services)
    finally:
        log.info("Shutting down — cleaning up resources.")
        await workers.close()
        await services.close()
        await dispatcher.storage.close()
        await bot.session.close()
        backend_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await backend_task
        log.info("Shutdown complete.")
