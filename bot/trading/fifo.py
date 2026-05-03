from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class FifoMatch:
    buy_trade_id: int
    amount: float        # amount matched from this buy lot
    buy_price: float
    sell_price: float
    pnl: float           # (sell_price - buy_price) * amount, before fee allocation


@dataclass
class FifoResult:
    matches: list[FifoMatch] = field(default_factory=list)

    @property
    def total_pnl(self) -> float:
        return sum(m.pnl for m in self.matches)

    @property
    def matched_amount(self) -> float:
        return sum(m.amount for m in self.matches)


def match_fifo(
    open_buys: list[tuple[int, float, float]],  # (trade_id, remaining_amount, buy_price)
    sell_amount: float,
    sell_price: float,
) -> FifoResult:
    """Match sell_amount against open BUY lots using FIFO (oldest first).

    open_buys must already be sorted oldest-first by the caller.
    Returns FifoResult with per-lot breakdown and total PnL.
    Stops as soon as sell_amount is fully matched.
    """
    result = FifoResult()
    remaining_sell = sell_amount

    for trade_id, available, buy_price in open_buys:
        if remaining_sell <= 1e-10:
            break
        matched = min(remaining_sell, available)
        result.matches.append(
            FifoMatch(
                buy_trade_id=trade_id,
                amount=matched,
                buy_price=buy_price,
                sell_price=sell_price,
                pnl=(sell_price - buy_price) * matched,
            )
        )
        remaining_sell -= matched

    return result
