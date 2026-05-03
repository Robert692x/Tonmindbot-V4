from __future__ import annotations

import logging
from html import escape
from typing import TYPE_CHECKING, Any

from bot.services.launchpad.analyzer import calculate_rug_risk, risk_emoji
from bot.services.launchpad.cache import LaunchpadCache
from bot.services.launchpad.fetcher import fetch_new_listings
from bot.services.launchpad.listing import get_new_tokens, normalize_pair
from bot.services.launchpad.notifier import (
    format_listing,
    format_listing_alert,
    format_listings_summary,
    format_token_analysis,
)
from bot.services.launchpad.signal_detector import detect_early_signals, detect_strong_tokens
from bot.services.launchpad.risk_scoring import calculate_risk_score
from bot.services.launchpad.signals import SIGNAL_HIGH, SIGNAL_MEDIUM, SignalsService
from bot.utils.links import address_link

if TYPE_CHECKING:
    from bot.services.risk import RiskService

log = logging.getLogger(__name__)

_MAX_WATCHLIST = 20

# ── Shared formatters ─────────────────────────────────────────────────────────

def _fmt_price(v: float) -> str:
    if v == 0:
        return "$0"
    if v >= 1:
        return f"${v:,.2f}"
    if v >= 0.001:
        return f"${v:.4f}"
    return f"${v:.8f}"


def _fmt_usd(v: float) -> str:
    if v >= 1_000_000_000:
        return f"${v / 1_000_000_000:.2f}B"
    if v >= 1_000_000:
        return f"${v / 1_000_000:.2f}M"
    if v >= 1_000:
        return f"${v / 1_000:.1f}K"
    return f"${v:,.0f}"


def _signal_emoji(level: str | None) -> str:
    return {"HIGH": "🔥", "MEDIUM": "📡", "LOW": "📶"}.get(level or "", "—")


def _make_conclusion(signal: str | None, risk: dict[str, Any]) -> str:
    score = int(risk.get("score") or 0)
    if score >= 70 and signal == SIGNAL_HIGH:
        return "Сильный сигнал роста при низком риске. Возможен ранний вход."
    if score >= 60 and signal in (SIGNAL_HIGH, SIGNAL_MEDIUM):
        return "Умеренный сигнал. Следите за объёмом и давлением покупок."
    if score < 40:
        return "Высокий риск. Возможен rug-pull. Не рекомендуется."
    if score < 50:
        return "Повышенный риск. Требуется осторожность."
    if signal:
        return f"Сигнал {signal}. Продолжайте мониторинг."
    return "Явных сигналов не обнаружено. Требуется наблюдение."


