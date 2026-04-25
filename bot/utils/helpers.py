from datetime import datetime, timezone
from typing import Optional


def shorten(addr: str, n: int = 6) -> str:
    if not addr or len(addr) < n * 2:
        return addr
    return f"{addr[:n]}...{addr[-4:]}"


def fmt_ton(amount: float) -> str:
    return f"{amount:,.4f} TON" if amount < 1000 else f"{amount:,.2f} TON"


def premium_left(dt: Optional[datetime]) -> str:
    if not dt:
        return "—"
    delta = dt - datetime.now(timezone.utc)
    if delta.total_seconds() <= 0:
        return "Истёк"
    return f"{delta.days}д {delta.seconds // 3600}ч"
