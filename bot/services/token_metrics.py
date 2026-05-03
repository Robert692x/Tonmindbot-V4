from __future__ import annotations

from typing import Any


def extract_token_metrics(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize a raw DexScreener token record for risk analysis."""
    return {
        "name": str(raw.get("name") or "Unknown"),
        "symbol": str(raw.get("symbol") or "?"),
        "address": str(raw.get("address") or ""),
        "pair": str(raw.get("pair") or ""),
        "price": float(raw.get("price") or 0),
        "price_change_h24": float(raw.get("price_change_h24") or 0),
        "mcap": float(raw.get("mcap") or 0),
        "liquidity": float(raw.get("liquidity") or 0),
        "volume": float(raw.get("volume") or 0),
        "buys": int(raw.get("buys") or 0),
        "sells": int(raw.get("sells") or 0),
    }