class LaunchpadService:
    """
    Main Launchpad Assistant orchestrator.

    Extension stubs at bottom: honeypot_check, whale_tracking, dev_wallet_analysis.
    """

    def __init__(self, risk: "RiskService") -> None:
        self._cache = LaunchpadCache()
        self._signals = SignalsService()
        self._risk = risk
        # In-memory token watchlist: user_id -> set of token addresses
        self._watchlist: dict[int, set[str]] = {}

    # ── New Listings ──────────────────────────────────────────────────────────

    async def get_new_tokens(self, *, max_items: int = 10) -> list[dict[str, Any]]:
        """All fresh listings (on-demand, does not mutate dedup cache)."""
        return await get_new_tokens(max_items)

    async def get_all_listings(self, *, max_items: int = 10) -> list[dict[str, Any]]:
        """Alias for backward compat with existing handler."""
        return await self.get_new_tokens(max_items=max_items)

    async def pop_new_listings(self) -> list[dict[str, Any]]:
        """Return unseen listings and mark them — for background alert worker."""
        pairs = await fetch_new_listings()
        fresh: list[dict[str, Any]] = []
        for pair in pairs:
            addr = pair.get("pairAddress", "")
            if not addr or await self._cache.is_seen(addr):
                continue
            await self._cache.mark_seen(addr)
            fresh.append(normalize_pair(pair))
        if fresh:
            log.info("Launchpad: %d new listing(s)", len(fresh))
        return fresh

    # ── Strong Tokens ─────────────────────────────────────────────────────────

    def get_strong_tokens(self, tokens: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return self._signals.filter_strong_tokens(tokens)

    # ── Early Signals ─────────────────────────────────────────────────────────

    def get_early_signals(
        self,
        tokens: list[dict[str, Any]],
    ) -> list[tuple[dict[str, Any], str]]:
        return self._signals.detect_early_signals(tokens)

    # ── Full Analysis ─────────────────────────────────────────────────────────

    async def build_token_analysis(
        self,
        token: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Orchestrate the complete analysis pipeline:
        token metrics → strong filter → early signal → dev wallet → risk score → conclusion.
        """
        is_strong = bool(self._signals.filter_strong_tokens([token]))
        signal_results = self._signals.detect_early_signals([token])
        signal_level: str | None = signal_results[0][1] if signal_results else None

        token_metrics, dev_data, risk = await self._risk.analyze_token(token_data=token)

        conclusion = _make_conclusion(signal_level, risk)
        return {
            "token": token_metrics,
            "is_strong": is_strong,
            "signal": signal_level,
            "dev": dev_data,
            "risk": risk,
            "conclusion": conclusion,
        }

    # ── Formatting ────────────────────────────────────────────────────────────

    @staticmethod
    def format_summary(listings: list[dict[str, Any]]) -> str:
        return format_listings_summary(listings)

    @staticmethod
    def format_single(pair: dict[str, Any]) -> str:
        return format_listing(pair)

    @staticmethod
    def format_alert(pair: dict[str, Any]) -> str:
        return format_listing_alert(pair)

    @staticmethod
    def format_unified_analysis(analysis: dict[str, Any]) -> str:
        """Format complete token analysis using unified analyzer output."""
        return format_token_analysis(analysis)

    def format_strong_tokens(self, tokens: list[dict[str, Any]]) -> str:
        if not tokens:
            return "<b>💪 Strong Tokens (TON)</b>\n\nФильтр не выявил качественных токенов."
        sep = "─" * 22
        lines = [f"💪 <b>Strong Tokens (TON)</b> — {len(tokens)} found\n", sep]
        for t in tokens[:10]:
            sym = escape(str(t.get("symbol") or "?")[:12])
            price = _fmt_price(float(t.get("price") or 0))
            liq = _fmt_usd(float(t.get("liquidity") or 0))
            vol = _fmt_usd(float(t.get("volume") or 0))
            buys = int(t.get("buys") or 0)
            sells = int(t.get("sells") or 0)
            addr = t.get("address") or ""
            link = f' <a href="https://tonscan.org/address/{addr}">📎</a>' if addr else ""
            lines.append(
                f"<b>{sym}</b>{link}  {price}\n"
                f"   Liq: {liq}  Vol: {vol}  B/S: {buys}/{sells}"
            )
            lines.append(sep)
        return "\n".join(lines)

    def format_signals(self, signals: list[tuple[dict[str, Any], str]]) -> str:
        if not signals:
            return "<b>📡 Early Signals (TON)</b>\n\nАктивных сигналов не обнаружено."
        sep = "─" * 22
        lines = [f"📡 <b>Early Signals (TON)</b> — {len(signals)} found\n", sep]
        for token, level in signals[:10]:
            sym = escape(str(token.get("symbol") or "?")[:12])
            price = _fmt_price(float(token.get("price") or 0))
            change = float(token.get("price_change_h24") or 0)
            vol = _fmt_usd(float(token.get("volume") or 0))
            sign = "+" if change >= 0 else ""
            emoji = _signal_emoji(level)
            addr = token.get("address") or ""
            link = f' <a href="https://tonscan.org/address/{addr}">📎</a>' if addr else ""
            lines.append(
                f"{emoji} <b>{level}</b>  <b>{sym}</b>{link}  {price}\n"
                f"   {sign}{change:.1f}%  Vol: {vol}"
            )
            lines.append(sep)
        return "\n".join(lines)

    def format_full_analysis(self, result: dict[str, Any]) -> str:
        """Render complete TOKEN ANALYSIS card (HTML)."""
        t = result.get("token") or {}
        dev = result.get("dev") or {}
        risk = result.get("risk") or {}
        signal: str | None = result.get("signal")
        conclusion: str = result.get("conclusion") or ""

        sym = escape(str(t.get("symbol") or "?"))
        name = escape(str(t.get("name") or ""))
        price = _fmt_price(float(t.get("price") or 0))
        mcap = _fmt_usd(float(t.get("mcap") or 0))
        liq = _fmt_usd(float(t.get("liquidity") or 0))
        vol = _fmt_usd(float(t.get("volume") or 0))
        buys = int(t.get("buys") or 0)
        sells = int(t.get("sells") or 0)

        dev_addr = dev.get("address")
        balance = float(dev.get("balance") or 0)
        activity = str(dev.get("activity") or "UNKNOWN")
        tx_24h = int(dev.get("tx_count_24h") or 0)
        flags: list[str] = list(dev.get("risk_flags") or [])

        score = int(risk.get("score") or 0)
        level = str(risk.get("level") or "UNKNOWN")
        factors: list[str] = list(risk.get("factors") or [])

        r_emoji = "🟢" if score >= 80 else ("🟡" if score >= 50 else "🔴")
        s_emoji = _signal_emoji(signal)
        sep = "─" * 22

        lines = [
            "🔍 <b>TOKEN ANALYSIS</b>",
            "",
            f"Token: <b>{sym}</b>",
            f"Name: {name}" if name and name != sym else "",
            "",
            f"💰 Price: {price}",
            f"📊 Market Cap: {mcap}",
            f"💧 Liquidity: {liq}",
            f"📈 Volume: {vol}",
            "",
            f"Buys/Sells: <b>{buys}/{sells}</b>",
            f"Signal: {s_emoji} <b>{signal or '—'}</b>",
            "",
            sep,
            "<b>DEV:</b>",
            "",
        ]

        if dev_addr:
            lines.append(f"Address: {address_link(dev_addr)}")
        else:
            lines.append("Address: <i>Unknown</i>")

        lines += [
            f"Balance: <b>{balance:.2f} TON</b>",
            f"Activity: <b>{activity}</b>",
            f"Tx 24h: {tx_24h}",
        ]
        if flags:
            lines.append(f"⚠️ Flags: {escape(', '.join(flags))}")

        lines += [
            "",
            sep,
            "<b>RISK:</b>",
            "",
            f"Score: <b>{score} / 100</b>",
            f"Level: {r_emoji} <b>{level}</b>",
        ]
        if factors:
            lines += ["", "Factors:"]
            for f in factors:
                lines.append(f"• {escape(f)}")

        lines += [
            "",
            sep,
            f"<b>Conclusion:</b>\n{escape(conclusion)}",
        ]

        return "\n".join(line for line in lines if line is not None)

    def format_alert_strong(self, token: dict[str, Any]) -> str:
        sym = escape(str(token.get("symbol") or "?"))
        price = _fmt_price(float(token.get("price") or 0))
        liq = _fmt_usd(float(token.get("liquidity") or 0))
        vol = _fmt_usd(float(token.get("volume") or 0))
        addr = token.get("address") or ""
        link = address_link(addr) if addr else "<i>Unknown</i>"
        return (
            "💪 <b>Strong Token Alert</b>\n\n"
            f"Token: <b>{sym}</b>\n"
            f"Price: {price}\n"
            f"Liquidity: {liq}\n"
            f"Volume: {vol}\n\n"
            f"Contract:\n{link}"
        )

    def format_alert_signal(self, token: dict[str, Any], level: str) -> str:
        sym = escape(str(token.get("symbol") or "?"))
        price = _fmt_price(float(token.get("price") or 0))
        change = float(token.get("price_change_h24") or 0)
        vol = _fmt_usd(float(token.get("volume") or 0))
        sign = "+" if change >= 0 else ""
        emoji = _signal_emoji(level)
        addr = token.get("address") or ""
        link = address_link(addr) if addr else "<i>Unknown</i>"
        return (
            f"📡 <b>Early Signal Alert</b>\n\n"
            f"Level: {emoji} <b>{level}</b>\n"
            f"Token: <b>{sym}</b>\n"
            f"Price: {price}  ({sign}{change:.1f}%)\n"
            f"Volume: {vol}\n\n"
            f"Contract:\n{link}"
        )

    # ── Token Watchlist ───────────────────────────────────────────────────────

    def watchlist_add(self, user_id: int, address: str) -> bool:
        """Add token address to user's watchlist. Returns False if limit reached."""
        addresses = self._watchlist.setdefault(user_id, set())
        if len(addresses) >= _MAX_WATCHLIST:
            return False
        addresses.add(address.strip())
        return True

    def watchlist_remove(self, user_id: int, address: str) -> bool:
        """Remove token from watchlist. Returns False if not found."""
        addresses = self._watchlist.get(user_id)
        if not addresses or address not in addresses:
            return False
        addresses.discard(address)
        return True

    def watchlist_list(self, user_id: int) -> list[str]:
        return list(self._watchlist.get(user_id) or [])

    def watchlist_clear(self, user_id: int) -> None:
        self._watchlist.pop(user_id, None)

    # ── Cache maintenance ─────────────────────────────────────────────────────

    async def cleanup_cache(self) -> None:
        removed = await self._cache.cleanup()
        sig_removed = self._signals.cleanup()
        if removed or sig_removed:
            log.debug(
                "Launchpad cleanup: %d dedup / %d signal baselines removed",
                removed,
                sig_removed,
            )

    @property
    def cache_size(self) -> int:
        return self._cache.size

    # ── Risk passthrough ──────────────────────────────────────────────────────

    @staticmethod
    def risk_for(pair: dict[str, Any]) -> dict[str, Any]:
        age_minutes = float(pair.get("_age_minutes") or 0)
        return calculate_rug_risk(pair, age_minutes)

    # ── Extension stubs ───────────────────────────────────────────────────────

    async def honeypot_check(self, token_address: str) -> dict[str, Any]:
        # TODO: call honeypot.is or similar TON honeypot-detection API
        return {"is_honeypot": False, "reason": None}

    async def whale_tracking(self, pair_address: str) -> list[dict[str, Any]]:
        # TODO: scan recent large buys/sells via TonAPI
        return []

    async def dev_wallet_analysis(self, token_address: str) -> dict[str, Any]:
        # TODO: delegates to self._risk's DevWalletAnalyzer directly
        return {}
