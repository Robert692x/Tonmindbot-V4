from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

log = logging.getLogger(__name__)

_NANO = 1_000_000_000
_MIN_AMOUNT_NANO = 10_000_000  # 0.01 TON


# ── Normalized transaction ────────────────────────────────────────────────────

@dataclass(slots=True)
class NormalizedTx:
    hash: str
    amount_ton: float
    from_addr: str
    to_addr: str
    direction: str        # IN / OUT
    time: datetime
    lt: int
    fee_ton: float
    status: str


# ── Internal helpers ──────────────────────────────────────────────────────────

def _extract_address(node: Any) -> str:
    if isinstance(node, dict):
        addr = node.get("address")
        if isinstance(addr, str) and addr:
            return addr
    if isinstance(node, str) and node:
        return node
    return "unknown"


def _effective_amount_nano(tx: dict[str, Any]) -> int:
    """Best single amount to represent this raw transaction in nanoton."""
    out_msgs = tx.get("out_msgs") or []
    if out_msgs:
        return sum(int(m.get("value", 0) or 0) for m in out_msgs)
    in_msg = tx.get("in_msg") or {}
    return int(in_msg.get("value", 0) or 0)


def _is_internal_only(tx: dict[str, Any]) -> bool:
    """True when the transaction is a pure internal relay with no user-visible amount."""
    in_msg = tx.get("in_msg") or {}
    # TON API labels purely internal messages with msg_type "int_msg"
    if in_msg.get("msg_type") == "int_msg" and not tx.get("out_msgs"):
        return True
    return False


def _determine_direction(tx: dict[str, Any], wallet_address: str) -> str:
    in_msg = tx.get("in_msg") or {}
    dest = _extract_address(in_msg.get("destination"))
    return "IN" if dest == wallet_address else "OUT"


def _tx_status(tx: dict[str, Any]) -> str:
    try:
        code = tx["description"]["action"]["result_code"]
        return "success" if code == 0 else f"failed ({code})"
    except (KeyError, TypeError):
        return "success"


def _to_normalized(tx_hash: str, tx: dict[str, Any], wallet_address: str) -> NormalizedTx:
    out_msgs = tx.get("out_msgs") or []
    in_msg = tx.get("in_msg") or {}

    if out_msgs:
        amount_nano = sum(int(m.get("value", 0) or 0) for m in out_msgs)
        from_addr = _extract_address(in_msg.get("source") or tx.get("account"))
        to_addr = _extract_address(out_msgs[0].get("destination"))
    else:
        amount_nano = int(in_msg.get("value", 0) or 0)
        from_addr = _extract_address(in_msg.get("source"))
        to_addr = _extract_address(in_msg.get("destination"))

    direction = "IN" if to_addr == wallet_address else "OUT"
    utime = tx.get("utime") or 0
    lt = int(tx.get("lt") or 0)
    fee_nano = int(tx.get("total_fees") or 0)

    return NormalizedTx(
        hash=tx_hash,
        amount_ton=amount_nano / _NANO,
        from_addr=from_addr,
        to_addr=to_addr,
        direction=direction,
        time=datetime.fromtimestamp(utime, tz=timezone.utc),
        lt=lt,
        fee_ton=fee_nano / _NANO,
        status=_tx_status(tx),
    )


# ── Public API ────────────────────────────────────────────────────────────────

def normalize_transactions(
    raw_txs: list[dict[str, Any]],
    wallet_address: str,
) -> list[NormalizedTx]:
    """Group raw API transactions by hash, filter dust/internal, pick the
    event with the largest amount per group.

    1 logical transaction → 1 NormalizedTx.
    """
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for tx in raw_txs:
        tx_hash = tx.get("hash", "")
        if not tx_hash:
            continue
        if _is_internal_only(tx):
            continue
        groups[tx_hash].append(tx)

    result: list[NormalizedTx] = []
    for tx_hash, events in groups.items():
        # pick the event with the largest effective amount
        best = max(events, key=_effective_amount_nano)
        if _effective_amount_nano(best) < _MIN_AMOUNT_NANO:
            continue
        result.append(_to_normalized(tx_hash, best, wallet_address))

    # newest first
    return sorted(result, key=lambda t: t.lt, reverse=True)


def format_alert(
    wallet_name: str,
    wallet_address: str,
    tx: NormalizedTx,
) -> str:
    """Canonical wallet alert — exact spec format.

    Each TonScan URL appears on its own line as clickable text.
    Full addresses and hashes — no truncation.
    """
    from bot.utils.links import address_link, tx_link

    sign = "+" if tx.direction == "IN" else "-"
    time_str = tx.time.strftime("%Y-%m-%d %H:%M:%S UTC")

    return "\n".join([
        "<b>WALLET ALERT</b>",
        "",
        f"Name: {wallet_name}",
        "Address:",
        address_link(wallet_address),
        "",
        f"Action: <b>{tx.direction}</b>",
        f"Amount: <b>{sign}{tx.amount_ton:,.4f} TON</b>",
        "",
        "From:",
        address_link(tx.from_addr),
        "",
        "To:",
        address_link(tx.to_addr),
        "",
        f"Time: {time_str}",
        "",
        "Transaction:",
        tx_link(tx.hash),
        "",
        f"Logical Time (LT): <code>{tx.lt}</code>",
        f"Fee: {tx.fee_ton:.6f} TON",
        "",
        f"Status: {tx.status}",
    ])


def process_alerts(
    raw_txs: list[dict[str, Any]],
    wallet_address: str,
    *,
    seen_hashes: set[str],
) -> list[NormalizedTx]:
    """Full pipeline: normalize → deduplicate → return unseen transactions.

    Updates `seen_hashes` in-place for every returned tx.
    """
    normalized = normalize_transactions(raw_txs, wallet_address)
    new: list[NormalizedTx] = []
    for tx in normalized:
        if tx.hash in seen_hashes:
            continue
        seen_hashes.add(tx.hash)
        new.append(tx)
    return new
