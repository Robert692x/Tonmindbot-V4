from __future__ import annotations

import logging
from typing import Any

import aiohttp

from bot.utils.links import address_link

log = logging.getLogger(__name__)

_API_URL = "https://api.dexscreener.com/latest/dex/search?q=ton"
_MIN_LIQUIDITY = 1_000.0
_MIN_VOLUME = 1_000.0
_TOP_N = 10
_TIMEOUT = 5


async def get_top_ton_tokens() -> list[dict]:
    """Fetch top 10 TON tokens by 24h volume from DexScreener API."""
    try:
        timeout = aiohttp.ClientTimeout(total=_TIMEOUT)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(_API_URL) as response:
                if response.status != 200:
                    log.warning("DexScreener returned status %s", response.status)
                    return []
                data: dict[str, Any] = await response.json(content_type=None)
    except Exception as exc:
        log.warning("DexScreener request failed: %s", exc)
        return []

    pairs: list[dict] = data.get("pairs") or []
    tokens: list[dict] = []

    for pair in pairs:
        if pair.get("chainId") != "ton":
            continue

        liquidity_usd = float((pair.get("liquidity") or {}).get("usd") or 0)
        volume_h24 = float((pair.get("volume") or {}).get("h24") or 0)

        if liquidity_usd < _MIN_LIQUIDITY or volume_h24 < _MIN_VOLUME:
            continue

        base = pair.get("baseToken") or {}
        txns_h24 = (pair.get("txns") or {}).get("h24") or {}

        try:
            price = float(pair.get("priceUsd") or 0)
        except (TypeError, ValueError):
            price = 0.0

        tokens.append({
            "name": base.get("name", ""),
            "symbol": base.get("symbol", ""),
            "address": base.get("address", ""),
            "pair": pair.get("pairAddress", ""),
            "price": price,
            "price_change_h24": float((pair.get("priceChange") or {}).get("h24") or 0),
            "mcap": float(pair.get("fdv") or 0),
            "liquidity": liquidity_usd,
            "volume": volume_h24,
            "buys": int(txns_h24.get("buys") or 0),
            "sells": int(txns_h24.get("sells") or 0),
        })

    tokens.sort(key=lambda t: t["volume"], reverse=True)
    return tokens[:_TOP_N]


# ── Formatting ────────────────────────────────────────────────────────────────

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


def format_top_tokens(tokens: list[dict]) -> str:
    if not tokens:
        return "<b>DEX TON TOP</b>\n\nNo data available."

    lines = ["<b>DEX TON TOP</b>\n"]
    sep = "─" * 22

    for i, t in enumerate(tokens, 1):
        block = (
            f"{i}. <b>{t['symbol']}</b>\n"
            f"   Price: {_fmt_price(t['price'])}\n"
            f"   MCAP: {_fmt_usd(t['mcap'])}\n"
            f"   LIQ: {_fmt_usd(t['liquidity'])}\n"
            f"   VOL: {_fmt_usd(t['volume'])}\n"
            f"   TXNS: {t['buys']}/{t['sells']}\n\n"
            f"Address:\n{address_link(t['address'])}"
        )
        lines.append(block)
        if i < len(tokens):
            lines.append(sep)

    return "\n".join(lines)
