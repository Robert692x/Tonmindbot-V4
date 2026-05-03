from __future__ import annotations

import asyncio
import logging
from contextlib import suppress

from aiogram import Bot

from bot.database.repositories import SubscriptionRepository, UserRepository
from bot.services.alerts import format_alert, process_alerts
from bot.services.container import ServiceContainer
from bot.services.dex_alerts import process_dex_alerts
from bot.services.dex_screener import get_top_ton_tokens
from bot.utils.formatters import format_whale_alert

log = logging.getLogger(__name__)

_WALLET_MONITOR_INTERVAL = 30       # seconds
_DEX_MONITOR_INTERVAL = 15          # seconds
_RISK_MONITOR_INTERVAL = 60         # seconds
_RISK_ALERT_THRESHOLD = 40          # score below this triggers an alert
_RISK_DROP_THRESHOLD = 15           # score drop this large in one cycle triggers an alert
_LAUNCHPAD_MONITOR_INTERVAL = 20    # seconds — new listings check cadence
_LAUNCHPAD_STRONG_INTERVAL = 30     # seconds — strong-token alert cadence
_LAUNCHPAD_SIGNAL_INTERVAL = 30     # seconds — early-signal alert cadence

# token_address -> last known risk score (resets on restart)
_risk_scores: dict[str, int] = {}


