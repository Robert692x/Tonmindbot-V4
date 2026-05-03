"""
AI tool definitions and executor for the TON Mind Bot intelligence layer.

Tools follow the OpenAI Responses API flat format:
  {"type": "function", "name": "...", "description": "...", "parameters": {...}}

The ToolExecutor calls the local FastAPI backend (server.py) via httpx,
keeping the AI layer fully decoupled from raw data services.
"""
from __future__ import annotations

import json
import logging
from typing import Any

import httpx

log = logging.getLogger(__name__)

# ── Tool schemas (Responses API flat format) ───────────────────────────────────

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "name": "get_wallet_activity",
        "description": (
            "Fetch a TON wallet's balance, risk level, account status, and recent "
            "transaction history (up to 10 txs with amounts, counterparties, and comments). "
            "Use for any wallet-related question or when the user says 'my wallet'."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "address": {
                    "type": "string",
                    "description": (
                        "TON wallet address (EQ.../UQ...) or the literal string "
                        "'my_wallet' to look up the user's connected wallet."
                    ),
                }
            },
            "required": ["address"],
        },
    },
    {
        "type": "function",
        "name": "get_token_data",
        "description": (
            "Fetch current price, 1h/24h/7d percentage changes, market cap, and "
            "24h trading volume for any cryptocurrency. Use for price questions, "
            "token overviews, or market data requests."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "token": {
                    "type": "string",
                    "description": "Token symbol (e.g. TON, BTC, ETH) or CoinGecko name.",
                }
            },
            "required": ["token"],
        },
    },
    {
        "type": "function",
        "name": "get_swap_activity",
        "description": (
            "Fetch DEX swap pools and trading activity for a token on STON.fi. "
            "Returns pool TVL, 24h volume, and APY. Use for DEX, liquidity, or swap questions."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "token": {
                    "type": "string",
                    "description": "Token symbol to look up in STON.fi pools.",
                }
            },
            "required": ["token"],
        },
    },
    {
        "type": "function",
        "name": "get_whale_activity",
        "description": (
            "Fetch recent large TON transfers (whale movements) above the configured "
            "threshold. Returns transfer amounts, sender/receiver labels, and timestamps. "
            "Use when the user asks 'who is buying', 'whale moves', or 'large transfers'."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "token": {
                    "type": "string",
                    "description": "Token context for the whale search (use 'TON' for native transfers).",
                }
            },
            "required": ["token"],
        },
    },
    {
        "type": "function",
        "name": "get_volume_spike",
        "description": (
            "Detect abnormal volume spikes for a token by comparing 24h trading volume "
            "to market cap (volume/mcap ratio). High ratio signals potential pump, "
            "manipulation, or major news event. Use for volume anomaly questions."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "token": {
                    "type": "string",
                    "description": "Token symbol or name to check for volume spikes.",
                }
            },
            "required": ["token"],
        },
    },
    {
        "type": "function",
        "name": "get_token_risk",
        "description": (
            "Comprehensive risk assessment for a token: volatility, ATH drawdown, "
            "volume/mcap ratio, market cap rank, and liquidity. Returns a risk score "
            "(0–100) and level (Low/Medium/High) with specific risk flags. "
            "Use for risk analysis, safety checks, or due diligence questions."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "token": {
                    "type": "string",
                    "description": "Token symbol or name to assess.",
                }
            },
            "required": ["token"],
        },
    },
]

# Map tool names to backend endpoint patterns
_ENDPOINT_MAP: dict[str, str] = {
    "get_wallet_activity": "/wallet/{address}",
    "get_token_data":      "/token/{token}",
    "get_swap_activity":   "/swap/{token}",
    "get_whale_activity":  "/whales/{token}",
    "get_volume_spike":    "/volume/{token}",
    "get_token_risk":      "/risk/{token}",
}


class ToolExecutor:
    """
    Executes AI-requested tool calls by calling the local FastAPI backend.

    Each tool maps to one HTTP GET endpoint. Errors are returned as structured
    JSON so the AI can acknowledge them without hallucinating data.
    """

    def __init__(self, backend_url: str, *, user_wallet: str | None = None) -> None:
        self.backend_url = backend_url.rstrip("/")
        self.user_wallet = user_wallet
        self._http = httpx.AsyncClient(timeout=20.0)

    async def close(self) -> None:
        await self._http.aclose()

    def _resolve_address(self, address: str) -> str | None:
        cleaned = (address or "").strip()
        if not cleaned or cleaned.lower() in ("my_wallet", "my wallet", "мой кошелек", "мой кошелёк"):
            return self.user_wallet
        return cleaned or None

    async def execute(self, name: str, arguments: dict[str, Any]) -> str:
        """Route a tool call to the correct backend endpoint and return JSON string."""
        try:
            if name == "get_wallet_activity":
                return await self._call_wallet(arguments)
            if name in ("get_token_data", "get_swap_activity",
                        "get_whale_activity", "get_volume_spike", "get_token_risk"):
                return await self._call_token_endpoint(name, arguments)
            return json.dumps({"error": f"Unknown tool: {name}"})
        except Exception as exc:
            log.warning("Tool '%s' failed: %s", name, exc)
            return json.dumps({"error": str(exc)})

    # ── Wallet ─────────────────────────────────────────────────────────────────

    async def _call_wallet(self, args: dict[str, Any]) -> str:
        address = self._resolve_address(args.get("address", ""))
        if not address:
            return json.dumps({
                "error": "No wallet address provided and user has no connected wallet. "
                         "Ask the user to connect a wallet or provide an address."
            })
        return await self._get(f"/wallet/{address}")

    # ── Token / market tools ───────────────────────────────────────────────────

    async def _call_token_endpoint(self, name: str, args: dict[str, Any]) -> str:
        token = (args.get("token") or "").strip()
        if not token:
            return json.dumps({"error": "No token specified."})

        path_tpl = _ENDPOINT_MAP[name]
        path = path_tpl.format(token=token, address=token)
        return await self._get(path)

    # ── HTTP helper ────────────────────────────────────────────────────────────

    async def _get(self, path: str) -> str:
        url = f"{self.backend_url}{path}"
        log.info("Backend call: GET %s", url)
        try:
            resp = await self._http.get(url)
            if resp.status_code == 404:
                return json.dumps({"error": f"Not found: {path}"})
            if resp.status_code == 429:
                return json.dumps({"error": "Data provider rate limit reached. Try again in 60 seconds."})
            resp.raise_for_status()
            data = resp.json()
            log.debug("Backend response: %s → %s", path, str(data)[:200])
            return json.dumps(data)
        except httpx.TimeoutException:
            return json.dumps({"error": "Backend request timed out. Data temporarily unavailable."})
        except httpx.HTTPStatusError as exc:
            return json.dumps({"error": f"Backend error {exc.response.status_code}: {exc.response.text[:200]}"})
        except httpx.RequestError as exc:
            return json.dumps({"error": f"Cannot reach backend at {self.backend_url}. Is the server running?"})
