from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from statistics import mean

from bot.services.tonapi import TonApiService, TransactionRecord

log = logging.getLogger(__name__)

_DUST_TON = 0.001


# ── Legacy PnL (kept for backward compat) ────────────────────────────────────

@dataclass(slots=True)
class WalletPnL:
    address: str
    period_days: int
    inflow: float
    outflow: float
    fees: float
    tx_count: int

    @property
    def profit(self) -> float:
        return self.inflow - self.outflow - self.fees


async def calculate_wallet_pnl(
    address: str,
    days: int,
    *,
    tonapi: TonApiService,
) -> WalletPnL:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    try:
        raw = await tonapi.get_pnl_transactions(address, limit=200)
    except Exception as exc:
        log.warning("Failed to fetch PnL transactions for %s: %s", address, exc)
        return WalletPnL(address=address, period_days=days, inflow=0, outflow=0, fees=0, tx_count=0)

    inflow = outflow = fees = 0.0
    count = 0
    for record, fee_ton in raw:
        if record.timestamp < since or record.amount_ton < _DUST_TON:
            continue
        count += 1
        fees += fee_ton
        if record.direction == "IN":
            inflow += record.amount_ton
        else:
            outflow += record.amount_ton

    return WalletPnL(address=address, period_days=days, inflow=inflow, outflow=outflow, fees=fees, tx_count=count)


# ── Extended Behavioral Analytics ─────────────────────────────────────────────

@dataclass(slots=True)
class FrequentAddress:
    address: str
    tx_count: int
    in_count: int
    out_count: int
    total_volume: float


@dataclass(slots=True)
class FlipperScore:
    score: int           # 0–100
    label: str           # Investor / Trader / Flipper
    trades_per_day: float
    in_out_ratio: float
    mutual_addresses: int
    avg_hold_hours: float | None
    factors: list[str]


@dataclass(slots=True)
class WalletRiskDetail:
    level: str           # LOW / MEDIUM / HIGH / CRITICAL
    score: int
    factors: list[str]


@dataclass
class WalletBehaviorReport:
    address: str
    first_tx_date: datetime | None
    wallet_age_days: int | None
    total_tx_count: int
    period_days: int
    total_in: float
    total_out: float
    net_flow: float
    unique_addresses: int
    frequent_addresses: list[FrequentAddress]
    flipper: FlipperScore
    risk: WalletRiskDetail
    ai_conclusion: str


# ── Internal computation helpers ──────────────────────────────────────────────

def _compute_flipper(
    transactions: list[TransactionRecord],
    period_days: int,
    total_in: float,
    total_out: float,
) -> FlipperScore:
    score = 0
    factors: list[str] = []

    tx_per_day = len(transactions) / max(period_days, 1)
    if tx_per_day > 20:
        score += 30
        factors.append(f"Very high frequency: {tx_per_day:.1f} tx/day")
    elif tx_per_day > 10:
        score += 20
        factors.append(f"High frequency: {tx_per_day:.1f} tx/day")
    elif tx_per_day > 5:
        score += 10
        factors.append(f"Moderate frequency: {tx_per_day:.1f} tx/day")

    ratio = total_in / max(total_out, 0.001)
    if 0.7 <= ratio <= 1.4:
        score += 20
        factors.append("Balanced IN/OUT ratio — active cycling pattern")

    in_addresses = {
        tx.counterparty for tx in transactions
        if tx.direction == "IN" and tx.counterparty != "unknown"
    }
    out_addresses = {
        tx.counterparty for tx in transactions
        if tx.direction == "OUT" and tx.counterparty != "unknown"
    }
    mutual = in_addresses & out_addresses
    mutual_count = len(mutual)
    if mutual_count > 5:
        score += 20
        factors.append(f"Many mutual addresses: {mutual_count} (repeated cycles detected)")
    elif mutual_count > 2:
        score += 10
        factors.append(f"Some mutual addresses: {mutual_count}")

    # Hold time: time between IN from address X and next OUT to X
    hold_times: list[float] = []
    by_address: dict[str, list[TransactionRecord]] = defaultdict(list)
    for tx in sorted(transactions, key=lambda t: t.timestamp):
        if tx.counterparty != "unknown":
            by_address[tx.counterparty].append(tx)

    for addr, txs in by_address.items():
        ins = [t for t in txs if t.direction == "IN"]
        outs = [t for t in txs if t.direction == "OUT"]
        for in_tx in ins:
            subsequent = [o for o in outs if o.timestamp > in_tx.timestamp]
            if subsequent:
                hold_h = (subsequent[0].timestamp - in_tx.timestamp).total_seconds() / 3600
                if 0 < hold_h < 720:
                    hold_times.append(hold_h)

    avg_hold = mean(hold_times) if hold_times else None
    if avg_hold is not None:
        if avg_hold < 6:
            score += 30
            factors.append(f"Very short hold time: avg {avg_hold:.1f}h")
        elif avg_hold < 24:
            score += 20
            factors.append(f"Short hold time: avg {avg_hold:.1f}h")
        elif avg_hold < 72:
            score += 10
            factors.append(f"Medium hold time: avg {avg_hold:.1f}h")

    score = min(100, score)

    if score >= 61:
        label = "Flipper"
    elif score >= 31:
        label = "Trader"
    else:
        label = "Investor"

    return FlipperScore(
        score=score,
        label=label,
        trades_per_day=tx_per_day,
        in_out_ratio=ratio,
        mutual_addresses=mutual_count,
        avg_hold_hours=avg_hold,
        factors=factors,
    )


