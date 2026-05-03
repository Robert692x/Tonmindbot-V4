from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from bot.services.cache import CacheService
from bot.services.tonapi import JettonHolding, TonApiService
from config import Settings

log = logging.getLogger(__name__)


def _shorten_address(address: str, head: int = 5, tail: int = 3) -> str:
    if len(address) <= head + tail + 3:
        return address
    return f"{address[:head]}...{address[-tail:]}"


@dataclass(slots=True)
class AlgoHolder:
    rank: int
    owner_address: str
    balance: float
    percent_of_supply: float | None

    @property
    def short_address(self) -> str:
        return _shorten_address(self.owner_address)


class AlgoService:
    def __init__(self, settings: Settings, cache: CacheService, tonapi: TonApiService) -> None:
        self.settings = settings
        self.cache = cache
        self.tonapi = tonapi

    async def close(self) -> None:
        return None

    async def get_algo_balance(self, address: str) -> float:
        portfolio = await self.tonapi.get_wallet_portfolio(address)
        for holding in portfolio:
            if holding.is_algo:
                return holding.balance
        return 0.0

    async def get_algo_holders(self, *, limit: int = 10) -> tuple[list[AlgoHolder], float | None]:
        cache_key = f"algo:holders:{limit}"
        cached = await self.cache.get_json(cache_key)
        if cached:
            return (
                [
                    AlgoHolder(
                        rank=item["rank"],
                        owner_address=item["owner_address"],
                        balance=item["balance"],
                        percent_of_supply=item["percent_of_supply"],
                    )
                    for item in cached["holders"]
                ],
                cached.get("total_supply"),
            )

        try:
            metadata = await self.tonapi.get_jetton_metadata(self.settings.ALGO_JETTON_ADDRESS)
            holders_payload = await self.tonapi.get_jetton_holders(self.settings.ALGO_JETTON_ADDRESS, limit=limit)
            decimals = int(metadata.get("metadata", {}).get("decimals", 9) or 9)
            divisor = 10 ** decimals
            total_supply_raw = float(metadata.get("total_supply", 0) or 0)
            total_supply = total_supply_raw / divisor if total_supply_raw else None

            holders = []
            for index, item in enumerate(holders_payload.get("addresses", [])[:limit], start=1):
                owner = item.get("owner", {}) or {}
                balance = float(item.get("balance", 0) or 0) / divisor
                percent = (balance / total_supply * 100.0) if total_supply else None
                holders.append(
                    AlgoHolder(
                        rank=index,
                        owner_address=owner.get("address", "unknown"),
                        balance=balance,
                        percent_of_supply=percent,
                    )
                )
            await self.cache.set_json(
                cache_key,
                {
                    "holders": [
                        {
                            "rank": holder.rank,
                            "owner_address": holder.owner_address,
                            "balance": holder.balance,
                            "percent_of_supply": holder.percent_of_supply,
                        }
                        for holder in holders
                    ],
                    "total_supply": total_supply,
                    "cached_at": int(datetime.now(timezone.utc).timestamp()),
                },
                self.settings.CACHE_TTL_LEADERBOARD_SECONDS,
            )
            return holders, total_supply
        except Exception as exc:
            log.warning("ALGO holders fetch failed: %s", exc)
            if cached:
                return (
                    [
                        AlgoHolder(
                            rank=item["rank"],
                            owner_address=item["owner_address"],
                            balance=item["balance"],
                            percent_of_supply=item["percent_of_supply"],
                        )
                        for item in cached["holders"]
                    ],
                    cached.get("total_supply"),
                )
            return [], None