class BackgroundWorkers:
    def __init__(self, bot: Bot, services: ServiceContainer) -> None:
        self.bot = bot
        self.services = services
        self._tasks: list[asyncio.Task] = []
        # In-memory dedup across cycles — prevents re-alerting when tx
        # stays in the top-N for multiple polling windows.
        self._seen_tx_hashes: set[str] = set()

    # Track which strong tokens already alerted to avoid spam
    _seen_strong: set[str] = set()

    async def start(self) -> None:
        self._tasks = [
            asyncio.create_task(self._payment_loop(),             name="payment-loop"),
            asyncio.create_task(self._whale_alert_loop(),         name="whale-alert-loop"),
            asyncio.create_task(self._monitor_wallets_loop(),     name="wallet-monitor-loop"),
            asyncio.create_task(self._dex_monitor_loop(),         name="dex-monitor-loop"),
            asyncio.create_task(self._risk_monitor_loop(),        name="risk-monitor-loop"),
            asyncio.create_task(self._launchpad_monitor_loop(),   name="launchpad-monitor-loop"),
            asyncio.create_task(self._launchpad_strong_loop(),    name="launchpad-strong-loop"),
            asyncio.create_task(self._launchpad_signal_loop(),    name="launchpad-signal-loop"),
        ]

    async def close(self) -> None:
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            with suppress(asyncio.CancelledError):
                await task
        self._tasks.clear()

    async def _payment_loop(self) -> None:
        while True:
            try:
                async with self.services.session_factory() as session:
                    subscriptions = await SubscriptionRepository(session).list_pending()
                    for subscription in subscriptions:
                        await self.services.premium.verify_subscription_payment(session, subscription)
                    await session.commit()
            except Exception as exc:
                log.exception("Payment worker failed: %s", exc)
            await asyncio.sleep(self.services.settings.PAYMENT_POLL_INTERVAL_SECONDS)

    async def _whale_alert_loop(self) -> None:
        while True:
            try:
                async with self.services.session_factory() as session:
                    users = await UserRepository(session).list_whale_alert_subscribers()
                    if users:
                        whales = await self.services.tonapi.get_recent_whales()
                        for whale in whales[:8]:
                            seen = await self.services.cache.remember_once(
                                f"whale-alert:{whale.tx_hash}",
                                self.services.settings.BACKGROUND_SEEN_TTL_SECONDS,
                            )
                            if not seen:
                                continue
                            for user in users:
                                with suppress(Exception):
                                    text = format_whale_alert(user, whale)
                                    await self.bot.send_message(user.telegram_id, text)
            except Exception as exc:
                log.exception("Whale alert worker failed: %s", exc)
            await asyncio.sleep(self.services.settings.WHALE_ALERT_POLL_INTERVAL_SECONDS)

    # ── Wallet monitoring ─────────────────────────────────────────────────────

    async def _monitor_wallets_loop(self) -> None:
        while True:
            try:
                await self._check_all_wallets()
            except Exception as exc:
                log.exception("Wallet monitor loop failed: %s", exc)
            await asyncio.sleep(_WALLET_MONITOR_INTERVAL)

    async def _check_all_wallets(self) -> None:
        async with self.services.session_factory() as session:
            pairs = await self.services.watchlist.get_all_active_with_telegram_id(session)
            if not pairs:
                return

            for wallet, telegram_id in pairs:
                with suppress(Exception):
                    await self._check_wallet(session, wallet, telegram_id)

            await session.commit()

    # ── DEX Screener monitoring ───────────────────────────────────────────────

    async def _dex_monitor_loop(self) -> None:
        while True:
            try:
                await self._check_dex_alerts()
            except Exception as exc:
                log.exception("DEX monitor loop failed: %s", exc)
            await asyncio.sleep(_DEX_MONITOR_INTERVAL)

    async def _check_dex_alerts(self) -> None:
        tokens = await get_top_ton_tokens()
        if not tokens:
            return

        alerts = await process_dex_alerts(tokens)
        if not alerts:
            return

        async with self.services.session_factory() as session:
            users = await UserRepository(session).list_dex_alert_subscribers()

        if not users:
            return

        for alert_text in alerts:
            for user in users:
                with suppress(Exception):
                    await self.bot.send_message(
                        user.telegram_id,
                        alert_text,
                        parse_mode="HTML",
                        disable_web_page_preview=True,
                    )

    # ── Risk monitoring ────────────────────────────────────────────────────────

    async def _risk_monitor_loop(self) -> None:
        while True:
            try:
                await self._check_risk_alerts()
            except Exception as exc:
                log.exception("Risk monitor loop failed: %s", exc)
            await asyncio.sleep(_RISK_MONITOR_INTERVAL)

    async def _check_risk_alerts(self) -> None:
        tokens = await get_top_ton_tokens()
        if not tokens:
            return

        alert_texts: list[str] = []
        for token in tokens:
            address = token.get("address", "")
            if not address:
                continue

            with suppress(Exception):
                _, dev_data, risk = await self.services.risk.analyze_token(token_data=token)
                score = int(risk.get("score") or 0)
                prev_score = _risk_scores.get(address)
                _risk_scores[address] = score

                should_alert = False
                reason: str | None = None

                if score < _RISK_ALERT_THRESHOLD:
                    should_alert = True
                    reason = f"Score dropped to {score} (HIGH RISK)"
                elif prev_score is not None and (prev_score - score) >= _RISK_DROP_THRESHOLD:
                    should_alert = True
                    reason = f"Score fell {prev_score - score} points (from {prev_score} to {score})"

                flags = list((dev_data or {}).get("risk_flags") or [])
                if "Mass outgoing transfers" in flags or "Wallet drained" in flags:
                    should_alert = True
                    reason = "Dev wallet draining funds"

                if should_alert:
                    alert_texts.append(self.services.risk.format_alert(token, risk, reason))

        if not alert_texts:
            return

        async with self.services.session_factory() as session:
            users = await UserRepository(session).list_dex_alert_subscribers()

        if not users:
            return

        for alert_text in alert_texts:
            for user in users:
                with suppress(Exception):
                    await self.bot.send_message(
                        user.telegram_id,
                        alert_text,
                        parse_mode="HTML",
                        disable_web_page_preview=True,
                    )

    # ── Launchpad new-listings monitoring ────────────────────────────────────

    async def _launchpad_monitor_loop(self) -> None:
        while True:
            try:
                await self._check_launchpad_listings()
                await self.services.launchpad.cleanup_cache()
            except Exception as exc:
                log.exception("Launchpad monitor loop failed: %s", exc)
            await asyncio.sleep(_LAUNCHPAD_MONITOR_INTERVAL)

    async def _check_launchpad_listings(self) -> None:
        """Fetch new (unseen) listings and notify DEX alert subscribers."""
        new_listings = await self.services.launchpad.pop_new_listings()
        if not new_listings:
            return

        async with self.services.session_factory() as session:
            users = await UserRepository(session).list_dex_alert_subscribers()

        if not users:
            return

        for pair in new_listings:
            alert_text = self.services.launchpad.format_alert(pair)
            for user in users:
                with suppress(Exception):
                    await self.bot.send_message(
                        user.telegram_id,
                        alert_text,
                        parse_mode="HTML",
                        disable_web_page_preview=True,
                    )

    # ── Strong token alerts ───────────────────────────────────────────────────

    async def _launchpad_strong_loop(self) -> None:
        while True:
            try:
                await self._check_launchpad_strong()
            except Exception as exc:
                log.exception("Launchpad strong-token loop failed: %s", exc)
            await asyncio.sleep(_LAUNCHPAD_STRONG_INTERVAL)

    async def _check_launchpad_strong(self) -> None:
        tokens = await self.services.launchpad.get_new_tokens(max_items=50)
        strong = self.services.launchpad.get_strong_tokens(tokens)
        new_strong = [t for t in strong if t.get("address") not in self._seen_strong]
        if not new_strong:
            return

        async with self.services.session_factory() as session:
            users = await UserRepository(session).list_dex_alert_subscribers()
        if not users:
            return

        for token in new_strong:
            addr = token.get("address") or ""
            if addr:
                self._seen_strong.add(addr)
            alert_text = self.services.launchpad.format_alert_strong(token)
            for user in users:
                with suppress(Exception):
                    await self.bot.send_message(
                        user.telegram_id,
                        alert_text,
                        parse_mode="HTML",
                        disable_web_page_preview=True,
                    )

    # ── Early signal alerts ───────────────────────────────────────────────────

    async def _launchpad_signal_loop(self) -> None:
        while True:
            try:
                await self._check_launchpad_signals()
            except Exception as exc:
                log.exception("Launchpad signal loop failed: %s", exc)
            await asyncio.sleep(_LAUNCHPAD_SIGNAL_INTERVAL)

    async def _check_launchpad_signals(self) -> None:
        tokens = await self.services.launchpad.get_new_tokens(max_items=50)
        signals = self.services.launchpad.get_early_signals(tokens)
        if not signals:
            return

        async with self.services.session_factory() as session:
            users = await UserRepository(session).list_dex_alert_subscribers()
        if not users:
            return

        for token, level in signals:
            alert_text = self.services.launchpad.format_alert_signal(token, level)
            for user in users:
                with suppress(Exception):
                    await self.bot.send_message(
                        user.telegram_id,
                        alert_text,
                        parse_mode="HTML",
                        disable_web_page_preview=True,
                    )

    async def _check_wallet(self, session, wallet, telegram_id: int) -> None:
        # ── Step 1: fetch raw transactions from the API ───────────────────────
        raw_txs = await self.services.tonapi.get_raw_transactions(wallet.address, limit=15)
        if not raw_txs:
            return

        # ── Step 2: bootstrap detection ───────────────────────────────────────
        last_known = await self.services.watchlist.get_last_tx_hash(session, wallet.id)
        bootstrap = last_known is None  # first run — record state, no alerts

        # ── Step 3: normalize — 1 tx = 1 NormalizedTx ────────────────────────
        # process_alerts groups by hash, filters dust/internal, dedupes via
        # seen_hashes (in-memory, shared across polling cycles).
        new_txs = process_alerts(
            raw_txs,
            wallet.address,
            seen_hashes=self._seen_tx_hashes,
        )

        for tx in new_txs:
            # Persist to DB — second dedup layer (survives restarts).
            event = await self.services.watchlist.record_event(
                session,
                wallet_id=wallet.id,
                tx_hash=tx.hash,
                event_type=tx.direction,
                amount=tx.amount_ton,
                token="TON",
                counterparty=tx.from_addr if tx.direction == "IN" else tx.to_addr,
                timestamp=tx.time,
            )
            if event is None or bootstrap:
                continue  # already in DB or first-run bootstrap

            # ── Step 4: send exactly one alert per transaction ────────────────
            with suppress(Exception):
                wallet_name = wallet.label or wallet.address
                text = format_alert(wallet_name, wallet.address, tx)
                await self.bot.send_message(
                    telegram_id,
                    text,
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                )