def _compute_risk(
    transactions: list[TransactionRecord],
    tx_per_day: float,
    unique_count: int,
) -> WalletRiskDetail:
    score = 0
    factors: list[str] = []

    if tx_per_day > 20:
        score += 25
        factors.append("Extremely high transaction frequency")
    elif tx_per_day > 10:
        score += 15
        factors.append("High transaction frequency")

    if unique_count > 50:
        score += 20
        factors.append("Interacting with a very large number of unique addresses")
    elif unique_count > 20:
        score += 10
        factors.append("Moderate number of unique counterparties")

    dust_in = sum(1 for tx in transactions if tx.direction == "IN" and 0 < tx.amount_ton < 0.05)
    if dust_in > 3:
        score += 20
        factors.append(f"Dust-sized inbound transfers detected ({dust_in})")

    if len(transactions) >= 2:
        sorted_txs = sorted(transactions, key=lambda t: t.timestamp)
        gaps = [
            (sorted_txs[i + 1].timestamp - sorted_txs[i].timestamp).total_seconds() / 60
            for i in range(len(sorted_txs) - 1)
        ]
        avg_gap_min = mean(gaps) if gaps else 9999
        if avg_gap_min < 30:
            score += 20
            factors.append(f"Very rapid transactions (avg gap {avg_gap_min:.0f} min)")
        elif avg_gap_min < 120:
            score += 10
            factors.append(f"Rapid transactions (avg gap {avg_gap_min:.0f} min)")

    total_in = sum(tx.amount_ton for tx in transactions if tx.direction == "IN")
    total_out = sum(tx.amount_ton for tx in transactions if tx.direction == "OUT")
    if total_out > total_in * 2 and total_out > 10:
        score += 15
        factors.append("Significant net outflow pattern")

    score = min(100, score)

    if score >= 76:
        level = "CRITICAL"
    elif score >= 51:
        level = "HIGH"
    elif score >= 26:
        level = "MEDIUM"
    else:
        level = "LOW"
        if not factors:
            factors.append("No high-risk patterns detected")

    return WalletRiskDetail(level=level, score=score, factors=factors)


def _generate_ai_conclusion(report: WalletBehaviorReport) -> str:
    if report.flipper.label == "Flipper":
        behavior = "Active flipper. Fast fund cycling, no accumulation."
    elif report.flipper.label == "Trader":
        behavior = f"Active trader. {report.flipper.trades_per_day:.1f} tx/day, balanced flows."
    else:
        age = f"{report.wallet_age_days}d" if report.wallet_age_days else "?"
        behavior = f"Long-term holder. Low activity ({age}), steady balance."

    if report.net_flow > 50:
        flow = f"Net accumulation +{report.net_flow:,.0f} TON."
    elif report.net_flow < -50:
        flow = f"Net outflow -{abs(report.net_flow):,.0f} TON. Possible withdrawal."
    else:
        flow = "Balanced in/out. No strong directional bias."

    return f"{behavior} {flow}"


# ── Public API ────────────────────────────────────────────────────────────────

