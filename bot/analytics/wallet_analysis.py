from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from bot.analytics.network_engine import NetworkReport, analyze_network
from bot.analytics.score_engine import WalletScore, compute_wallet_score
from bot.services.tonapi import TonApiService
from bot.services.wallet_analytics import WalletBehaviorReport, analyze_wallet_behavior
from bot.services.wallet_service import WalletData, WalletService

log = logging.getLogger(__name__)


@dataclass
class FullWalletAnalysis:
    """All wallet intelligence in one place — fetched from real blockchain data."""
    data: WalletData             # raw on-chain: balance, txs, jettons
    behavior: WalletBehaviorReport  # flipper score, risk, AI conclusion
    score: WalletScore           # composite credibility score 0–100
    network: NetworkReport       # connected-address graph


async def full_analysis(address: str, *, tonapi: TonApiService) -> FullWalletAnalysis:
    """Run complete wallet analysis using only real TON blockchain data.

    Executes all three heavy calls in parallel to minimise latency:
      1. WalletService — balance, transactions, jettons
      2. analyze_wallet_behavior — flipper detection, risk scoring, AI text
      3. analyze_network — connected-wallet graph
    """
    wallet_service = WalletService(tonapi)

    data, behavior, network = await asyncio.gather(
        wallet_service.get_wallet_data(address),
        analyze_wallet_behavior(address, tonapi=tonapi, period_days=30),
        analyze_network(address, tonapi=tonapi),
    )

    score = compute_wallet_score(behavior, data.balance.balance_ton)

    return FullWalletAnalysis(
        data=data,
        behavior=behavior,
        score=score,
        network=network,
    )
