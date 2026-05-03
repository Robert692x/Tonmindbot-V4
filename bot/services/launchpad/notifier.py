from __future__ import annotations

from html import escape
from typing import Any

from bot.services.launchpad.analyzer import calculate_rug_risk, risk_emoji
from bot.services.launchpad.risk_scoring import risk_emoji as risk_emoji_new
from bot.utils.links import address_link

_DEXSCREENER_BASE = "https://dexscreener.com/ton"
_MAX_SUMMARY_ITEMS = 10


# ── Shared formatters ─────────────────────────────────────────────────────────

def _fmt_usd(v: float) -> str:
    if v >= 1_000_000_000:
        return f"${v / 1_000_000_000:.2f}B"
    if v >= 1_000_000:
        return f"${v / 1_000_000:.2f}M"
    if v >= 1_000:
        return f"${v / 1_000:.1f}K"
    return f"${v:,.0f}"


def _fmt_price(v: float) -> str:
    if v == 0:
        return "$0"
    if v >= 1:
        return f"${v:,.2f}"
    if v >= 0.001:
        return f"${v:.4f}"
    return f"${v:.8f}"


# ── Single listing — full card ────────────────────────────────────────────────

def format_listing(pair: dict[str, Any]) -> str:
    """
    Full HTML card for one new listing.

    Example output:

        🚀 New Listing

        Name: ALGO (ALGO)
        Chain: TON
        Price: $0.0042
        Liquidity: $12.3K
        Volume: $4.5K
        FDV: $420K
        Age: 3.2 min

        Risk: 🔴 High (70/100)

        Factors:
          • Low liquidity ($3,200)
          • No website or socials
          • Very fresh pair (3.2 min old)

        DEX: STON.FI
        Contract:
        <a href="...">EQ...</a>
        Link: <a href="...">DexScreener</a>
    """
    base: dict = pair.get("baseToken") or {}
    name = escape(str(base.get("name") or base.get("symbol") or "Unknown"))
    symbol = escape(str(base.get("symbol") or "?"))
    address = str(base.get("address") or "")

    liquidity = float((pair.get("liquidity") or {}).get("usd") or 0)
    volume_h24 = float((pair.get("volume") or {}).get("h24") or 0)
    fdv = float(pair.get("fdv") or 0)
    price_usd = float(pair.get("priceUsd") or 0)
    pair_address = str(pair.get("pairAddress") or "")
    dex_id = str(pair.get("dexId") or "unknown").upper().replace("-", ".")
    age_minutes = float(pair.get("_age_minutes") or 0)

    risk = calculate_rug_risk(pair, age_minutes)
    score: int = risk["score"]
    level: str = risk["level"]
    factors: list[str] = risk.get("factors") or []

    emoji = risk_emoji(score)
    dex_url = f"{_DEXSCREENER_BASE}/{pair_address}"
    factors_text = "\n".join(f"  • {escape(f)}" for f in factors) if factors else "  None"

    lines: list[str] = [
        "🚀 <b>New Listing</b>",
        "",
        f"Name: <b>{name}</b> ({symbol})",
        "Chain: <b>TON</b>",
        f"Price: {_fmt_price(price_usd)}",
        f"Liquidity: {_fmt_usd(liquidity)}",
        f"Volume: {_fmt_usd(volume_h24)}",
        f"FDV: {_fmt_usd(fdv)}",
        f"Age: {age_minutes:.1f} min",
        "",
        f"Risk: {emoji} <b>{level}</b> ({score}/100)",
        "",
        "Factors:",
        factors_text,
        "",
        f"DEX: {escape(dex_id)}",
    ]

    if address:
        lines.append(f"Contract:\n{address_link(address)}")

    lines.append(f'Link: <a href="{dex_url}">DexScreener</a>')

    return "\n".join(lines)


# ── Summary list — multiple listings ─────────────────────────────────────────

def format_listings_summary(listings: list[dict[str, Any]]) -> str:
    """
    Compact multi-token summary.

    Example output:

        🚀 New Listings (TON) — 3 found

        🔴 MEMECOIN   Liq: $2.1K  Age: 1.4m  Risk: 80
        🟡 NEWTOKEN   Liq: $8.5K  Age: 12.0m  Risk: 50
        🟢 SOLID      Liq: $22K   Age: 18.1m  Risk: 20
    """
    if not listings:
        return (
            "<b>New Listings (TON)</b>\n\n"
            "No new listings in the last 20 minutes."
        )

    sep = "─" * 24
    count = len(listings)
    lines: list[str] = [f"🚀 <b>New Listings (TON)</b> — {count} found\n", sep]

    for pair in listings[:_MAX_SUMMARY_ITEMS]:
        base: dict = pair.get("baseToken") or {}
        symbol = escape(str(base.get("symbol") or "?"))[:12]
        liquidity = float((pair.get("liquidity") or {}).get("usd") or 0)
        age_minutes = float(pair.get("_age_minutes") or 0)
        pair_address = str(pair.get("pairAddress") or "")

        risk = calculate_rug_risk(pair, age_minutes)
        score: int = risk["score"]
        emoji = risk_emoji(score)
        dex_url = f"{_DEXSCREENER_BASE}/{pair_address}"

        lines.append(
            f"{emoji} <b>{symbol}</b>  "
            f"Liq: {_fmt_usd(liquidity)}  "
            f"Age: {age_minutes:.1f}m  "
            f"Risk: {score}  "
            f'<a href="{dex_url}">DEX</a>'
        )

    if count > _MAX_SUMMARY_ITEMS:
        lines.append(f"\n+ {count - _MAX_SUMMARY_ITEMS} more…")

    return "\n".join(lines)


