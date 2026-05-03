from __future__ import annotations

import logging
import time
from typing import Any

import aiohttp

log = logging.getLogger(__name__)

_API_URL = "https://api.dexscreener.com/latest/dex/pairs/ton"
_MAX_AGE_MINUTES: float = 20.0
_MIN_LIQUIDITY: float = 2_000.0
_TIMEOUT: int = 8


async def fetch_new_listings() -> list[dict[str, Any]]:
    """
    Pull all TON pairs from DexScreener and keep only those that are:
      - younger than _MAX_AGE_MINUTES (based on pairCreatedAt)
      - liquid enough (liquidity.usd >= _MIN_LIQUIDITY)

    Returns dicts enriched with a synthetic ``_age_minutes`` key.
    Sorted newest-first.
    """
    raw = await _get_pairs()
    if not raw:
        return []

    now_ms = int(time.time() * 1000)
    cutoff_ms = now_ms - int(_MAX_AGE_MINUTES * 60 * 1000)
    results: list[dict[str, Any]] = []

    for pair in raw:
        created_at = pair.get("pairCreatedAt")
        if not created_at:
            continue
        try:
            created_at = int(created_at)
        except (TypeError, ValueError):
            continue
        if created_at < cutoff_ms:
            continue

        liquidity_usd = float((pair.get("liquidity") or {}).get("usd") or 0)
        if liquidity_usd < _MIN_LIQUIDITY:
            continue

        age_minutes = (now_ms - created_at) / 60_000
        results.append({**pair, "_age_minutes": age_minutes})

    results.sort(key=lambda p: p.get("pairCreatedAt", 0), reverse=True)
    return results


async def _get_pairs() -> list[dict[str, Any]]:
    try:
        timeout = aiohttp.ClientTimeout(total=_TIMEOUT)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(_API_URL) as resp:
                if resp.status != 200:
                    log.warning("DexScreener /pairs/ton returned HTTP %s", resp.status)
                    return []
                data: dict[str, Any] = await resp.json(content_type=None)
        return data.get("pairs") or []
    except Exception as exc:
        log.warning("fetch_new_listings request failed: %s", exc)
        return []
