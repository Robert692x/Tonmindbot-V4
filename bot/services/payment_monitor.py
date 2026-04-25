import asyncio
import logging
from datetime import datetime, timezone
from aiogram import Bot
from bot.database.db import get_session
from bot.database.crud import get_pending_payments, confirm_payment, activate_premium
from bot.services.ton_service import ton_service
from config import settings

log = logging.getLogger(__name__)


class PaymentMonitor:
    def __init__(self, bot: Bot):
        self.bot = bot
        self._running = False

    async def run(self):
        self._running = True
        log.info("Payment monitor started")
        while self._running:
            try:
                await self._check()
            except Exception as e:
                log.error("Monitor error: %s", e)
            await asyncio.sleep(30)

    async def _check(self):
        async with get_session() as session:
            pending = await get_pending_payments(session)
            if not pending:
                return
            try:
                raw_txs = await ton_service.get_transactions(settings.TON_WALLET, limit=30)
            except Exception:
                return
            parsed = [ton_service.parse_tx(t) for t in raw_txs]
            for payment in pending:
                for tx in parsed:
                    if (tx["comment"].upper() == payment.memo.upper() and
                            tx["amount"] >= payment.amount_ton * 0.99):
                        await confirm_payment(session, payment, tx["hash"])
                        await activate_premium(session, payment.telegram_id, payment.premium_days)
                        await self._notify(payment.telegram_id, payment, tx)
                        break

    async def _notify(self, tg_id, payment, tx):
        try:
            text = (
                "🎉 <b>Оплата подтверждена!</b>\n\n"
                f"⭐ <b>Premium активирован на {payment.premium_days} дней</b>\n"
                f"💰 Сумма: <code>{payment.amount_ton:.2f} TON</code>\n"
                f"🔑 Код: <code>{payment.memo}</code>\n\n"
                "Наслаждайся безлимитным AI и всеми функциями! 🚀"
            )
            await self.bot.send_message(tg_id, text)
        except Exception as e:
            log.warning("Notify failed %d: %s", tg_id, e)