# ── Alert message — single token alert for background notifications ────────────

def format_listing_alert(pair: dict[str, Any]) -> str:
    """
    Short alert card sent to subscribers when a new listing appears.
    """
    base: dict = pair.get("baseToken") or {}
    name = escape(str(base.get("name") or base.get("symbol") or "Unknown"))
    symbol = escape(str(base.get("symbol") or "?"))
    address = str(base.get("address") or "")

    liquidity = float((pair.get("liquidity") or {}).get("usd") or 0)
    volume_h24 = float((pair.get("volume") or {}).get("h24") or 0)
    pair_address = str(pair.get("pairAddress") or "")
    dex_id = str(pair.get("dexId") or "unknown").upper().replace("-", ".")
    age_minutes = float(pair.get("_age_minutes") or 0)

    risk = calculate_rug_risk(pair, age_minutes)
    score: int = risk["score"]
    level: str = risk["level"]
    emoji = risk_emoji(score)
    dex_url = f"{_DEXSCREENER_BASE}/{pair_address}"

    lines: list[str] = [
        f"🚀 <b>New Listing</b>",
        "",
        f"Name: <b>{name}</b> ({symbol})",
        f"Liquidity: {_fmt_usd(liquidity)}",
        f"Volume: {_fmt_usd(volume_h24)}",
        f"Age: {age_minutes:.1f} min",
        "",
        f"Risk: {emoji} <b>{level}</b> ({score}/100)",
        "",
        f"DEX: {escape(dex_id)}",
    ]

    if address:
        lines.append(f"Contract:\n{address_link(address)}")

    lines.append(f'<a href="{dex_url}">Open on DexScreener</a>')

    return "\n".join(lines)


# ── Complete token analysis format ────────────────────────────────────────────

def format_token_analysis(analysis: dict[str, Any]) -> str:
    """
    Format complete token analysis with metrics, signals, dev analysis, and risk.

    Returns full HTML card with all analysis details.
    """
    token = analysis.get("token_info", {})
    signal = analysis.get("signal", {})
    risk = analysis.get("risk", {})
    dev = analysis.get("dev_analysis", {})
    conclusion = analysis.get("conclusion", "")

    symbol = escape(str(token.get("symbol", "?")))
    address = str(token.get("address", ""))
    name = escape(str(token.get("name", "Unknown")))
    price = float(token.get("price", 0))
    liquidity = float(token.get("liquidity", 0))
    volume = float(token.get("volume", 0))
    fdv = float(token.get("fdv", 0))
    buys = int(token.get("buys", 0))
    sells = int(token.get("sells", 0))
    price_change = float(token.get("price_change_h24", 0))

    risk_score = int(risk.get("score", 50))
    risk_level = str(risk.get("level", "MEDIUM"))
    risk_factors = risk.get("factors", [])

    signal_level = str(signal.get("signal", "LOW"))
    signal_indicators = signal.get("indicators", [])
    signal_emoji_val = signal_emoji_new(risk_level)

    dev_balance = float(dev.get("balance", 0))
    dev_tx_24h = int(dev.get("tx_count_24h", 0))
    dev_activity = str(dev.get("activity", "UNKNOWN"))
    dev_flags = dev.get("risk_flags", [])

    # Format buy/sell ratio
    total_trades = buys + sells
    buy_pct = (buys / total_trades * 100) if total_trades > 0 else 0

    lines: list[str] = [
        f"<b>📊 TOKEN ANALYSIS</b>",
        "",
        f"<b>{name}</b> ({symbol})",
        f"Price: {_fmt_price(price)}",
        f"Market Cap: {_fmt_usd(fdv)}",
        f"Liquidity: {_fmt_usd(liquidity)}",
        f"Volume (24h): {_fmt_usd(volume)}",
        "",
        f"Buys/Sells: <b>{buys}</b> / <b>{sells}</b> ({buy_pct:.0f}% buys)",
        f"Price Change (24h): <b>{price_change:+.1f}%</b>",
        "",
        f"<b>Signal: {signal_level}</b>",
        "\n".join(f"  {ind}" for ind in signal_indicators),
        "",
        f"<b>Developer Wallet</b>",
    ]

    if address:
        dex_url = f"{_DEXSCREENER_BASE}/{address}"
        lines.append(f"Address: {address_link(address)}")

    lines.extend([
        f"Balance: <b>{dev_balance:.2f}</b> TON",
        f"Activity: {dev_activity} ({dev_tx_24h} tx/24h)",
    ])

    if dev_flags:
        lines.append("⚠️ Risk Flags:")
        lines.extend(f"  • {flag}" for flag in dev_flags)
    else:
        lines.append("✅ No suspicious activity")

    lines.extend([
        "",
        f"<b>Risk Assessment</b>",
        f"Score: <b>{risk_score}/100</b> {risk_emoji_new(risk_level)} {risk_level}",
        "Factors:",
    ])

    lines.extend(f"  {factor}" for factor in risk_factors)

    lines.extend([
        "",
        "<b>Conclusion</b>",
        conclusion,
    ])

    return "\n".join(lines)
