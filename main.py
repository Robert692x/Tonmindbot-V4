"""
TON Mind Bot — Main Entry Point
"""
import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage

from config import settings
from bot.database.db import init_db
from bot.handlers import register_all_handlers
from bot.middleware.auth import AuthMiddleware
from bot.middleware.throttle import ThrottleMiddleware
from bot.services.payment_monitor import PaymentMonitor
from bot.utils.logger import setup_logging


async def main() -> None:
    setup_logging()
    log = logging.getLogger(__name__)
    log.info("Starting TON Mind Bot v2.0...")

    # Init DB tables
    await init_db()
    log.info("Database ready")

    # Bot + Redis FSM storage
    storage = RedisStorage.from_url(settings.REDIS_URL)
    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=storage)

    # Middleware
    dp.update.middleware(AuthMiddleware())
    dp.message.middleware(ThrottleMiddleware(rate=1.0))

    # Handlers
    register_all_handlers(dp)

    # Payment monitor background task
    monitor = PaymentMonitor(bot)
    asyncio.create_task(monitor.run())

    log.info("Bot polling started")
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()
        log.info("Bot stopped")


if __name__ == "__main__":
    asyncio.run(main())
