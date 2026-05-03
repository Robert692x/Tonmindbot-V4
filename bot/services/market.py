from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

import aiohttp

from bot.services.cache import CacheService
from config import Settings

log = logging.getLogger(__name__)

MARKET_OVERVIEW_IDS = ["the-open-network", "ethereum"]


@dataclass(slots=True)
class TonMarketSnapshot:
    price_usd: float
    change_24h_pct: float
    volume_24h_usd: float
    market_cap_usd: float


@dataclass(slots=True)
class TokenSnapshot:
    coin_id: str
    name: str
    symbol: str
    price_usd: float
    change_1h_pct: float | None
    change_24h_pct: float
    volume_24h_usd: float
    market_cap_usd: float


@dataclass(slots=True)
class DexPoolSnapshot:
    token0: str
    token1: str
    tvl_usd: float
    apy_1d: float | None


def _parse_token(item: dict[str, Any]) -> TokenSnapshot:
    raw_1h = item.get("price_change_percentage_1h_in_currency")
    return TokenSnapshot(
        coin_id=item.get("id", ""),
        name=item.get("name", ""),
        symbol=(item.get("symbol") or "").upper(),
        price_usd=float(item.get("current_price") or 0.0),
        change_1h_pct=float(raw_1h) if raw_1h is not None else None,
        change_24h_pct=float(
            item.get("price_change_percentage_24h_in_currency")
            or item.get("price_change_percentage_24h")
            or 0.0
        ),
        volume_24h_usd=float(item.get("total_volume") or 0.0),
        market_cap_usd=float(item.get("market_cap") or 0.0),
    )


def _token_to_dict(t: TokenSnapshot) -> dict[str, Any]:
    return {
        "coin_id": t.coin_id,
        "name": t.name,
        "symbol": t.symbol,
        "price_usd": t.price_usd,
        "change_1h_pct": t.change_1h_pct,
        "change_24h_pct": t.change_24h_pct,
        "volume_24h_usd": t.volume_24h_usd,
        "market_cap_usd": t.market_cap_usd,
    }


