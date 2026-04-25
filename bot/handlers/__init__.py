from aiogram import Dispatcher
from bot.handlers.start import router as start_router
from bot.handlers.wallet import router as wallet_router
from bot.handlers.ai_handler import router as ai_router
from bot.handlers.misc import router as misc_router


def register_all_handlers(dp: Dispatcher) -> None:
    dp.include_router(start_router)
    dp.include_router(wallet_router)
    dp.include_router(ai_router)
    dp.include_router(misc_router)
