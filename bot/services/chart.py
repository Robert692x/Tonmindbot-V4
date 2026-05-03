from __future__ import annotations

import io
import logging

# Use the non-interactive Agg backend before importing pyplot or mplfinance.
# Must happen before any other matplotlib import.
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

log = logging.getLogger(__name__)

# ── Theme constants ───────────────────────────────────────────────────────────

_BG      = "#131722"
_GRID    = "#2a2e39"
_TEXT    = "#787b86"
_GREEN   = "#26a69a"
_RED     = "#ef5350"
_EDGE    = "#363a45"

# ── Public API ────────────────────────────────────────────────────────────────

def build_chart(candles: list[dict], interval: str = "1h") -> io.BytesIO:
    """Build a candlestick chart and return PNG bytes in a BytesIO buffer.

    This function is synchronous (matplotlib/mplfinance are blocking).
    Call it inside asyncio.get_event_loop().run_in_executor() from handlers.
    """
    import mplfinance as mpf
    import pandas as pd

    if len(candles) < 3:
        raise ValueError(f"Too few candles to render chart: {len(candles)}")

    df = _prepare_dataframe(candles)
    style = _make_style()

    fig, axes = mpf.plot(
        df,
        type="candle",
        style=style,
        figsize=(10, 5),
        volume=False,           # keep 800×400 (10in × 5in @ 80 DPI)
        returnfig=True,
        show_nontrading=False,
        tight_layout=True,
        datetime_format=_datetime_fmt(interval),
        xrotation=0,
    )

    # Remove top/right spines for a cleaner look
    for ax in axes:
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_color(_EDGE)
        ax.spines["left"].set_color(_EDGE)
        ax.spines["bottom"].set_color(_EDGE)

    # Minimal title
    axes[0].set_title(
        f"TON/USDT  [{interval}]",
        color=_TEXT,
        fontsize=10,
        pad=6,
    )

    buf = io.BytesIO()
    fig.savefig(
        buf,
        format="png",
        dpi=80,
        bbox_inches="tight",
        facecolor=_BG,
        edgecolor="none",
    )
    plt.close(fig)
    buf.seek(0)
    return buf


# ── Helpers ───────────────────────────────────────────────────────────────────

def _prepare_dataframe(candles: list[dict]):
    import pandas as pd

    df = pd.DataFrame(candles)
    df["Date"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df = df.set_index("Date")
    df = df.rename(columns={
        "open":  "Open",
        "high":  "High",
        "low":   "Low",
        "close": "Close",
    })
    # mplfinance requires at least Open/High/Low/Close columns
    return df[["Open", "High", "Low", "Close"]]


def _make_style():
    import mplfinance as mpf

    mc = mpf.make_marketcolors(
        up=_GREEN,
        down=_RED,
        edge="inherit",
        wick="inherit",
    )
    return mpf.make_mpf_style(
        base_mpf_style="nightclouds",
        marketcolors=mc,
        facecolor=_BG,
        edgecolor=_EDGE,
        figcolor=_BG,
        gridcolor=_GRID,
        gridstyle="--",
        y_on_right=True,
        rc={
            "axes.labelcolor": _TEXT,
            "xtick.color":     _TEXT,
            "ytick.color":     _TEXT,
            "font.size":       9,
        },
    )


def _datetime_fmt(interval: str) -> str:
    if interval in ("1m", "5m"):
        return "%H:%M"
    if interval == "30m":
        return "%d %H:%M"
    return "%m-%d %Hh"
