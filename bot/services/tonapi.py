from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import aiohttp

from bot.services.cache import CacheService
from bot.services.i18n import get_text
from config import Settings

log = logging.getLogger(__name__)
NANO = 1_000_000_000
ADDRESS_RE = re.compile(r"\b(?:EQ|UQ)[A-Za-z0-9_-]{46}\b|\b0:[a-fA-F0-9]{64}\b")


@dataclass(slots=True)
class TransactionRecord:
    direction: str
    amount_ton: float
    timestamp: datetime
    counterparty: str
    tx_hash: str
    comment: str | None = None


@dataclass(slots=True)
class WalletRisk:
    level: str
    reasons: list[str]


@dataclass(slots=True)
class JettonHolding:
    symbol: str
    balance: float
    jetton_address: str
    name: str
    is_algo: bool
    verification: str


@dataclass(slots=True)
class WalletReport:
    address: str
    balance_ton: float
    last_activity: datetime | None
    transactions: list[TransactionRecord]
    risk: WalletRisk
    portfolio: list[JettonHolding]
    algo_balance: float


@dataclass(slots=True)
class WhaleTransfer:
    tx_hash: str
    amount_ton: float
    timestamp: datetime
    from_address: str
    to_address: str
    source_label: str | None = None
    destination_label: str | None = None


@dataclass(slots=True)
class PaymentMatch:
    tx_hash: str
    amount_ton: float
    timestamp: datetime
    sender_address: str


