from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from bot.services.cache import CacheService
from bot.services.tonapi import TonApiService

log = logging.getLogger(__name__)

_CACHE_TTL = 300  # 5 minutes
_TONSCAN_ADDR = "https://tonscan.org/address/{address}"


@dataclass(slots=True)
class TokenHolder:
    rank: int
    owner_address: str
    balance: float
    percent_of_supply: float | None
    symbol: str

    @property
    def tonscan_url(self) -> str:
        return _TONSCAN_ADDR.format(address=self.owner_address)


@dataclass(slots=True)
class TokenLeaderboard:
    token_address: str
    symbol: str
    total_supply: float | None
    holders: list[TokenHolder]


async def get_token_holders(
    token_address: str,
    *,
    tonapi: TonApiService,
    cache: CacheService,
    limit: int = 10,
) -> TokenLeaderboard:
    """Fetch top N holders for any jetton address.

    Caches results for 5 minutes to avoid redundant API calls.
    """
    cache_key = f"lb:holders:{token_address.strip()}:{limit}"
    cached = await cache.get_json(cache_key)
    if cached:
        holders = [
            TokenHolder(
                rank=h["rank"],
                owner_address=h["owner_address"],
                balance=h["balance"],
                percent_of_supply=h.get("percent_of_supply"),
                symbol=h.get("symbol", "TOKEN"),
            )
            for h in cached["holders"]
        ]
        return TokenLeaderboard(
            token_address=token_address,
            symbol=cached.get("symbol", "TOKEN"),
            total_supply=cached.get("total_supply"),
            holders=holders,
        )

    metadata = await tonapi.get_jetton_metadata(token_address.strip())
    meta_inner = metadata.get("metadata", {}) or {}
    decimals = int(meta_inner.get("decimals", 9) or 9)
    divisor = 10 ** decimals
    symbol = (meta_inner.get("symbol") or meta_inner.get("name") or "TOKEN").strip()

    total_supply_raw = float(metadata.get("total_supply", 0) or 0)
    total_supply = total_supply_raw / divisor if total_supply_raw else None

    holders_payload = await tonapi.get_jetton_holders(token_address.strip(), limit=limit)
    holders: list[TokenHolder] = []
    for index, item in enumerate(holders_payload.get("addresses", [])[:limit], start=1):
        owner = item.get("owner", {}) or {}
        balance = float(item.get("balance", 0) or 0) / divisor
        percent = (balance / total_supply * 100.0) if total_supply else None
        holders.append(
            TokenHolder(
                rank=index,
                owner_address=owner.get("address", "unknown"),
                balance=balance,
                percent_of_supply=percent,
                symbol=symbol,
            )
        )

    await cache.set_json(
        cache_key,
        {
            "symbol": symbol,
            "total_supply": total_supply,
            "holders": [
                {
                    "rank": h.rank,
                    "owner_address": h.owner_address,
                    "balance": h.balance,
                    "percent_of_supply": h.percent_of_supply,
                    "symbol": h.symbol,
                }
                for h in holders
            ],
            "cached_at": int(datetime.now(timezone.utc).timestamp()),
        },
        _CACHE_TTL,
    )

    return TokenLeaderboard(
        token_address=token_address,
        symbol=symbol,
        total_supply=total_supply,
        holders=holders,
    )


# ── Per-user active token storage ─────────────────────────────────────────────

_LB_TOKEN_TTL = 60 * 60 * 24  # 24 hours


async def get_active_token(user_id: int, *, cache: CacheService, default: str) -> str:
    """Return the user's last-searched token address, or the default ALGO address."""
    cached = await cache.get_json(f"lb_token:{user_id}")
    if cached and isinstance(cached.get("address"), str):
        return cached["address"]
    return default


async def set_active_token(user_id: int, token_address: str, *, cache: CacheService) -> None:
    """Persist the user's active token across navigation."""
    await cache.set_json(
        f"lb_token:{user_id}",
        {"address": token_address.strip()},
        _LB_TOKEN_TTL,
    )
