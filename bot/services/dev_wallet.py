from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from bot.services.cache import CacheService
from bot.services.tonapi import TonApiService
from config import Settings

log = logging.getLogger(__name__)

_CACHE_TTL = 20  # seconds — fast enough for live analysis, avoids hammering tonapi


class DevWalletAnalyzer:
    """Identifies and analyzes the developer/admin wallet for a TON token."""

    def __init__(self, tonapi: TonApiService, cache: CacheService, settings: Settings) -> None:
        self._tonapi = tonapi
        self._cache = cache
        self._settings = settings

    # ── Dev address resolution ────────────────────────────────────────────────

    async def get_dev_address(self, token_address: str) -> str | None:
        """Return the admin/deployer address for a jetton, or None if unavailable."""
        if not token_address:
            return None

        cache_key = f"dev_addr:{token_address}"
        cached = await self._cache.get_json(cache_key)
        if cached is not None:
            return cached.get("address")

        address: str | None = None

        # Strategy 1: jetton admin field from TonAPI metadata
        try:
            metadata = await self._tonapi.get_jetton_metadata(token_address)
            admin = metadata.get("admin")
            if isinstance(admin, dict):
                address = admin.get("address") or None
            if not address:
                # Some responses put it at top level
                address = metadata.get("admin_address") or None
        except Exception as exc:
            log.debug("Jetton metadata unavailable for %s: %s", token_address, exc)

        # Strategy 2: top holder as fallback
        if not address:
            try:
                holders_data = await self._tonapi.get_jetton_holders(token_address, limit=3)
                addresses_list = holders_data.get("addresses") or []
                if addresses_list:
                    first = addresses_list[0]
                    if isinstance(first, dict):
                        owner = first.get("owner") or {}
                        address = (owner.get("address") if isinstance(owner, dict) else None) or first.get("address")
            except Exception as exc:
                log.debug("Jetton holders unavailable for %s: %s", token_address, exc)

        await self._cache.set_json(cache_key, {"address": address}, _CACHE_TTL)
        return address

    # ── Wallet analysis ────────────────────────────────────────────────────────

    async def analyze_dev_wallet(self, address: str) -> dict[str, Any]:
        """Fetch wallet metrics and detect risk flags for a dev/admin address."""
        cache_key = f"dev_analysis:{address}"
        cached = await self._cache.get_json(cache_key)
        if cached is not None:
            return cached

        result: dict[str, Any] = {
            "address": address,
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

        try:
            report = await self._tonapi.get_wallet_report(address, limit=50)
            result["balance"] = report.balance_ton

            now = datetime.now(timezone.utc)
            cutoff_24h = now - timedelta(hours=24)

            tx_24h = 0
            total_out = 0.0
            total_in = 0.0
            out_counterparties: list[str] = []

            for tx in report.transactions:
                if tx.direction == "OUT":
                    total_out += tx.amount_ton
                    out_counterparties.append(tx.counterparty)
                else:
                    total_in += tx.amount_ton
                if tx.timestamp >= cutoff_24h:
                    tx_24h += 1

            unique_addrs = len(
                {tx.counterparty for tx in report.transactions if tx.counterparty != "unknown"}
            )
            unique_out = len(set(out_counterparties))

            result.update({
                "tx_count": len(report.transactions),
                "tx_count_24h": tx_24h,
                "total_outgoing": total_out,
                "total_incoming": total_in,
                "unique_addresses": unique_addrs,
                "last_tx_time": report.last_activity.isoformat() if report.last_activity else None,
                "activity": "ACTIVE" if tx_24h > 0 else "LOW",
            })

            flags: list[str] = []
            if total_in > 0.1 and total_out > total_in * 2:
                flags.append("Mass outgoing transfers")
            if unique_out >= 8:
                flags.append("Transfers to many addresses")
            if unique_addrs >= 12:
                flags.append("High address cluster")
            if report.balance_ton < 1.0 and total_out > 5.0:
                flags.append("Wallet drained")
            result["risk_flags"] = flags

        except Exception as exc:
            log.warning("Dev wallet analysis failed for %s: %s", address, exc)

        await self._cache.set_json(cache_key, result, _CACHE_TTL)
        return result
