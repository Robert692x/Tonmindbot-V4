from __future__ import annotations

import logging
from typing import Any

import aiohttp

from bot.services.cache import CacheService
from bot.services.dev_wallet import DevWalletAnalyzer
from bot.services.token_metrics import extract_token_metrics
from bot.utils.links import address_link
from config import Settings

log = logging.getLogger(__name__)

_TOKEN_API = "https://api.dexscreener.com/latest/dex/tokens/{address}"
_CACHE_TTL = 15  # seconds


# ── Pure scoring function ─────────────────────────────────────────────────────

def calculate_risk(
    token_data: dict[str, Any],
    dev_data: dict[str, Any],
) -> dict[str, Any]:
    """
    Calculate a 0–100 risk score from token market data and dev wallet analysis.
    Returns {"score": int, "level": str, "factors": list[str]}.
    """
    score = 50
    factors: list[str] = []

    # ── 6.1  Liquidity ────────────────────────────────────────────────────────
    liquidity = float(token_data.get("liquidity") or 0)
    if liquidity > 5_000:
        score += 15
        factors.append("High liquidity")
    elif liquidity >= 1_000:
        score += 5
        factors.append("Moderate liquidity")
    elif liquidity < 500:
        score -= 20
        factors.append("Very low liquidity")

    # ── 6.2  Volume ───────────────────────────────────────────────────────────
    volume = float(token_data.get("volume") or 0)
    if volume > 5_000:
        score += 15
        factors.append("Strong volume")
    elif volume >= 1_000:
        score += 5
        factors.append("Moderate volume")
    elif volume < 500:
        score -= 15
        factors.append("Low volume")

    # ── 6.3  Buy / sell ratio ─────────────────────────────────────────────────
    buys = int(token_data.get("buys") or 0)
    sells = int(token_data.get("sells") or 0)
    if buys > sells:
        score += 10
        factors.append("Buys > sells")
    elif sells > buys and sells > 0:
        score -= 10
        factors.append("Sells > buys")

    # ── 6.4  Price trend ──────────────────────────────────────────────────────
    price_change = float(token_data.get("price_change_h24") or 0)
    if price_change > 20:
        score += 10
        factors.append("Strong price growth")
    elif price_change < -10:
        score -= 10
        factors.append("Price falling")

    # ── 6.5  Dev balance ──────────────────────────────────────────────────────
    balance = float(dev_data.get("balance") or 0)
    if balance > 10:
        score += 10
        factors.append("Healthy dev balance")
    elif balance < 1:
        score -= 20
        factors.append("Low dev balance")

    # ── 6.6  Dev activity ─────────────────────────────────────────────────────
    tx_24h = int(dev_data.get("tx_count_24h") or 0)
    activity = str(dev_data.get("activity") or "UNKNOWN")
    if tx_24h > 5:
        score += 5
        factors.append("Dev wallet active")
    elif tx_24h == 0 and activity != "UNKNOWN":
        score -= 5
        factors.append("Dev wallet inactive")

    # ── 6.7  Dangerous actions ────────────────────────────────────────────────
    risk_flags: list[str] = list(dev_data.get("risk_flags") or [])
    if "Mass outgoing transfers" in risk_flags:
        score -= 20
        factors.append("Mass outgoing tx")
    if "Transfers to many addresses" in risk_flags:
        score -= 10
        factors.append("Distributed transfers")
    if "Wallet drained" in risk_flags:
        score -= 15
        factors.append("Dev wallet drained")

    # ── 6.8  Address cluster ──────────────────────────────────────────────────
    if "High address cluster" in risk_flags:
        score -= 10
        factors.append("Address cluster risk")

    # ── Clamp & classify ──────────────────────────────────────────────────────
    score = max(0, min(100, score))

    if score >= 80:
        level = "LOW RISK"
    elif score >= 50:
        level = "MEDIUM RISK"
    else:
        level = "HIGH RISK"

    return {"score": score, "level": level, "factors": factors}


# ── Risk service ──────────────────────────────────────────────────────────────

