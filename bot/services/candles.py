from __future__ import annotations

import logging
import time
from typing import Any

import aiohttp

log = logging.getLogger(__name__)

_BINANCE_URL = "https://api.binance.com/api/v3/klines"
_TIMEOUT = 10
_CANDLE_COUNT = 100
_CACHE_TTL = 15  # seconds

# Supported intervals: user-facing label -> Binance interval string
VALID_INTERVALS: dict[str, str] = {
    "1m":  "1m",
    "5m":  "5m",
    "30m": "30m",
    "1h":  "1h",
}
DEFAULT_INTERVAL = "1h"

# {"{pair}:{interval}": (fetched_at, candles)}
_cache: dict[str, tuple[float, list[dict]]] = {}


async def get_candles(pair_address: str, interval: str) -> list[dict]:
    """Return OHLC candles for the given pair + interval.

    pair_address is used as a cache key.  Currently fetches TONUSDT from
    Binance regardless of the pair address; replace _fetch() to support
    arbitrary DEX pairs via DexScreener or similar APIs.
    """
    binance_iv = VALID_INTERVALS.get(interval, VALID_INTERVALS[DEFAULT_INTERVAL])
    cache_key = f"{pair_address}:{interval}"
    now = time.monotonic()

    cached = _cache.get(cache_key)
    if cached is not None:
        fetched_at, candles = cached
        if now - fetched_at < _CACHE_TTL:
            log.debug("Candles cache hit: %s", cache_key)
            return candles

    candles = await _fetch_binance(binance_iv)
    _cache[cache_key] = (now, candles)
    return candles


def invalidate_cache(pair_address: str, interval: str) -> None:
    """Force-expire the cache entry so the next call re-fetches."""
    _cache.pop(f"{pair_address}:{interval}", None)


# ── Binance fetch ─────────────────────────────────────────────────────────────

async def _fetch_binance(interval: str) -> list[dict]:
    params: dict[str, Any] = {
        "symbol": "TONUSDT",
        "interval": interval,
        "limit": _CANDLE_COUNT,
    }
    try:
        timeout = aiohttp.ClientTimeout(total=_TIMEOUT)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(_BINANCE_URL, params=params) as resp:
                if resp.status != 200:
                    log.warning("Binance returned status %s for interval %s", resp.status, interval)
                    return []
                raw: list[list] = await resp.json()
    except Exception as exc:
        log.warning("Binance candles request failed: %s", exc)
        return []

    candles: list[dict] = []
    for kline in raw:
        try:
            candles.append({
                "time":   int(kline[0]) // 1000,
                "open":   float(kline[1]),
                "high":   float(kline[2]),
                "low":    float(kline[3]),
                "close":  float(kline[4]),
                "volume": float(kline[5]),
            })
        except (IndexError, TypeError, ValueError):
            continue

    return candles
