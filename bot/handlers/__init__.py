from aiogram import Dispatcher

from bot.handlers import (
    admin_wallets, ai, alerts, analytics, chart, dex, errors,
    launchpad, leaderboard, portfolio, premium, price, profile,
    settings, start, trade, wallet, wallet_manager, watchlist, whales,
)


def include_routers(dispatcher: Dispatcher) -> None:
    dispatcher.include_router(errors.router)
    dispatcher.include_router(start.router)
    dispatcher.include_router(settings.router)
    dispatcher.include_router(wallet.router)
    dispatcher.include_router(wallet_manager.router)
    dispatcher.include_router(admin_wallets.router)
    dispatcher.include_router(portfolio.router)
    dispatcher.include_router(leaderboard.router)
    dispatcher.include_router(analytics.router)
    dispatcher.include_router(price.router)
    dispatcher.include_router(whales.router)
    dispatcher.include_router(chart.router)
    dispatcher.include_router(dex.router)
    dispatcher.include_router(launchpad.router)
    dispatcher.include_router(alerts.router)
    dispatcher.include_router(ai.router)
    dispatcher.include_router(premium.router)
    dispatcher.include_router(profile.router)
    dispatcher.include_router(trade.router)
    dispatcher.include_router(watchlist.router)
