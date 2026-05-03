from __future__ import annotations

from typing import Any

# Risk Score Scale: 0-100
# - 0-29: LOW risk (green)
# - 30-59: MEDIUM risk (yellow)
# - 60-100: HIGH risk (red)

_LEVEL_LOW = "LOW"
_LEVEL_MEDIUM = "MEDIUM"
_LEVEL_HIGH = "HIGH"


def calculate_risk_score(
    token_data: dict[str, Any],
    dev_data: dict[str, Any],
) -> dict[str, Any]:
    """
    Calculate a 0–100 risk score from token metrics and dev wallet analysis.

    Initial score = 50

    Factors:
    - Liquidity: >5000 → +15, <500 → -20
    - Volume: >5000 → +15, <500 → -15
    - Buys/Sells: buys > sells → +10, sells > buys → -10
    - Price growth: >20% → +10
    - Dev balance: >10 TON → +10, <1 TON → -20
    - Dev activity: mass outgoing → -20

    Returns {"score": int, "level": str, "factors": list[str]}.
    """
    score = 50
    factors: list[str] = []

    # ── Liquidity factor ──────────────────────────────────────────────────────
    liquidity = float(token_data.get("liquidity") or 0)
    if liquidity > 5_000:
        score += 15
        factors.append("✅ Strong liquidity")
    elif liquidity >= 1_000:
        score += 5
        factors.append("➖ Moderate liquidity")
    elif liquidity < 500:
        score -= 20
        factors.append("❌ Critical: low liquidity")

    # ── Volume factor ─────────────────────────────────────────────────────────
    volume = float(token_data.get("volume") or 0)
    if volume > 5_000:
        score += 15
        factors.append("✅ Strong volume")
    elif volume >= 1_000:
        score += 5
        factors.append("➖ Moderate volume")
    elif volume < 500:
        score -= 15
        factors.append("❌ Low volume")

    # ── Buy/Sell ratio ───────────────────────────────────────────────────────
    buys = int(token_data.get("buys") or 0)
    sells = int(token_data.get("sells") or 0)
    total = buys + sells
    if total > 0:
        buy_ratio = buys / total
        if buys > sells:
            score += 10
            factors.append(f"✅ More buys ({buy_ratio:.1%})")
        elif sells > buys:
            score -= 10
            factors.append(f"❌ More sells ({buy_ratio:.1%})")
    else:
        factors.append("➖ No trades yet")

    # ── Price trend (24h change) ──────────────────────────────────────────────
    price_change = float(token_data.get("price_change_h24") or 0)
    if price_change > 20:
        score += 10
        factors.append(f"✅ Strong growth (+{price_change:.1f}%)")
    elif price_change < -10:
        score -= 10
        factors.append(f"❌ Price falling ({price_change:.1f}%)")

    # ── Dev wallet balance ────────────────────────────────────────────────────
    balance = float(dev_data.get("balance") or 0)
    if balance > 10:
        score += 10
        factors.append(f"✅ Healthy dev ({balance:.2f} TON)")
    elif balance < 1:
        score -= 20
        factors.append(f"❌ Critical: low dev balance ({balance:.2f} TON)")
    else:
        factors.append(f"➖ Low dev balance ({balance:.2f} TON)")

    # ── Dev wallet activity ───────────────────────────────────────────────────
    tx_count_24h = int(dev_data.get("tx_count_24h") or 0)
    if tx_count_24h > 5:
        score += 5
        factors.append(f"✅ Dev active ({tx_count_24h} tx/24h)")
    elif tx_count_24h == 0:
        score -= 5
        factors.append("❌ Dev inactive")

    # ── Risk flags (mass transfers, etc) ──────────────────────────────────────
    risk_flags: list[str] = dev_data.get("risk_flags") or []
    for flag in risk_flags:
        if "mass" in flag.lower() or "transfer" in flag.lower():
            score -= 20
            factors.append(f"❌ {flag}")

    # ── Clamp score to 0-100 range ────────────────────────────────────────────
    score = max(0, min(100, score))

    # ── Determine risk level ──────────────────────────────────────────────────
    if score < 30:
        level = _LEVEL_LOW
    elif score < 60:
        level = _LEVEL_MEDIUM
    else:
        level = _LEVEL_HIGH

    return {
        "score": score,
        "level": level,
        "factors": factors,
    }


def risk_emoji(level: str) -> str:
    """Return emoji for risk level."""
    if level == _LEVEL_LOW:
        return "🟢"
    elif level == _LEVEL_MEDIUM:
        return "🟡"
    else:
        return "🔴"