class RiskService:
    """Full token risk analysis: DEX market data + dev wallet + score."""

    def __init__(
        self,
        dev_analyzer: DevWalletAnalyzer,
        cache: CacheService,
        settings: Settings,
    ) -> None:
        self._dev = dev_analyzer
        self._cache = cache
        self._settings = settings

    # ── DexScreener fetching ──────────────────────────────────────────────────

    async def _fetch_by_token_address(self, token_address: str) -> dict[str, Any] | None:
        """Fetch best TON pair for a token address from DexScreener."""
        url = _TOKEN_API.format(address=token_address)
        try:
            timeout = aiohttp.ClientTimeout(total=5)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        return None
                    data = await resp.json(content_type=None)

            pairs: list[dict] = data.get("pairs") or []
            ton_pairs = [p for p in pairs if p.get("chainId") == "ton"]
            if not ton_pairs:
                return None
            ton_pairs.sort(
                key=lambda p: float((p.get("volume") or {}).get("h24") or 0),
                reverse=True,
            )
            return self._parse_pair(ton_pairs[0])

        except Exception as exc:
            log.warning("DexScreener token fetch failed for %s: %s", token_address, exc)
            return None

    @staticmethod
    def _parse_pair(pair: dict[str, Any]) -> dict[str, Any]:
        base = pair.get("baseToken") or {}
        txns = (pair.get("txns") or {}).get("h24") or {}
        return {
            "name": str(base.get("name") or ""),
            "symbol": str(base.get("symbol") or "?"),
            "address": str(base.get("address") or ""),
            "pair": str(pair.get("pairAddress") or ""),
            "price": float(pair.get("priceUsd") or 0),
            "price_change_h24": float((pair.get("priceChange") or {}).get("h24") or 0),
            "mcap": float(pair.get("fdv") or 0),
            "liquidity": float((pair.get("liquidity") or {}).get("usd") or 0),
            "volume": float((pair.get("volume") or {}).get("h24") or 0),
            "buys": int(txns.get("buys") or 0),
            "sells": int(txns.get("sells") or 0),
        }

    # ── Full analysis pipeline ────────────────────────────────────────────────

    async def analyze_token(
        self,
        token_address: str | None = None,
        token_data: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        """
        Run the full pipeline. Provide either a pre-fetched token_data dict
        (from the top-tokens cache) or a token_address to look up on DexScreener.

        Returns (token_metrics, dev_data, risk_result).
        """
        ident = token_address or (token_data or {}).get("address", "")
        cache_key = f"risk:token:{ident}"
        cached = await self._cache.get_json(cache_key)
        if cached:
            return cached["token"], cached["dev"], cached["risk"]

        # Resolve market data
        if token_data is None:
            if not token_address:
                raise ValueError("token_address or token_data required")
            token_data = await self._fetch_by_token_address(token_address)

        _empty_dev: dict[str, Any] = {
            "address": None,
            "balance": 0.0,
            "tx_count": 0,
            "tx_count_24h": 0,
            "total_outgoing": 0.0,
            "total_incoming": 0.0,
            "unique_addresses": 0,
            "last_tx_time": None,
            "activity": "UNKNOWN",
            "risk_flags": [],
        }

        if not token_data:
            risk = calculate_risk({}, _empty_dev)
            return {}, _empty_dev, risk

        token_metrics = extract_token_metrics(token_data)

        # Resolve and analyze dev wallet
        dev_address = await self._dev.get_dev_address(token_metrics["address"])
        if dev_address:
            dev_data = await self._dev.analyze_dev_wallet(dev_address)
        else:
            dev_data = {**_empty_dev, "address": None}

        risk = calculate_risk(token_metrics, dev_data)

        await self._cache.set_json(
            cache_key,
            {"token": token_metrics, "dev": dev_data, "risk": risk},
            _CACHE_TTL,
        )
        return token_metrics, dev_data, risk

    # ── Formatting ────────────────────────────────────────────────────────────

    def format_analysis(
        self,
        token: dict[str, Any],
        dev_data: dict[str, Any],
        risk: dict[str, Any],
    ) -> str:
        """Render the full risk analysis as HTML for Telegram (parse_mode=HTML)."""
        symbol = token.get("symbol") or "?"
        price = _fmt_price(float(token.get("price") or 0))
        mcap = _fmt_usd(float(token.get("mcap") or 0))
        liquidity = _fmt_usd(float(token.get("liquidity") or 0))
        volume = _fmt_usd(float(token.get("volume") or 0))
        buys = int(token.get("buys") or 0)
        sells = int(token.get("sells") or 0)

        dev_addr = dev_data.get("address")
        balance = float(dev_data.get("balance") or 0)
        activity = str(dev_data.get("activity") or "UNKNOWN")

        score = int(risk.get("score") or 0)
        level = str(risk.get("level") or "UNKNOWN")
        factors: list[str] = list(risk.get("factors") or [])

        if score >= 80:
            risk_emoji = "🟢"
        elif score >= 50:
            risk_emoji = "🟡"
        else:
            risk_emoji = "🔴"

        sep = "─" * 22

        lines: list[str] = [
            "<b>TOKEN ANALYSIS</b>",
            "",
            f"Token: <b>{symbol}</b>",
            "",
            f"Price: {price}",
            f"Market Cap: {mcap}",
            f"Liquidity: {liquidity}",
            f"Volume: {volume}",
            f"Buys/Sells: {buys}/{sells}",
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
            f"Balance: {balance:.2f} TON",
            f"Activity: <b>{activity}</b>",
        ]

        flags = list(dev_data.get("risk_flags") or [])
        if flags:
            lines.append(f"Flags: {', '.join(flags)}")

        lines += [
            "",
            sep,
            "<b>RISK:</b>",
            "",
            f"Score: <b>{score} / 100</b>",
            f"Level: {risk_emoji} <b>{level}</b>",
        ]

        if factors:
            lines += ["", "Factors:"]
            for factor in factors:
                lines.append(f"• {factor}")

        return "\n".join(lines)

    def format_alert(
        self,
        token: dict[str, Any],
        risk: dict[str, Any],
        reason: str | None = None,
    ) -> str:
        """Render a RISK ALERT message for background notifications."""
        symbol = token.get("symbol") or "?"
        score = int(risk.get("score") or 0)
        level = str(risk.get("level") or "UNKNOWN")
        factors: list[str] = list(risk.get("factors") or [])
        alert_reason = reason or (factors[0] if factors else "Risk threshold exceeded")

        return (
            "⚠️ <b>RISK ALERT</b>\n\n"
            f"Token: <b>{symbol}</b>\n\n"
            f"Score: {score}\n"
            f"Level: <b>{level}</b>\n\n"
            f"Reason:\n{alert_reason}"
        )


# ── Shared formatters (mirrors dex_screener helpers to avoid circular imports) ─

def _fmt_price(value: float) -> str:
    if value == 0:
        return "$0"
    if value >= 1:
        return f"${value:,.2f}"
    if value >= 0.001:
        return f"${value:.4f}"
    return f"${value:.8f}"


def _fmt_usd(value: float) -> str:
    if value >= 1_000_000_000:
        return f"${value / 1_000_000_000:.2f}B"
    if value >= 1_000_000:
        return f"${value / 1_000_000:.2f}M"
    if value >= 1_000:
        return f"${value / 1_000:.1f}K"
    return f"${value:,.0f}"
