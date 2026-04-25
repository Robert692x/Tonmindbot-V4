import httpx
import logging

log = logging.getLogger(__name__)


async def get_ston_pools(limit=5) -> list:
    try:
        async with httpx.AsyncClient(timeout=10.0) as c:
            r = await c.get("https://api.ston.fi/v1/pools", params={"limit": limit})
            if r.status_code == 200:
                raw = r.json().get("pool_list", [])
                result = []
                for p in raw[:limit]:
                    result.append({
                        "token0": p.get("token0_symbol", "?"),
                        "token1": p.get("token1_symbol", "?"),
                        "tvl_usd": p.get("lp_total_supply_usd", 0),
                        "apy": p.get("apy_1d"),
                    })
                return result
    except Exception as e:
        log.error("STON.fi error: %s", e)
    return []
