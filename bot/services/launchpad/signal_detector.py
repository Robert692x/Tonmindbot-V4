from __future__ import annotations

from typing import Any

# Signal levels
SIGNAL_LOW = "LOW"
SIGNAL_MEDIUM = "MEDIUM"
SIGNAL_HIGH = "HIGH"


def detect_early_signals(token_data: dict[str, Any]) -> dict[str, Any]:
    """
    Detect early growth signals in token data.

    Criteria for signals:
    - price >= first_price * 1.2 (20% growth)
    - volume >= first_volume * 1.5
    - buys > sells
    - liquidity >= 1000

    Returns {"signal": str, "strength": int, "indicators": list[str]}.
    """
    indicators: list[str] = []
    strength = 0

    liquidity = float(token_data.get("liquidity") or 0)
    volume = float(token_data.get("volume") or 0)
    buys = int(token_data.get("buys") or 0)
    sells = int(token_data.get("sells") or 0)
    price_change = float(token_data.get("price_change_h24") or 0)

    # Check liquidity baseline
    if liquidity < 1_000:
        return {
            "signal": SIGNAL_LOW,
            "strength": 0,
            "indicators": ["❌ Insufficient liquidity"],
        }

    # Price growth signal
    if price_change >= 20:
        strength += 3
        indicators.append(f"✅ Strong price growth ({price_change:.1f}%)")
    elif price_change >= 10:
        strength += 2
        indicators.append(f"➖ Moderate growth ({price_change:.1f}%)")
    elif price_change > 0:
        strength += 1
        indicators.append(f"➖ Slight growth ({price_change:.1f}%)")

    # Volume signal
    if volume > 5_000:
        strength += 3
        indicators.append(f"✅ Strong volume (${volume:,.0f})")
    elif volume > 1_500:
        strength += 2
        indicators.append(f"➖ Good volume (${volume:,.0f})")
    elif volume >= 1_000:
        strength += 1
        indicators.append(f"➖ Moderate volume (${volume:,.0f})")

    # Buy/sell dominance
    if buys > 0 and sells > 0:
        total = buys + sells
        buy_ratio = buys / total
        if buy_ratio > 0.65:
            strength += 3
            indicators.append(f"✅ Buying pressure ({buy_ratio:.1%})")
        elif buy_ratio > 0.55:
            strength += 1
            indicators.append(f"➖ Slight buying ({buy_ratio:.1%})")
    elif buys > 0:
        strength += 2
        indicators.append("✅ Only buys, no sells")

    # Determine signal level based on strength
    if strength >= 7:
        signal = SIGNAL_HIGH
    elif strength >= 4:
        signal = SIGNAL_MEDIUM
    else:
        signal = SIGNAL_LOW

    return {
        "signal": signal,
        "strength": strength,
        "indicators": indicators,
    }


def detect_strong_tokens(token_data: dict[str, Any]) -> bool:
    """
    Filter for 'strong' tokens based on quality criteria.

    Strong token requirements:
    - liquidity >= 1000
    - volume >= 1000
    - fdv >= 1000
    - buys > sells

    Returns True if token meets all criteria.
    """
    liquidity = float(token_data.get("liquidity") or 0)
    volume = float(token_data.get("volume") or 0)
    fdv = float(token_data.get("fdv") or 0)
    buys = int(token_data.get("buys") or 0)
    sells = int(token_data.get("sells") or 0)

    return (
        liquidity >= 1_000
        and volume >= 1_000
        and fdv >= 1_000
        and buys > sells
    )


def signal_emoji(signal: str) -> str:
    """Return emoji for signal level."""
    if signal == SIGNAL_HIGH:
        return "🚀"
    elif signal == SIGNAL_MEDIUM:
        return "📈"
    else:
        return "➖"