class MarketService:
    def __init__(self, settings: Settings, cache: CacheService) -> None:
        self.settings = settings
        self.cache = cache
        timeout = aiohttp.ClientTimeout(total=settings.REQUEST_TIMEOUT_SECONDS)
        self._coingecko = aiohttp.ClientSession(timeout=timeout)
        self._ston = aiohttp.ClientSession(base_url=settings.STON_API_BASE, timeout=timeout)

    async def close(self) -> None:
        await self._coingecko.close()
        await self._ston.close()

    async def get_ton_market_snapshot(self) -> TonMarketSnapshot:
        cache_key = "market:ton:price"
        cached = await self.cache.get_json(cache_key)
        if cached:
            return TonMarketSnapshot(**cached)

        async with self._coingecko.get(
            f"{self.settings.COINGECKO_API_BASE}/simple/price",
            params={
                "ids": "the-open-network",
                "vs_currencies": "usd",
                "include_24hr_change": "true",
                "include_24hr_vol": "true",
                "include_market_cap": "true",
            },
        ) as response:
            response.raise_for_status()
            payload = (await response.json())["the-open-network"]

        snapshot = TonMarketSnapshot(
            price_usd=float(payload.get("usd", 0.0) or 0.0),
            change_24h_pct=float(payload.get("usd_24h_change", 0.0) or 0.0),
            volume_24h_usd=float(payload.get("usd_24h_vol", 0.0) or 0.0),
            market_cap_usd=float(payload.get("usd_market_cap", 0.0) or 0.0),
        )
        await self.cache.set_json(
            cache_key,
            {
                "price_usd": snapshot.price_usd,
                "change_24h_pct": snapshot.change_24h_pct,
                "volume_24h_usd": snapshot.volume_24h_usd,
                "market_cap_usd": snapshot.market_cap_usd,
            },
            self.settings.CACHE_TTL_PRICE_SECONDS,
        )
        return snapshot

    async def get_top_dex_pools(self, *, limit: int = 5) -> list[DexPoolSnapshot]:
        cache_key = f"dex:pools:{limit}"
        cached = await self.cache.get_json(cache_key)
        if cached:
            return [DexPoolSnapshot(**item) for item in cached]

        async with self._ston.get("/v1/pools", params={"limit": limit}) as response:
            response.raise_for_status()
            payload = (await response.json()).get("pool_list", [])
        pools = [
            DexPoolSnapshot(
                token0=item.get("token0_symbol", "?"),
                token1=item.get("token1_symbol", "?"),
                tvl_usd=float(item.get("lp_total_supply_usd", 0.0) or 0.0),
                apy_1d=float(item["apy_1d"]) if item.get("apy_1d") is not None else None,
            )
            for item in payload[:limit]
        ]
        await self.cache.set_json(
            cache_key,
            [
                {
                    "token0": pool.token0,
                    "token1": pool.token1,
                    "tvl_usd": pool.tvl_usd,
                    "apy_1d": pool.apy_1d,
                }
                for pool in pools
            ],
            self.settings.CACHE_TTL_DEX_SECONDS,
        )
        return pools

    async def get_signal_context(self) -> dict[str, object]:
        market = await self.get_ton_market_snapshot()
        pools = await self.get_top_dex_pools(limit=3)
        return {
            "price_usd": market.price_usd,
            "change_24h_pct": market.change_24h_pct,
            "volume_24h_usd": market.volume_24h_usd,
            "top_pools": [
                {
                    "token0": pool.token0,
                    "token1": pool.token1,
                    "tvl_usd": pool.tvl_usd,
                    "apy_1d": pool.apy_1d,
                }
                for pool in pools
            ],
        }

    async def calculate_1h_change(self, token_id: str, current_price: float) -> float | None:
        """Fetch market_chart for the last ~2h and derive 1h % change manually."""
        cache_key = f"market:1h:{token_id}"
        cached = await self.cache.get_json(cache_key)
        if cached is not None:
            return float(cached)

        try:
            async with self._coingecko.get(
                f"{self.settings.COINGECKO_API_BASE}/coins/{token_id}/market_chart",
                params={"vs_currency": "usd", "days": "0.1"},
            ) as response:
                response.raise_for_status()
                data = await response.json()
        except Exception as exc:
            log.warning("market_chart fetch failed for %s: %s", token_id, exc)
            return None

        prices: list[list[float]] = data.get("prices", [])
        if len(prices) < 2:
            return None

        now_ms = prices[-1][0]
        one_hour_ago_ms = now_ms - 3_600_000

        # Find the first data point at or after the 1-hour mark (closest to 1h ago)
        price_1h_ago: float | None = None
        for ts, price in prices:
            if ts >= one_hour_ago_ms:
                price_1h_ago = price
                break

        if price_1h_ago is None or price_1h_ago == 0:
            return None

        change = ((current_price - price_1h_ago) / price_1h_ago) * 100.0
        await self.cache.set_json(cache_key, change, self.settings.CACHE_TTL_PRICE_SECONDS)
        return change

    async def _fill_missing_1h_changes(self, tokens: list[TokenSnapshot]) -> None:
        """Parallel fallback: calculate 1h change for tokens that are missing it."""
        missing = [(i, t) for i, t in enumerate(tokens) if t.change_1h_pct is None]
        if not missing:
            return

        results = await asyncio.gather(
            *[self.calculate_1h_change(t.coin_id, t.price_usd) for _, t in missing],
            return_exceptions=True,
        )
        for (i, _), result in zip(missing, results):
            if isinstance(result, float):
                tokens[i].change_1h_pct = result

    async def get_tokens_market(self, coin_ids: list[str]) -> list[TokenSnapshot]:
        cache_key = f"market:tokens:{','.join(sorted(coin_ids))}"
        cached = await self.cache.get_json(cache_key)
        if cached:
            return [TokenSnapshot(**item) for item in cached]

        async with self._coingecko.get(
            f"{self.settings.COINGECKO_API_BASE}/coins/markets",
            params={
                "vs_currency": "usd",
                "ids": ",".join(coin_ids),
                "price_change_percentage": "1h,24h",
                "sparkline": "false",
                "locale": "en",
            },
        ) as response:
            response.raise_for_status()
            payload: list[dict] = await response.json()

        tokens = [_parse_token(item) for item in payload]
        order = {cid: i for i, cid in enumerate(coin_ids)}
        tokens.sort(key=lambda t: order.get(t.coin_id, 999))

        # Fill 1h change via market_chart for any token that didn't get it
        await self._fill_missing_1h_changes(tokens)

        await self.cache.set_json(
            cache_key,
            [_token_to_dict(t) for t in tokens],
            self.settings.CACHE_TTL_PRICE_SECONDS,
        )
        return tokens

    async def get_token_data(self, token_id: str) -> TokenSnapshot:
        tokens = await self.get_tokens_market([token_id])
        if not tokens:
            raise ValueError(f"Token not found: {token_id}")
        return tokens[0]

    async def get_market_overview(self) -> list[TokenSnapshot]:
        return await self.get_tokens_market(MARKET_OVERVIEW_IDS)

    async def search_token(self, query: str, *, limit: int = 3) -> list[TokenSnapshot]:
        query = query.strip()
        search_cache_key = f"market:search:{query.lower()}"
        coin_ids: list[str] | None = await self.cache.get_json(search_cache_key)

        if coin_ids is None:
            try:
                async with self._coingecko.get(
                    f"{self.settings.COINGECKO_API_BASE}/search",
                    params={"query": query},
                ) as response:
                    response.raise_for_status()
                    data = await response.json()
            except Exception as exc:
                log.warning("CoinGecko search failed for %r: %s", query, exc)
                return []

            coin_ids = [c["id"] for c in data.get("coins", [])[:limit] if c.get("id")]
            if not coin_ids:
                return []
            await self.cache.set_json(search_cache_key, coin_ids, self.settings.CACHE_TTL_PRICE_SECONDS)

        try:
            return await self.get_tokens_market(coin_ids[:limit])
        except Exception as exc:
            log.warning("CoinGecko markets fetch failed: %s", exc)
            return []

    async def get_trending(self, *, limit: int = 5) -> list[TokenSnapshot]:
        cache_key = "market:trending"
        cached = await self.cache.get_json(cache_key)
        if cached:
            return [TokenSnapshot(**item) for item in cached]

        try:
            async with self._coingecko.get(
                f"{self.settings.COINGECKO_API_BASE}/search/trending",
            ) as response:
                response.raise_for_status()
                data = await response.json()
        except Exception as exc:
            log.warning("CoinGecko trending fetch failed: %s", exc)
            return []

        coin_ids = [
            item["item"]["id"]
            for item in data.get("coins", [])[:limit]
            if item.get("item", {}).get("id")
        ]
        if not coin_ids:
            return []

        tokens = await self.get_tokens_market(coin_ids)
        await self.cache.set_json(
            cache_key,
            [_token_to_dict(t) for t in tokens],
            self.settings.CACHE_TTL_PRICE_SECONDS * 5,
        )
        return tokens
