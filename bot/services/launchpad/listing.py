from __future__ import annotations

import logging
from typing import Any

from bot.services.launchpad.fetcher import fetch_new_listings

log = logging.getLogger(__name__)

_DEX_TON_BASE = "https://dexscreener.com/ton"


async def get_new_tokens(max_items: int = 10) -> list[dict[str, Any]]:
    """Fetch fresh TON pairs and normalize to standard token dict, newest-first."""
    pairs = await fetch_new_listings()
    return [normalize_pair(p) for p in pairs[:max_items]]


def normalize_pair(pair: dict[str, Any]) -> dict[str, Any]:
    """Convert raw DexScreener pair into the project-standard token dict."""
    base = pair.get("baseToken") or {}
    txns = (pair.get("txns") or {}).get("h24") or {}
    pair_address = str(pair.get("pairAddress") or "")
    return {
        "name":             str(base.get("name") or "Unknown"),
        "symbol":           str(base.get("symbol") or "?"),
        "address":          str(base.get("address") or ""),
        "pair":             pair_address,
        "price":            float(pair.get("priceUsd") or 0),
        "price_change_h24": float((pair.get("priceChange") or {}).get("h24") or 0),
        "mcap":             float(pair.get("fdv") or 0),
        "liquidity":        float((pair.get("liquidity") or {}).get("usd") or 0),
        "volume":           float((pair.get("volume") or {}).get("h24") or 0),
        "buys":             int(txns.get("buys") or 0),
        "sells":            int(txns.get("sells") or 0),
        "dex_id":           str(pair.get("dexId") or "").upper().replace("-", "."),
        "url":              pair.get("url") or f"{_DEX_TON_BASE}/{pair_address}",
        "_age_minutes":     float(pair.get("_age_minutes") or 0),
    }
