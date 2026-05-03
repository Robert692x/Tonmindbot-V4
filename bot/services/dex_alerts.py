from __future__ import annotations

import logging

from bot.utils.links import address_link

log = logging.getLogger(__name__)

_ALERT_STEP = 1_000.0
_INITIAL_THRESHOLD = 1_000.0

# token_address -> last mcap milestone (multiple of _ALERT_STEP) that triggered an alert.
# In-memory only; resets on process restart so the first cycle bootstraps cleanly.
dex_alerts: dict[str, float] = {}


async def process_dex_alerts(tokens: list[dict]) -> list[str]:
    """Return HTML alert messages for tokens that crossed a new +1000 mcap milestone."""
    messages: list[str] = []

    for token in tokens:
        mcap = token["mcap"]
        if mcap < _INITIAL_THRESHOLD:
            continue

        address = token["address"]
        last_milestone = dex_alerts.get(address, 0.0)

        if mcap >= last_milestone + _ALERT_STEP:
            new_milestone = (mcap // _ALERT_STEP) * _ALERT_STEP
            dex_alerts[address] = new_milestone
            messages.append(_build_alert_message(token))
            log.debug(
                "DEX alert: %s  mcap=%.0f  milestone=%.0f",
                token["symbol"], mcap, new_milestone,
            )

    return messages


# ── Formatting ────────────────────────────────────────────────────────────────

def _fmt_price(value: float) -> str:
    if value == 0:
        return "$0"
    if value >= 1:
        return f"${value:,.2f}"
    if value >= 0.001:
        return f"${value:.4f}"
    return f"${value:.8f}"


def _fmt_usd(value: float) -> str:
    if value >= 1_000_000_000:
        return f"${value / 1_000_000_000:.2f}B"
    if value >= 1_000_000:
        return f"${value / 1_000_000:.2f}M"
    if value >= 1_000:
        return f"${value / 1_000:.1f}K"
    return f"${value:,.0f}"


def _build_alert_message(token: dict) -> str:
    return (
        "<b>DEX ALERT</b>\n\n"
        f"Token: <b>{token['symbol']}</b>\n"
        f"Price: {_fmt_price(token['price'])}\n\n"
        f"Market Cap: {_fmt_usd(token['mcap'])}\n"
        f"Liquidity: {_fmt_usd(token['liquidity'])}\n"
        f"Volume: {_fmt_usd(token['volume'])}\n\n"
        f"Рост: <b>+{int(_ALERT_STEP):,}</b>\n\n"
        f"Address:\n{address_link(token['address'])}\n\n"
        f"Dex:\nhttps://dexscreener.com/ton/{token['pair']}"
    )
