from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass

from bot.services.tonapi import TonApiService

log = logging.getLogger(__name__)

_DUST_TON = 0.001

_KNOWN_LABELS: dict[str, str] = {
    "EQCxE6mUtQJKFnGfaROTKOt1lZbDiiX1kCixRv7Nw2Id_sDs": "Binance",
    "EQB3ncyBUTjZUA5EnFKR5_EnOMI9V1tTEAAPaiU71gc4TiUt": "OKX",
}


@dataclass(slots=True)
class NetworkNode:
    address: str
    label: str | None
    tx_count: int
    in_count: int
    out_count: int
    total_volume: float
    is_mutual: bool


@dataclass(slots=True)
class NetworkReport:
    address: str
    total_connections: int
    nodes: list[NetworkNode]   # top 10 sorted by tx_count
    mutual_count: int
    cluster_detected: bool     # True when 3+ mutual high-tx addresses


async def analyze_network(
    address: str,
    *,
    tonapi: TonApiService,
    limit: int = 200,
) -> NetworkReport:
    """Build a connection graph for the wallet from its recent transactions."""
    try:
        raw = await tonapi.get_pnl_transactions(address, limit=limit)
    except Exception as exc:
        log.warning("analyze_network failed for %s: %s", address, exc)
        raw = []

    txs = [r for r, _f in raw if r.counterparty != "unknown" and r.amount_ton >= _DUST_TON]

    counter_stats: dict[str, dict] = defaultdict(lambda: {"in": 0, "out": 0, "vol": 0.0})
    for tx in txs:
        counter_stats[tx.counterparty]["in" if tx.direction == "IN" else "out"] += 1
        counter_stats[tx.counterparty]["vol"] += tx.amount_ton

    in_addrs = {tx.counterparty for tx in txs if tx.direction == "IN"}
    out_addrs = {tx.counterparty for tx in txs if tx.direction == "OUT"}
    mutual_addrs = in_addrs & out_addrs

    nodes = sorted(
        [
            NetworkNode(
                address=addr,
                label=_KNOWN_LABELS.get(addr),
                tx_count=stats["in"] + stats["out"],
                in_count=stats["in"],
                out_count=stats["out"],
                total_volume=stats["vol"],
                is_mutual=addr in mutual_addrs,
            )
            for addr, stats in counter_stats.items()
        ],
        key=lambda n: n.tx_count,
        reverse=True,
    )

    # Cluster: 3+ mutual addresses each with 3+ transactions
    high_mutual = sum(1 for n in nodes if n.is_mutual and n.tx_count >= 3)

    return NetworkReport(
        address=address,
        total_connections=len(nodes),
        nodes=nodes[:10],
        mutual_count=len(mutual_addrs),
        cluster_detected=high_mutual >= 3,
    )
