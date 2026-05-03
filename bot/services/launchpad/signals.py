from __future__ import annotations

import time
from typing import Any

_STRONG_MIN_LIQUIDITY = 1_000.0
_STRONG_MIN_VOLUME = 1_000.0
_STRONG_MIN_FDV = 1_000.0

_SIGNAL_PRICE_MULT = 1.20   # +20%
_SIGNAL_VOLUME_MULT = 1.50  # +50%
_SIGNAL_MIN_LIQUIDITY = 1_000.0

_BASELINE_TTL = 4 * 3600  # seconds

SIGNAL_LOW = "LOW"
SIGNAL_MEDIUM = "MEDIUM"
SIGNAL_HIGH = "HIGH"


class SignalsService:
    """
    Stateful service that tracks per-token baselines (first-seen price/volume)
    and exposes filter_strong_tokens() / detect_early_signals().
    """

    def __init__(self) -> None:
        # address -> {price, volume, ts (monotonic)}
        self._baselines: dict[str, dict[str, float]] = {}

    # ── Strong filter ──────────────────────────────────────────────────────────

    @staticmethod
    def filter_strong_tokens(tokens: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Returns tokens passing ALL quality gates:
          liquidity >= 1000, volume >= 1000, fdv >= 1000, buys > sells.
        """
        result = []
        for t in tokens:
            if (
                float(t.get("liquidity") or 0) >= _STRONG_MIN_LIQUIDITY
                and float(t.get("volume") or 0) >= _STRONG_MIN_VOLUME
                and float(t.get("mcap") or 0) >= _STRONG_MIN_FDV
                and int(t.get("buys") or 0) > int(t.get("sells") or 0)
            ):
                result.append(t)
        return result

    # ── Early signals ──────────────────────────────────────────────────────────

    def detect_early_signals(
        self,
        tokens: list[dict[str, Any]],
    ) -> list[tuple[dict[str, Any], str]]:
        """
        Compare current metrics to first-seen baseline.
        Records baselines for new tokens; on subsequent calls checks growth.

        Returns [(token, level)] where level in (LOW, MEDIUM, HIGH).
        """
        now = time.monotonic()
        result: list[tuple[dict[str, Any], str]] = []

        for t in tokens:
            addr = t.get("address") or t.get("pair") or ""
            if not addr:
                continue

            price = float(t.get("price") or 0)
            volume = float(t.get("volume") or 0)
            liquidity = float(t.get("liquidity") or 0)
            buys = int(t.get("buys") or 0)
            sells = int(t.get("sells") or 0)

            if addr not in self._baselines:
                self._baselines[addr] = {"price": price, "volume": volume, "ts": now}
                continue

            if liquidity < _SIGNAL_MIN_LIQUIDITY:
                continue

            base = self._baselines[addr]
            price_grew = base["price"] > 0 and price >= base["price"] * _SIGNAL_PRICE_MULT
            volume_grew = base["volume"] > 0 and volume >= base["volume"] * _SIGNAL_VOLUME_MULT
            buy_pressure = buys > sells

            matched = sum([price_grew, volume_grew, buy_pressure])
            if matched == 0:
                continue

            level = SIGNAL_LOW if matched == 1 else (SIGNAL_MEDIUM if matched == 2 else SIGNAL_HIGH)
            result.append((t, level))

        return result

    # ── Maintenance ────────────────────────────────────────────────────────────

    def cleanup(self) -> int:
        """Prune baselines older than TTL. Returns count removed."""
        now = time.monotonic()
        expired = [k for k, v in self._baselines.items() if now - v.get("ts", 0) > _BASELINE_TTL]
        for k in expired:
            del self._baselines[k]
        return len(expired)