async def analyze_wallet_behavior(
    address: str,
    *,
    tonapi: TonApiService,
    period_days: int = 30,
) -> WalletBehaviorReport:
    """Full behavioral analysis: flipper detection, risk scoring, AI conclusion."""
    since = datetime.now(timezone.utc) - timedelta(days=period_days)

    try:
        raw = await tonapi.get_pnl_transactions(address, limit=200)
    except Exception as exc:
        log.warning("analyze_wallet_behavior: failed to fetch txs for %s: %s", address, exc)
        raw = []

    transactions = [
        record
        for record, _fee in raw
        if record.timestamp >= since and record.amount_ton >= _DUST_TON
    ]

    all_txs = [record for record, _fee in raw]
    first_tx = min(all_txs, key=lambda t: t.timestamp) if all_txs else None
    wallet_age_days: int | None = (
        (datetime.now(timezone.utc) - first_tx.timestamp).days if first_tx else None
    )

    total_in = sum(tx.amount_ton for tx in transactions if tx.direction == "IN")
    total_out = sum(tx.amount_ton for tx in transactions if tx.direction == "OUT")
    net_flow = total_in - total_out

    counter_stats: dict[str, dict] = defaultdict(lambda: {"in": 0, "out": 0, "vol": 0.0})
    for tx in transactions:
        if tx.counterparty == "unknown":
            continue
        counter_stats[tx.counterparty]["in" if tx.direction == "IN" else "out"] += 1
        counter_stats[tx.counterparty]["vol"] += tx.amount_ton

    unique_addresses = len(counter_stats)
    frequent_addresses = sorted(
        [
            FrequentAddress(
                address=addr,
                tx_count=stats["in"] + stats["out"],
                in_count=stats["in"],
                out_count=stats["out"],
                total_volume=stats["vol"],
            )
            for addr, stats in counter_stats.items()
        ],
        key=lambda fa: fa.tx_count,
        reverse=True,
    )[:5]

    tx_per_day = len(transactions) / max(period_days, 1)
    flipper = _compute_flipper(transactions, period_days, total_in, total_out)
    risk = _compute_risk(transactions, tx_per_day, unique_addresses)

    report = WalletBehaviorReport(
        address=address,
        first_tx_date=first_tx.timestamp if first_tx else None,
        wallet_age_days=wallet_age_days,
        total_tx_count=len(transactions),
        period_days=period_days,
        total_in=total_in,
        total_out=total_out,
        net_flow=net_flow,
        unique_addresses=unique_addresses,
        frequent_addresses=frequent_addresses,
        flipper=flipper,
        risk=risk,
        ai_conclusion="",
    )
    report.ai_conclusion = _generate_ai_conclusion(report)
    return report


async def get_wallet_activity(
    address: str,
    *,
    tonapi: TonApiService,
) -> dict[str, int]:
    """Return {today, yesterday, week} transaction counts (non-dust only)."""
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday_start = today_start - timedelta(days=1)
    week_start = today_start - timedelta(days=7)

    try:
        raw = await tonapi.get_pnl_transactions(address, limit=200)
    except Exception as exc:
        log.warning("get_wallet_activity failed for %s: %s", address, exc)
        return {"today": 0, "yesterday": 0, "week": 0}

    today = sum(1 for r, _ in raw if r.timestamp >= today_start and r.amount_ton >= _DUST_TON)
    yesterday = sum(
        1 for r, _ in raw
        if yesterday_start <= r.timestamp < today_start and r.amount_ton >= _DUST_TON
    )
    week = sum(1 for r, _ in raw if r.timestamp >= week_start and r.amount_ton >= _DUST_TON)
    return {"today": today, "yesterday": yesterday, "week": week}


async def get_transaction_summary(
    address: str,
    days: int,
    *,
    tonapi: TonApiService,
) -> tuple[list[TransactionRecord], float, float, int]:
    """Return (filtered_txs, total_in, total_out, tx_count) for the given period."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    try:
        raw = await tonapi.get_pnl_transactions(address, limit=200)
    except Exception as exc:
        log.warning("get_transaction_summary failed for %s: %s", address, exc)
        return [], 0.0, 0.0, 0

    txs = [r for r, _f in raw if r.timestamp >= since and r.amount_ton >= _DUST_TON]
    total_in = sum(t.amount_ton for t in txs if t.direction == "IN")
    total_out = sum(t.amount_ton for t in txs if t.direction == "OUT")
    return txs, total_in, total_out, len(txs)
