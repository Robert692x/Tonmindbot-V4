from __future__ import annotations

from typing import Any

# ── Rug-risk score rules ──────────────────────────────────────────────────────
#
# Score accumulates from 0 upward — higher means MORE suspicious.
# Opposite of the quality score in risk.py (where higher = safer).
#
# 0–29   → Low
# 30–59  → Medium
# 60–100 → High

_LEVEL_LOW = "Low"
_LEVEL_MEDIUM = "Medium"
_LEVEL_HIGH = "High"


def calculate_rug_risk(
    pair: dict[str, Any],
    age_minutes: float,
) -> dict[str, Any]:
    """
    Calculate a rug / honeypot risk score (0–100) for a new listing.
    Higher score = more suspicious.

    Returns {"score": int, "level": str, "factors": list[str]}.
    """
    score = 0
    factors: list[str] = []

    liquidity_usd = float((pair.get("liquidity") or {}).get("usd") or 0)
    volume_h24 = float((pair.get("volume") or {}).get("h24") or 0)
    fdv = float(pair.get("fdv") or 0)
    info: dict[str, Any] = pair.get("info") or {}
    websites: list = info.get("websites") or []
    socials: list = info.get("socials") or []

    # Rule 1 — low liquidity signals easy rug
    if liquidity_usd < 5_000:
        score += 30
        factors.append(f"Low liquidity (${liquidity_usd:,.0f})")

    # Rule 2 — minimal trading activity
    if volume_h24 < 2_000:
        score += 20
        factors.append(f"Low 24h volume (${volume_h24:,.0f})")

    # Rule 3 — inflated FDV vs locked liquidity
    if liquidity_usd > 0 and fdv > 0:
        ratio = fdv / liquidity_usd
        if ratio > 20:
            score += 20
            factors.append(f"FDV/Liquidity ratio {ratio:.0f}x")

    # Rule 4 — anonymous project (no socials or website)
    if not websites and not socials:
        score += 10
        factors.append("No website or socials")

    # Rule 5 — extremely fresh pair (< 5 minutes old)
    if age_minutes < 5:
        score += 20
        factors.append(f"Very fresh pair ({age_minutes:.1f} min old)")

    score = min(100, score)

    if score < 30:
        level = _LEVEL_LOW
    elif score < 60:
        level = _LEVEL_MEDIUM
    else:
        level = _LEVEL_HIGH

    return {"score": score, "level": level, "factors": factors}


def risk_emoji(score: int) -> str:
    if score < 30:
        return "🟢"
    if score < 60:
        return "🟡"
    return "🔴"