class TonApiService:
    def __init__(self, settings: Settings, cache: CacheService) -> None:
        self.settings = settings
        self.cache = cache
        self._client = aiohttp.ClientSession(
            base_url=settings.TON_API_BASE,
            timeout=aiohttp.ClientTimeout(total=settings.REQUEST_TIMEOUT_SECONDS),
        )
        self._watch_labels = {
            "EQCxE6mUtQJKFnGfaROTKOt1lZbDiiX1kCixRv7Nw2Id_sDs": "Binance",
            "EQB3ncyBUTjZUA5EnFKR5_EnOMI9V1tTEAAPaiU71gc4TiUt": "OKX",
        }
        self._algo_raw_address: str | None = None

    async def close(self) -> None:
        await self._client.close()

    @staticmethod
    def is_probable_address(value: str) -> bool:
        return bool(ADDRESS_RE.fullmatch(value.strip()))

    @staticmethod
    def extract_wallet_address(text: str) -> str | None:
        match = ADDRESS_RE.search(text)
        return match.group(0) if match else None

    async def _request(self, path: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        headers = {}
        if self.settings.TON_API_KEY:
            headers["Authorization"] = f"Bearer {self.settings.TON_API_KEY}"

        async with self._client.get(path, params=params, headers=headers) as response:
            if response.status == 401 and headers:
                async with self._client.get(path, params=params) as retry_response:
                    retry_response.raise_for_status()
                    return await retry_response.json()
            response.raise_for_status()
            return await response.json()

    @staticmethod
    def _from_unix(timestamp: int | None) -> datetime | None:
        if not timestamp:
            return None
        return datetime.fromtimestamp(timestamp, tz=timezone.utc)

    @staticmethod
    def _extract_address(node: Any) -> str:
        if isinstance(node, dict):
            address = node.get("address")
            if isinstance(address, str):
                return address
        if isinstance(node, str):
            return node
        return "unknown"

    def _extract_comment(self, node: Any) -> str | None:
        if isinstance(node, dict):
            for key in ("comment", "text", "memo"):
                value = node.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
            for value in node.values():
                comment = self._extract_comment(value)
                if comment:
                    return comment
        if isinstance(node, list):
            for item in node:
                comment = self._extract_comment(item)
                if comment:
                    return comment
        return None

    def _parse_transaction(self, wallet_address: str, payload: dict[str, Any]) -> TransactionRecord | None:
        wallet_address = wallet_address.strip()
        out_messages = payload.get("out_msgs") or []
        if out_messages:
            amount = sum(int(message.get("value", 0) or 0) for message in out_messages) / NANO
            counterparty = self._extract_address(out_messages[0].get("destination"))
            comment = None
            for message in out_messages:
                comment = self._extract_comment(message.get("decoded_body"))
                if comment:
                    break
            if not comment:
                comment = self._extract_comment(payload.get("in_msg"))
            return TransactionRecord(
                direction="OUT",
                amount_ton=amount,
                timestamp=self._from_unix(payload.get("utime")) or datetime.now(timezone.utc),
                counterparty=counterparty,
                tx_hash=payload["hash"],
                comment=comment,
            )

        in_message = payload.get("in_msg") or {}
        destination = self._extract_address(in_message.get("destination"))
        source = self._extract_address(in_message.get("source"))
        amount = int(in_message.get("value", 0) or 0) / NANO
        if destination != wallet_address and source == wallet_address:
            direction = "OUT"
            counterparty = destination
        else:
            direction = "IN"
            counterparty = source

        return TransactionRecord(
            direction=direction,
            amount_ton=amount,
            timestamp=self._from_unix(payload.get("utime")) or datetime.now(timezone.utc),
            counterparty=counterparty,
            tx_hash=payload["hash"],
            comment=self._extract_comment(in_message.get("decoded_body")) or self._extract_comment(in_message),
        )

    async def _ensure_algo_raw_address(self) -> str | None:
        if self._algo_raw_address is not None:
            return self._algo_raw_address
        try:
            metadata = await self.get_jetton_metadata(self.settings.ALGO_JETTON_ADDRESS)
            self._algo_raw_address = metadata.get("metadata", {}).get("address")
        except Exception as exc:
            log.warning("Unable to resolve ALGO raw jetton address: %s", exc)
            self._algo_raw_address = None
        return self._algo_raw_address

    def _build_risk(self, transactions: list[TransactionRecord]) -> WalletRisk:
        if not transactions:
            return WalletRisk(level="low", reasons=["risk_no_recent"])

        reasons: list[str] = []
        outgoing = [tx for tx in transactions if tx.direction == "OUT"]
        incoming = [tx for tx in transactions if tx.direction == "IN"]
        unique_counterparties = {tx.counterparty for tx in transactions if tx.counterparty != "unknown"}

        if len(transactions) >= 5:
            reasons.append("risk_high_activity")
        if len(unique_counterparties) >= 4:
            reasons.append("risk_many_counterparties")
        if outgoing and sum(tx.amount_ton for tx in outgoing) > max(sum(tx.amount_ton for tx in incoming), 0.1) * 2:
            reasons.append("risk_outflows_exceed")
        if any(tx.amount_ton < 0.05 for tx in incoming):
            reasons.append("risk_dust_inbound")

        if len(reasons) >= 3:
            level = "high"
        elif reasons:
            level = "medium"
        else:
            reasons.append("risk_clean")
            level = "low"
        return WalletRisk(level=level, reasons=reasons)

    async def get_jetton_metadata(self, jetton_address: str) -> dict[str, Any]:
        cache_key = f"jetton:meta:{jetton_address}"
        cached = await self.cache.get_json(cache_key)
        if cached:
            return cached
        payload = await self._request(f"/v2/jettons/{jetton_address}")
        await self.cache.set_json(cache_key, payload, self.settings.CACHE_TTL_LEADERBOARD_SECONDS)
        return payload

    async def get_jetton_holders(self, jetton_address: str, *, limit: int = 10) -> dict[str, Any]:
        return await self._request(f"/v2/jettons/{jetton_address}/holders", params={"limit": limit})

    async def get_wallet_portfolio(self, address: str, *, limit: int = 5) -> list[JettonHolding]:
        normalized = address.strip()
        cache_key = f"portfolio:{normalized}:{limit}"
        cached = await self.cache.get_json(cache_key)
        if cached:
            return [JettonHolding(**item) for item in cached]

        algo_raw_address = await self._ensure_algo_raw_address()
        payload = await self._request(f"/v2/accounts/{normalized}/jettons")
        portfolio: list[JettonHolding] = []
        for item in payload.get("balances", []):
            jetton = item.get("jetton", {}) or {}
            wallet_address = item.get("wallet_address", {}) or {}
            raw_balance = int(item.get("balance", 0) or 0)
            decimals = int(jetton.get("decimals", 9) or 9)
            balance = raw_balance / (10 ** decimals)
            if balance <= 0:
                continue
            if wallet_address.get("is_scam") or jetton.get("verification") == "blacklist":
                continue
            symbol = (jetton.get("symbol") or jetton.get("name") or "").strip()
            if not symbol:
                continue
            jetton_address = jetton.get("address", "")
            portfolio.append(
                JettonHolding(
                    symbol=symbol,
                    balance=balance,
                    jetton_address=jetton_address,
                    name=jetton.get("name", symbol),
                    is_algo=jetton_address == algo_raw_address or jetton_address == self.settings.ALGO_JETTON_ADDRESS,
                    verification=str(jetton.get("verification", "none")),
                )
            )

        portfolio.sort(key=lambda holding: holding.balance, reverse=True)
        portfolio = portfolio[:limit]
        await self.cache.set_json(
            cache_key,
            [
                {
                    "symbol": holding.symbol,
                    "balance": holding.balance,
                    "jetton_address": holding.jetton_address,
                    "name": holding.name,
                    "is_algo": holding.is_algo,
                    "verification": holding.verification,
                }
                for holding in portfolio
            ],
            self.settings.CACHE_TTL_PORTFOLIO_SECONDS,
        )
        return portfolio

    async def get_wallet_report(self, address: str, *, limit: int = 5) -> WalletReport:
        normalized = address.strip()
        cache_key = f"wallet:{normalized}:{limit}"
        cached = await self.cache.get_json(cache_key)
        if cached:
            return WalletReport(
                address=cached["address"],
                balance_ton=cached["balance_ton"],
                last_activity=self._from_unix(cached["last_activity"]),
                transactions=[
                    TransactionRecord(
                        direction=tx["direction"],
                        amount_ton=tx["amount_ton"],
                        timestamp=self._from_unix(tx["timestamp"]) or datetime.now(timezone.utc),
                        counterparty=tx["counterparty"],
                        tx_hash=tx["tx_hash"],
                        comment=tx.get("comment"),
                    )
                    for tx in cached["transactions"]
                ],
                risk=WalletRisk(level=cached["risk"]["level"], reasons=list(cached["risk"]["reasons"])),
                portfolio=[JettonHolding(**item) for item in cached.get("portfolio", [])],
                algo_balance=float(cached.get("algo_balance", 0.0) or 0.0),
            )

        account, transactions, portfolio = await asyncio.gather(
            self._request(f"/v2/accounts/{normalized}"),
            self._request(f"/v2/blockchain/accounts/{normalized}/transactions", params={"limit": limit}),
            self.get_wallet_portfolio(normalized, limit=5),
        )
        parsed_transactions = [
            tx
            for tx in (self._parse_transaction(normalized, item) for item in transactions.get("transactions", []))
            if tx is not None
        ]
        algo_balance = next((holding.balance for holding in portfolio if holding.is_algo), 0.0)
        report = WalletReport(
            address=account["address"],
            balance_ton=int(account.get("balance", 0) or 0) / NANO,
            last_activity=self._from_unix(account.get("last_activity")),
            transactions=parsed_transactions,
            risk=self._build_risk(parsed_transactions),
            portfolio=portfolio,
            algo_balance=algo_balance,
        )
        await self.cache.set_json(
            cache_key,
            {
                "address": report.address,
                "balance_ton": report.balance_ton,
                "last_activity": int(report.last_activity.timestamp()) if report.last_activity else None,
                "transactions": [
                    {
                        "direction": tx.direction,
                        "amount_ton": tx.amount_ton,
                        "timestamp": int(tx.timestamp.timestamp()),
                        "counterparty": tx.counterparty,
                        "tx_hash": tx.tx_hash,
                        "comment": tx.comment,
                    }
                    for tx in report.transactions
                ],
                "risk": {"level": report.risk.level, "reasons": report.risk.reasons},
                "portfolio": [
                    {
                        "symbol": holding.symbol,
                        "balance": holding.balance,
                        "jetton_address": holding.jetton_address,
                        "name": holding.name,
                        "is_algo": holding.is_algo,
                        "verification": holding.verification,
                    }
                    for holding in report.portfolio
                ],
                "algo_balance": report.algo_balance,
            },
            self.settings.CACHE_TTL_WALLET_SECONDS,
        )
        return report

    async def get_pnl_transactions(
        self,
        address: str,
        *,
        limit: int = 200,
    ) -> list[tuple[TransactionRecord, float]]:
        """Fetch up to `limit` transactions for PnL analysis.

        Returns list of (TransactionRecord, fee_ton) tuples, deduplicated by hash.
        fee_ton is total_fees from the chain payload (nanoton → TON).
        """
        cache_key = f"pnl_txs:{address.strip()}:{limit}"
        cached = await self.cache.get_json(cache_key)
        if cached:
            return [
                (
                    TransactionRecord(
                        direction=item["direction"],
                        amount_ton=item["amount_ton"],
                        timestamp=self._from_unix(item["timestamp"]) or datetime.now(timezone.utc),
                        counterparty=item["counterparty"],
                        tx_hash=item["tx_hash"],
                        comment=item.get("comment"),
                    ),
                    item["fee_ton"],
                )
                for item in cached
            ]

        payload = await self._request(
            f"/v2/blockchain/accounts/{address.strip()}/transactions",
            params={"limit": limit},
        )

        seen: set[str] = set()
        result: list[tuple[TransactionRecord, float]] = []
        for item in payload.get("transactions", []):
            tx_hash = item.get("hash", "")
            if not tx_hash or tx_hash in seen:
                continue
            seen.add(tx_hash)

            fee_ton = int(item.get("total_fees", 0) or 0) / NANO
            record = self._parse_transaction(address.strip(), item)
            if record is not None:
                result.append((record, fee_ton))

        await self.cache.set_json(
            cache_key,
            [
                {
                    "direction": r.direction,
                    "amount_ton": r.amount_ton,
                    "timestamp": int(r.timestamp.timestamp()),
                    "counterparty": r.counterparty,
                    "tx_hash": r.tx_hash,
                    "comment": r.comment,
                    "fee_ton": fee,
                }
                for r, fee in result
            ],
            self.settings.CACHE_TTL_WALLET_SECONDS,
        )
        return result

    async def get_raw_transactions(
        self,
        address: str,
        *,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Return raw API transaction dicts for use by the alerts normalizer.

        Not cached — always reflects the latest on-chain state.
        """
        try:
            payload = await self._request(
                f"/v2/blockchain/accounts/{address.strip()}/transactions",
                params={"limit": limit},
            )
        except Exception as exc:
            log.warning("get_raw_transactions failed for %s: %s", address, exc)
            return []
        return list(payload.get("transactions", []))

    async def get_latest_transactions(
        self, address: str, *, limit: int = 10
    ) -> list[TransactionRecord]:
        """Fetch the most recent transactions for wallet monitoring. Not cached."""
        try:
            payload = await self._request(
                f"/v2/blockchain/accounts/{address.strip()}/transactions",
                params={"limit": limit},
            )
        except Exception as exc:
            log.warning("get_latest_transactions failed for %s: %s", address, exc)
            return []

        seen: set[str] = set()
        result: list[TransactionRecord] = []
        for item in payload.get("transactions", []):
            tx_hash = item.get("hash", "")
            if not tx_hash or tx_hash in seen:
                continue
            seen.add(tx_hash)
            record = self._parse_transaction(address.strip(), item)
            if record is not None:
                result.append(record)
        return result

    async def _get_watch_wallet_transactions(self, address: str, limit: int) -> list[dict[str, Any]]:
        payload = await self._request(f"/v2/blockchain/accounts/{address}/transactions", params={"limit": limit})
        return list(payload.get("transactions", []))

    async def get_recent_whales(self, *, limit_per_wallet: int = 8) -> list[WhaleTransfer]:
        cache_key = f"whales:{limit_per_wallet}:{self.settings.WHALE_THRESHOLD_TON}"
        cached = await self.cache.get_json(cache_key)
        if cached:
            return [
                WhaleTransfer(
                    tx_hash=item["tx_hash"],
                    amount_ton=item["amount_ton"],
                    timestamp=self._from_unix(item["timestamp"]) or datetime.now(timezone.utc),
                    from_address=item["from_address"],
                    to_address=item["to_address"],
                    source_label=item.get("source_label"),
                    destination_label=item.get("destination_label"),
                )
                for item in cached
            ]

        tasks = [self._get_watch_wallet_transactions(address, limit_per_wallet) for address in self.settings.WHALE_WATCH_ADDRESSES]
        raw_batches = await asyncio.gather(*tasks, return_exceptions=True)

        whales: dict[str, WhaleTransfer] = {}
        for batch in raw_batches:
            if isinstance(batch, Exception):
                log.warning("Whale scan batch failed: %s", batch)
                continue
            for payload in batch:
                transaction = self._parse_transaction(self._extract_address(payload.get("account")), payload)
                if transaction is None or transaction.amount_ton < self.settings.WHALE_THRESHOLD_TON:
                    continue
                in_message = payload.get("in_msg") or {}
                transfer = WhaleTransfer(
                    tx_hash=payload["hash"],
                    amount_ton=transaction.amount_ton,
                    timestamp=transaction.timestamp,
                    from_address=self._extract_address(in_message.get("source")),
                    to_address=self._extract_address(in_message.get("destination")),
                    source_label=self._watch_labels.get(self._extract_address(in_message.get("source"))),
                    destination_label=self._watch_labels.get(self._extract_address(in_message.get("destination"))),
                )
                whales[transfer.tx_hash] = transfer

        result = sorted(whales.values(), key=lambda item: item.timestamp, reverse=True)
        await self.cache.set_json(
            cache_key,
            [
                {
                    "tx_hash": item.tx_hash,
                    "amount_ton": item.amount_ton,
                    "timestamp": int(item.timestamp.timestamp()),
                    "from_address": item.from_address,
                    "to_address": item.to_address,
                    "source_label": item.source_label,
                    "destination_label": item.destination_label,
                }
                for item in result
            ],
            self.settings.CACHE_TTL_WHALES_SECONDS,
        )
        return result

    async def find_payment_transaction(
        self,
        receiving_wallet: str,
        comment: str,
        minimum_amount_ton: float,
    ) -> PaymentMatch | None:
        payload = await self._request(
            f"/v2/blockchain/accounts/{receiving_wallet}/transactions",
            params={"limit": 50},
        )
        for transaction in payload.get("transactions", []):
            in_message = transaction.get("in_msg") or {}
            destination = self._extract_address(in_message.get("destination"))
            amount_ton = int(in_message.get("value", 0) or 0) / NANO
            tx_comment = self._extract_comment(in_message.get("decoded_body")) or self._extract_comment(in_message)
            if destination != receiving_wallet:
                continue
            if amount_ton + 1e-9 < minimum_amount_ton:
                continue
            if not tx_comment or tx_comment.strip().casefold() != comment.strip().casefold():
                continue
            return PaymentMatch(
                tx_hash=transaction["hash"],
                amount_ton=amount_ton,
                timestamp=self._from_unix(transaction.get("utime")) or datetime.now(timezone.utc),
                sender_address=self._extract_address(in_message.get("source")),
            )
        return None
