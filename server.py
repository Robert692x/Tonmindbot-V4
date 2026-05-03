"""
TON Mind Bot — FastAPI blockchain intelligence backend.

Exposes data endpoints consumed by the AI tool executor.
Each endpoint fetches real on-chain / market data and returns structured JSON.

Run standalone: python server.py
Or launched automatically by main.py as a background asyncio task.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

import aiohttp
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from config import get_settings

log = logging.getLogger(__name__)
NANO = 1_000_000_000

# ── Shared HTTP session ────────────────────────────────────────────────────────

_http: aiohttp.ClientSession | None = None


def _get_http() -> aiohttp.ClientSession:
    if _http is None:
        raise RuntimeError("HTTP session not initialized — server not started properly")
    return _http


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _http
    settings = get_settings()
    timeout = aiohttp.ClientTimeout(total=settings.REQUEST_TIMEOUT_SECONDS)
    headers = {"Accept": "application/json", "User-Agent": "TONMindBot/1.0"}
    _http = aiohttp.ClientSession(timeout=timeout, headers=headers)
    log.info("Backend HTTP session opened")
    yield
    if _http:
        await _http.close()
    log.info("Backend HTTP session closed")


app = FastAPI(
    title="TON Mind Bot Backend",
    description="Blockchain intelligence data layer for AI tool execution",
    version="2.0.0",
    lifespan=lifespan,
)


# ── Internal helpers ───────────────────────────────────────────────────────────

async def _tonapi(path: str, params: dict[str, Any] | None = None) -> dict:
    settings = get_settings()
    headers: dict[str, str] = {}
    if settings.TON_API_KEY:
        headers["Authorization"] = f"Bearer {settings.TON_API_KEY}"
    url = f"{settings.TON_API_BASE}{path}"
    try:
        async with _get_http().get(url, params=params, headers=headers) as resp:
            if resp.status == 404:
                raise HTTPException(status_code=404, detail="Address not found on TON blockchain")
            if resp.status == 401:
                # Retry without auth key (public endpoint)
                async with _get_http().get(url, params=params) as retry:
                    retry.raise_for_status()
                    return await retry.json()
            resp.raise_for_status()
            return await resp.json()
    except HTTPException:
        raise
    except aiohttp.ClientError as exc:
        raise HTTPException(status_code=502, detail=f"TON API unreachable: {exc}") from exc


async def _coingecko(path: str, params: dict[str, Any] | None = None) -> Any:
    settings = get_settings()
    url = f"{settings.COINGECKO_API_BASE}{path}"
    try:
        async with _get_http().get(url, params=params) as resp:
            if resp.status == 429:
                raise HTTPException(status_code=429, detail="CoinGecko rate limit hit — try again in 60s")
            resp.raise_for_status()
            return await resp.json()
    except HTTPException:
        raise
    except aiohttp.ClientError as exc:
        raise HTTPException(status_code=502, detail=f"CoinGecko unreachable: {exc}") from exc


async def _resolve_coin_id(token: str) -> str:
    """Resolve a token symbol/name to a CoinGecko coin ID."""
    # Direct match attempt first (e.g. "the-open-network")
    try:
        data = await _coingecko(
            "/coins/markets",
            {"vs_currency": "usd", "ids": token.lower(), "per_page": 1},
        )
        if data:
            return data[0]["id"]
    except HTTPException:
        pass

    # Fall back to search
    search = await _coingecko("/search", {"query": token})
    coins = (search or {}).get("coins", [])
    if not coins:
        raise HTTPException(status_code=404, detail=f"Token '{token}' not found on CoinGecko")
    return coins[0]["id"]


# ── Endpoints ──────────────────────────────────────────────────────────────────

@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "ton-mind-backend"}


@app.get("/wallet/{address}")
async def get_wallet(address: str) -> dict:
    """
    Wallet overview: balance, status, risk level, and recent transactions.
    Calls tonapi.io v2.
    """
    try:
        account, txs_data = await _tonapi(f"/v2/accounts/{address}"), None
        try:
            txs_data = await _tonapi(
                f"/v2/blockchain/accounts/{address}/transactions",
                {"limit": 15, "sort_order": "desc"},
            )
        except HTTPException:
            txs_data = {}
    except HTTPException:
        raise
    except Exception as exc:
        log.warning("Wallet fetch error %s: %s", address, exc)
        raise HTTPException(status_code=502, detail=str(exc))

    balance_ton = account.get("balance", 0) / NANO

    transactions: list[dict] = []
    for tx in (txs_data or {}).get("transactions", [])[:15]:
        in_msg = tx.get("in_msg") or {}
        out_msgs = tx.get("out_msgs") or []

        if in_msg.get("value", 0) > 0:
            body = in_msg.get("decoded_body") or {}
            transactions.append({
                "direction": "IN",
                "amount_ton": round(in_msg["value"] / NANO, 4),
                "counterparty": (in_msg.get("source") or {}).get("address", "unknown"),
                "comment": body.get("text") if isinstance(body, dict) else None,
                "timestamp": tx.get("utime"),
            })

        for msg in out_msgs[:1]:
            body = msg.get("decoded_body") or {}
            transactions.append({
                "direction": "OUT",
                "amount_ton": round((msg.get("value") or 0) / NANO, 4),
                "counterparty": (msg.get("destination") or {}).get("address", "unknown"),
                "comment": body.get("text") if isinstance(body, dict) else None,
                "timestamp": tx.get("utime"),
            })

    # Risk heuristics
    risk_level = "Low"
    risk_flags: list[str] = []
    if balance_ton > 100_000:
        risk_flags.append("Whale wallet — balance > 100k TON")
        risk_level = "High"
    elif balance_ton < 0.05:
        risk_flags.append("Dust wallet — near-zero balance")
    tx_count = account.get("transactions_count", 0)
    if tx_count < 3:
        risk_flags.append("Very few transactions — new or inactive wallet")
    if account.get("status") not in ("active", "nonexist", None):
        risk_flags.append(f"Unusual account status: {account.get('status')}")

    if risk_flags and risk_level == "Low":
        risk_level = "Medium" if len(risk_flags) == 1 else "High"

    return {
        "address": address,
        "balance_ton": round(balance_ton, 4),
        "status": account.get("status", "unknown"),
        "transaction_count": tx_count,
        "risk_level": risk_level,
        "risk_flags": risk_flags,
        "recent_transactions": transactions[:10],
    }


@app.get("/token/{token}")
async def get_token(token: str) -> dict:
    """
    Token price, market cap, 24h/1h change, and volume.
    Calls CoinGecko markets endpoint.
    """
    coin_id = await _resolve_coin_id(token)
    data = await _coingecko(
        "/coins/markets",
        {
            "vs_currency": "usd",
            "ids": coin_id,
            "per_page": 1,
            "price_change_percentage": "1h,24h,7d",
        },
    )
    if not data:
        raise HTTPException(status_code=404, detail=f"No market data for '{token}'")

    t = data[0]
    return {
        "name": t["name"],
        "symbol": (t.get("symbol") or "").upper(),
        "coin_id": coin_id,
        "price_usd": t.get("current_price"),
        "change_1h_pct": t.get("price_change_percentage_1h_in_currency"),
        "change_24h_pct": t.get("price_change_percentage_24h"),
        "change_7d_pct": t.get("price_change_percentage_7d_in_currency"),
        "market_cap_usd": t.get("market_cap"),
        "volume_24h_usd": t.get("total_volume"),
        "ath_usd": t.get("ath"),
        "market_cap_rank": t.get("market_cap_rank"),
    }


@app.get("/swap/{token}")
async def get_swap_activity(token: str) -> dict:
    """
    DEX swap activity for a token from STON.fi pools.
    Returns matching pool stats and recent volume.
    """
    settings = get_settings()
    swaps: list[dict] = []
    error: str | None = None

    try:
        pool_url = f"{settings.STON_API_BASE}/v1/pools"
        async with _get_http().get(pool_url) as resp:
            resp.raise_for_status()
            pools_raw = await resp.json()

        token_lower = token.lower()
        pool_list = (pools_raw or {}).get("pool_list", [])

        for pool in pool_list:
            t0 = (pool.get("token0_metadata") or {}).get("symbol", "").lower()
            t1 = (pool.get("token1_metadata") or {}).get("symbol", "").lower()
            name0 = (pool.get("token0_metadata") or {}).get("display_name", "").lower()
            name1 = (pool.get("token1_metadata") or {}).get("display_name", "").lower()

            if token_lower in (t0, t1, name0, name1):
                swaps.append({
                    "pool_address": pool.get("address", "")[:20] + "…",
                    "pair": f"{(pool.get('token0_metadata') or {}).get('symbol', '?')}"
                            f"/{(pool.get('token1_metadata') or {}).get('symbol', '?')}",
                    "tvl_usd": pool.get("lp_total_supply_usd"),
                    "volume_24h_usd": pool.get("volume_24h_usd"),
                    "apy_1d_pct": pool.get("apy_1d"),
                })

    except aiohttp.ClientError as exc:
        log.warning("STON.fi unavailable for %s: %s", token, exc)
        error = "STON.fi DEX data temporarily unavailable"

    return {
        "token": token,
        "source": "ston.fi",
        "pool_count": len(swaps),
        "pools": swaps[:8],
        "error": error,
    }


@app.get("/whales/{token}")
async def get_whale_activity(token: str) -> dict:
    """
    Large TON transfers (whale movements) above the configured threshold.
    When token == 'TON', looks at native TON events; otherwise searches account events.
    """
    settings = get_settings()
    threshold = settings.WHALE_THRESHOLD_TON
    whales: list[dict] = []
    error: str | None = None

    try:
        data = await _tonapi("/v2/events", {"limit": 100, "subject_only": "false"})
        events = (data or {}).get("events", [])

        for evt in events:
            for action in evt.get("actions", []):
                if action.get("type") != "TonTransfer":
                    continue
                details = action.get("TonTransfer") or {}
                amount = (details.get("amount") or 0) / NANO
                if amount < threshold:
                    continue
                sender = details.get("sender") or {}
                recipient = details.get("recipient") or {}
                whales.append({
                    "amount_ton": round(amount, 2),
                    "from_address": sender.get("address", "unknown")[:20] + "…",
                    "from_label": sender.get("name"),
                    "to_address": recipient.get("address", "unknown")[:20] + "…",
                    "to_label": recipient.get("name"),
                    "timestamp": evt.get("timestamp"),
                })
    except HTTPException as exc:
        error = exc.detail
    except Exception as exc:
        log.warning("Whale activity error for %s: %s", token, exc)
        error = str(exc)

    return {
        "token": token,
        "threshold_ton": threshold,
        "whale_count": len(whales),
        "whales": whales[:10],
        "error": error,
    }


@app.get("/volume/{token}")
async def get_volume_spike(token: str) -> dict:
    """
    Volume spike detector: compares 24h volume to market cap.
    High volume/mcap ratio (> 30%) signals abnormal activity.
    """
    coin_id = await _resolve_coin_id(token)
    data = await _coingecko(
        "/coins/markets",
        {
            "vs_currency": "usd",
            "ids": coin_id,
            "per_page": 1,
            "price_change_percentage": "1h,24h",
        },
    )
    if not data:
        raise HTTPException(status_code=404, detail=f"No volume data for '{token}'")

    t = data[0]
    vol_24h = t.get("total_volume") or 0
    mcap = t.get("market_cap") or 0
    turnover_pct = round(vol_24h / mcap * 100, 2) if mcap > 0 else None

    spike = turnover_pct is not None and turnover_pct > 30
    if turnover_pct is None:
        severity = "unknown"
    elif turnover_pct > 100:
        severity = "critical"
    elif turnover_pct > 50:
        severity = "high"
    elif turnover_pct > 30:
        severity = "elevated"
    else:
        severity = "normal"

    return {
        "token": token,
        "coin_id": coin_id,
        "name": t["name"],
        "price_usd": t.get("current_price"),
        "volume_24h_usd": vol_24h,
        "market_cap_usd": mcap,
        "volume_to_mcap_pct": turnover_pct,
        "spike_detected": spike,
        "spike_severity": severity,
        "change_1h_pct": t.get("price_change_percentage_1h_in_currency"),
        "change_24h_pct": t.get("price_change_percentage_24h"),
    }


@app.get("/risk/{token}")
async def get_token_risk(token: str) -> dict:
    """
    Comprehensive risk assessment: volatility, volume anomaly, ATH drawdown,
    market cap rank, and liquidity. Returns a risk score 0–100 and level.
    """
    coin_id = await _resolve_coin_id(token)

    try:
        coin_detail = await _coingecko(
            f"/coins/{coin_id}",
            {"localization": "false", "tickers": "false",
             "community_data": "false", "developer_data": "false"},
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    mkt = coin_detail.get("market_data") or {}
    price = (mkt.get("current_price") or {}).get("usd") or 0
    mcap = (mkt.get("market_cap") or {}).get("usd") or 0
    vol_24h = (mkt.get("total_volume") or {}).get("usd") or 0
    change_24h = mkt.get("price_change_percentage_24h") or 0
    change_7d = mkt.get("price_change_percentage_7d") or 0
    ath = (mkt.get("ath") or {}).get("usd") or 0
    rank = coin_detail.get("market_cap_rank")

    ath_drop_pct = round((1 - price / ath) * 100, 1) if ath > 0 and price > 0 else None
    turnover_pct = round(vol_24h / mcap * 100, 2) if mcap > 0 else None

    risk_score = 0
    risk_flags: list[str] = []

    if turnover_pct is not None:
        if turnover_pct > 50:
            risk_score += 30
            risk_flags.append(f"Volume/mcap {turnover_pct}% — possible pump or manipulation")
        elif turnover_pct > 20:
            risk_score += 15
            risk_flags.append(f"Elevated volume/mcap ratio: {turnover_pct}%")

    if abs(change_24h) > 15:
        risk_score += 25
        risk_flags.append(f"Extreme 24h swing: {change_24h:+.1f}%")
    elif abs(change_24h) > 8:
        risk_score += 12
        risk_flags.append(f"High 24h volatility: {change_24h:+.1f}%")

    if ath_drop_pct is not None and ath_drop_pct > 80:
        risk_score += 20
        risk_flags.append(f"Down {ath_drop_pct}% from all-time high")

    if rank and rank > 500:
        risk_score += 15
        risk_flags.append(f"Low market cap rank #{rank} — limited liquidity")
    elif not rank:
        risk_score += 30
        risk_flags.append("No CoinGecko rank — micro-cap or unverified")

    if change_7d and change_7d < -25:
        risk_score += 10
        risk_flags.append(f"Heavy 7-day drawdown: {change_7d:+.1f}%")

    risk_level = "High" if risk_score >= 55 else "Medium" if risk_score >= 25 else "Low"

    return {
        "token": token,
        "coin_id": coin_id,
        "name": coin_detail.get("name"),
        "price_usd": price,
        "market_cap_usd": mcap,
        "volume_24h_usd": vol_24h,
        "change_24h_pct": change_24h,
        "change_7d_pct": change_7d,
        "ath_drop_pct": ath_drop_pct,
        "volume_to_mcap_pct": turnover_pct,
        "market_cap_rank": rank,
        "risk_score": risk_score,
        "risk_level": risk_level,
        "risk_flags": risk_flags,
    }


# ── Exception handler ──────────────────────────────────────────────────────────

@app.exception_handler(Exception)
async def generic_handler(request, exc: Exception) -> JSONResponse:
    log.error("Unhandled backend error: %s", exc, exc_info=True)
    return JSONResponse(status_code=500, content={"error": "Internal backend error"})


# ── Standalone entry point ─────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8080, log_level="info")
