import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional
import httpx
from config import settings

log = logging.getLogger(__name__)
NANO = 1_000_000_000

KNOWN = {
    "EQCxE6mUtQJKFnGfaROTKOt1lZbDiiX1kCixRv7Nw2Id_sDs": "Binance",
    "EQB3ncyBUTjZUA5EnFKR5_EnOMI9V1tTEAAPaiU71gc4TiUt": "OKX",
}


class TONService:
    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None

    def _get(self) -> httpx.AsyncClient:
        if not self._client or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=settings.TON_API_BASE,
                headers={"X-API-Key": settings.TON_API_KEY},
                timeout=15.0
            )
        return self._client

    async def _req(self, path: str, params: dict = None, retries=3) -> any:
        for i in range(retries):
            try:
                r = await self._get().get(path, params=params)
                r.raise_for_status()
                data = r.json()
                if not data.get("ok"):
                    raise ValueError(data.get("error", "API error"))
                return data.get("result")
            except Exception as e:
                if i < retries - 1:
                    await asyncio.sleep(2 ** i)
                else:
                    raise

    async def get_balance(self, address: str) -> float:
        try:
            result = await self._req("/getAddressBalance", {"address": address})
            return int(result) / NANO
        except Exception as e:
            log.error("Balance error: %s", e)
            return 0.0

    async def get_transactions(self, address: str, limit=10) -> list:
        try:
            result = await self._req("/getTransactions", {"address": address, "limit": limit})
            return result or []
        except Exception as e:
            log.error("Txs error: %s", e)
            return []

    def parse_tx(self, raw: dict) -> dict:
        in_msg = raw.get("in_msg", {})
        value = int(in_msg.get("value", 0)) / NANO
        comment = ""
        md = in_msg.get("msg_data", {})
        if isinstance(md, dict):
            comment = md.get("text", "") or ""
        ts = raw.get("utime", 0)
        date = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%d %b %H:%M") if ts else ""
        return {
            "hash": raw.get("transaction_id", {}).get("hash", ""),
            "from": in_msg.get("source", ""),
            "to": in_msg.get("destination", ""),
            "amount": value,
            "in": value > 0,
            "comment": comment.strip(),
            "date": date,
            "ts": ts,
        }

    async def get_wallet_info(self, address: str) -> dict:
        balance, raw_txs = await asyncio.gather(
            self.get_balance(address),
            self.get_transactions(address, limit=10),
            return_exceptions=True
        )
        if isinstance(balance, Exception):
            balance = 0.0
        if isinstance(raw_txs, Exception):
            raw_txs = []
        txs = [self.parse_tx(t) for t in raw_txs]
        return {"address": address, "balance": balance, "txs": txs}

    async def find_payment(self, to_address: str, memo: str, min_amount: float) -> Optional[dict]:
        try:
            raw_txs = await self.get_transactions(to_address, limit=25)
            for raw in raw_txs:
                tx = self.parse_tx(raw)
                if tx["comment"].upper() == memo.upper() and tx["amount"] >= min_amount * 0.99:
                    return tx
        except Exception as e:
            log.error("find_payment error: %s", e)
        return None

    async def get_whale_txs(self, addresses: list = None) -> list:
        addresses = addresses or list(KNOWN.keys())[:2]
        whales = []
        for addr in addresses:
            try:
                raw_txs = await self.get_transactions(addr, limit=10)
                for raw in raw_txs:
                    tx = self.parse_tx(raw)
                    if tx["amount"] >= settings.WHALE_THRESHOLD_TON:
                        tx["label"] = KNOWN.get(tx["from"]) or KNOWN.get(tx["to"])
                        whales.append(tx)
            except Exception:
                pass
        return whales

    @staticmethod
    def is_valid_address(addr: str) -> bool:
        if not addr:
            return False
        s = addr.strip()
        return (s[:2] in ("EQ", "UQ") and len(s) == 48) or \
               (s.startswith("0:") and len(s) == 66)

    async def get_ton_price(self) -> Optional[float]:
        try:
            async with httpx.AsyncClient(timeout=8.0) as c:
                r = await c.get(
                    "https://api.coingecko.com/api/v3/simple/price",
                    params={"ids": "the-open-network", "vs_currencies": "usd",
                            "include_24hr_change": "true", "include_7d_change": "true",
                            "include_24hr_vol": "true", "include_market_cap": "true"}
                )
                d = r.json().get("the-open-network", {})
                return {
                    "usd": d.get("usd", 0),
                    "change_24h": d.get("usd_24h_change", 0),
                    "change_7d": d.get("usd_7d_change", 0),
                    "change_1h": 0,
                    "volume_24h": d.get("usd_24h_vol", 0),
                    "market_cap": d.get("usd_market_cap", 0),
                }
        except Exception as e:
            log.warning("Price error: %s", e)
            return None


ton_service = TONService()
