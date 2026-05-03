from __future__ import annotations

import logging
from typing import Any

from bot.services.dev_wallet import DevWalletAnalyzer
from bot.services.launchpad.risk_scoring import calculate_risk_score, risk_emoji
from bot.services.launchpad.signal_detector import (
    detect_early_signals,
    detect_strong_tokens,
    signal_emoji,
)

log = logging.getLogger(__name__)


class LaunchpadAnalyzer:
    """
    Unified analyzer for complete token analysis pipeline.

    Combines:
    - Token metrics (price, liquidity, volume, buy/sell)
    - Signal detection (early growth indicators)
    - Strong token filtering (quality criteria)
    - Dev wallet analysis (balance, activity, risk flags)
    - Risk scoring (comprehensive 0-100 system)
    """

    def __init__(self) -> None:
        self.dev_analyzer = DevWalletAnalyzer()

    async def analyze_token(
        self,
        token_data: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Perform complete analysis of a token.

        Input: token_data from DexScreener (with metrics)
        Output: {
            "token_info": {...},
            "signal": {...},
            "is_strong": bool,
            "dev_analysis": {...},
            "risk": {...},
            "conclusion": str,
        }
        """
        token_address = token_data.get("baseToken", {}).get("address", "")
        symbol = token_data.get("baseToken", {}).get("symbol", "?")

        # Step 1: Extract and normalize token metrics
        metrics = self._extract_metrics(token_data)

        # Step 2: Detect signals
        signal = detect_early_signals(metrics)

        # Step 3: Check if token is "strong"
        is_strong = detect_strong_tokens(metrics)

        # Step 4: Analyze dev wallet (if we can fetch it)
        dev_analysis = {}
        if token_address:
            try:
                dev_analysis = await self.dev_analyzer.analyze(token_address)
            except Exception as exc:
                log.warning("Could not analyze dev wallet for %s: %s", symbol, exc)
                dev_analysis = self._default_dev_analysis()

        # Step 5: Calculate risk
        risk = calculate_risk_score(metrics, dev_analysis)

        # Step 6: Generate conclusion
        conclusion = self._generate_conclusion(signal, is_strong, risk, dev_analysis)

        return {
            "token_info": {
                "symbol": symbol,
                "address": token_address,
                "name": token_data.get("baseToken", {}).get("name", "Unknown"),
                "price": float(token_data.get("priceUsd") or 0),
                "liquidity": metrics.get("liquidity", 0),
                "volume": metrics.get("volume", 0),
                "fdv": float(token_data.get("fdv") or 0),
                "buys": metrics.get("buys", 0),
                "sells": metrics.get("sells", 0),
                "price_change_h24": metrics.get("price_change_h24", 0),
            },
            "signal": signal,
            "is_strong": is_strong,
            "dev_analysis": dev_analysis,
            "risk": risk,
            "conclusion": conclusion,
        }

    def _extract_metrics(self, token_data: dict[str, Any]) -> dict[str, Any]:
        """Extract and normalize metrics from DexScreener token data."""
        return {
            "liquidity": float(token_data.get("liquidity", {}).get("usd") or 0),
            "volume": float(token_data.get("volume", {}).get("h24") or 0),
            "buys": int(token_data.get("txns", {}).get("h24", {}).get("buys") or 0),
            "sells": int(token_data.get("txns", {}).get("h24", {}).get("sells") or 0),
            "price_change_h24": float(token_data.get("priceChange", {}).get("h24") or 0),
            "price_change_6h": float(token_data.get("priceChange", {}).get("h6") or 0),
            "price_change_1h": float(token_data.get("priceChange", {}).get("h1") or 0),
        }

    def _default_dev_analysis(self) -> dict[str, Any]:
        """Return default dev analysis when data is unavailable."""
        return {
            "balance": 0.0,
            "tx_count_24h": 0,
            "activity": "UNKNOWN",
            "risk_flags": ["Unable to fetch dev data"],
        }

    def _generate_conclusion(
        self,
        signal: dict[str, Any],
        is_strong: bool,
        risk: dict[str, Any],
        dev_analysis: dict[str, Any],
    ) -> str:
        """Generate a human-readable conclusion from analysis."""
        parts = []

        # Signal level
        if signal["signal"] == "HIGH":
            parts.append("🚀 Strong buy signals detected")
        elif signal["signal"] == "MEDIUM":
            parts.append("📈 Moderate growth indicators")

        # Quality check
        if is_strong:
            parts.append("✅ Meets quality criteria (liquidity, volume, buy pressure)")
        else:
            parts.append("⚠️ Does not meet all quality standards")

        # Risk assessment
        level = risk["level"]
        score = risk["score"]
        if level == "LOW":
            parts.append(f"🟢 Low risk ({score}/100)")
        elif level == "MEDIUM":
            parts.append(f"🟡 Medium risk ({score}/100)")
        else:
            parts.append(f"🔴 High risk ({score}/100)")

        # Dev wallet verdict
        if dev_analysis.get("risk_flags"):
            parts.append("⚠️ Developer wallet shows suspicious activity")
        else:
            parts.append("✅ Developer wallet appears healthy")

        # Final recommendation
        if (
            signal["signal"] in ("HIGH", "MEDIUM")
            and is_strong
            and level in ("LOW", "MEDIUM")
            and not dev_analysis.get("risk_flags")
        ):
            parts.append("\n💡 <b>VERDICT: Promising opportunity</b>")
        elif level == "HIGH" or dev_analysis.get("risk_flags"):
            parts.append("\n⛔ <b>VERDICT: High risk, approach with caution</b>")
        else:
            parts.append("\n➖ <b>VERDICT: Monitor further development</b>")

        return "\n".join(parts)
