from __future__ import annotations

from dataclasses import dataclass

from bot.services.wallet_analytics import WalletBehaviorReport


@dataclass(slots=True)
class WalletScore:
    total: int           # 0–100
    activity_score: int  # 0–30
    volume_score: int    # 0–25
    age_score: int       # 0–20
    diversity_score: int # 0–15
    balance_bonus: int   # 0–10
    risk_penalty: int    # 0 to -30
    activity_label: str
    behavior_type: str   # Investor / Trader / Flipper / Whale
    risk_level: str
    grade: str           # A+ … F


def compute_wallet_score(
    behavior: WalletBehaviorReport,
    balance_ton: float,
) -> WalletScore:
    tx_per_day = behavior.total_tx_count / max(behavior.period_days, 1)

    # Activity component (0–30)
    if tx_per_day > 20:
        activity, activity_label = 30, "Very High"
    elif tx_per_day > 10:
        activity, activity_label = 22, "High"
    elif tx_per_day > 3:
        activity, activity_label = 15, "Moderate"
    elif tx_per_day > 0.5:
        activity, activity_label = 8, "Low"
    else:
        activity, activity_label = 2, "Very Low"

    # Volume component (0–25)
    total_vol = behavior.total_in + behavior.total_out
    if total_vol > 100_000:
        volume = 25
    elif total_vol > 10_000:
        volume = 20
    elif total_vol > 1_000:
        volume = 15
    elif total_vol > 100:
        volume = 10
    elif total_vol > 10:
        volume = 5
    else:
        volume = 1

    # Age component (0–20)
    age_days = behavior.wallet_age_days or 0
    if age_days > 730:
        age_score = 20
    elif age_days > 365:
        age_score = 15
    elif age_days > 180:
        age_score = 10
    elif age_days > 30:
        age_score = 5
    else:
        age_score = 0

    # Diversity component (0–15)
    diversity_score = min(15, behavior.unique_addresses // 3)

    # Balance bonus (0–10)
    if balance_ton > 100_000:
        balance_bonus = 10
    elif balance_ton > 10_000:
        balance_bonus = 8
    elif balance_ton > 1_000:
        balance_bonus = 5
    elif balance_ton > 100:
        balance_bonus = 3
    else:
        balance_bonus = 0

    # Risk penalty
    risk_penalty = {"LOW": 0, "MEDIUM": -5, "HIGH": -15, "CRITICAL": -30}.get(behavior.risk.level, 0)

    total = max(0, min(100, activity + volume + age_score + diversity_score + balance_bonus + risk_penalty))

    if total >= 90:
        grade = "A+"
    elif total >= 80:
        grade = "A"
    elif total >= 70:
        grade = "B+"
    elif total >= 60:
        grade = "B"
    elif total >= 50:
        grade = "C+"
    elif total >= 40:
        grade = "C"
    elif total >= 30:
        grade = "D"
    else:
        grade = "F"

    # Whale override
    behavior_type = "Whale" if balance_ton >= 10_000 else behavior.flipper.label

    return WalletScore(
        total=total,
        activity_score=activity,
        volume_score=volume,
        age_score=age_score,
        diversity_score=diversity_score,
        balance_bonus=balance_bonus,
        risk_penalty=risk_penalty,
        activity_label=activity_label,
        behavior_type=behavior_type,
        risk_level=behavior.risk.level,
        grade=grade,
    )
