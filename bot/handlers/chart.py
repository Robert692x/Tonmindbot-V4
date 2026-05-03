from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from functools import partial

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, CallbackQuery, InputMediaPhoto, Message

from bot.database.models import User
from bot.keyboards.inline import chart_keyboard
from bot.services.candles import DEFAULT_INTERVAL, VALID_INTERVALS, get_candles, invalidate_cache
from bot.services.chart import build_chart

log = logging.getLogger(__name__)
router = Router(name="chart")

_PAIR = "TON"  # cache key; maps to TONUSDT on Binance


# ── /chart command ────────────────────────────────────────────────────────────

@router.message(Command("chart"))
async def cmd_chart(message: Message, user: User) -> None:
    interval = DEFAULT_INTERVAL
    candles = await get_candles(_PAIR, interval)
    if not candles:
        await message.answer("Chart data is temporarily unavailable. Please try again.")
        return

    buf = await _build_in_executor(candles, interval)
    photo = BufferedInputFile(buf.read(), filename="chart.png")
    await message.answer_photo(
        photo,
        caption=_caption(interval),
        reply_markup=chart_keyboard(user, interval),
    )


# ── Interval switch and refresh ───────────────────────────────────────────────

@router.callback_query(F.data.startswith("chart:"))
async def chart_callback(callback: CallbackQuery, user: User) -> None:
    parts = callback.data.split(":")   # "chart:1h"  or  "chart:refresh:1h"

    if len(parts) == 3 and parts[1] == "refresh":
        # "chart:refresh:{interval}" — force-expire cache before fetching
        interval = parts[2]
        invalidate_cache(_PAIR, interval)
    elif len(parts) == 2:
        interval = parts[1]
    else:
        await callback.answer("Unknown action.", show_alert=True)
        return

    if interval not in VALID_INTERVALS:
        await callback.answer("Unknown interval.", show_alert=True)
        return

    await callback.answer()  # dismiss spinner immediately

    candles = await get_candles(_PAIR, interval)
    if not candles:
        await callback.answer("Chart data unavailable.", show_alert=True)
        return

    buf = await _build_in_executor(candles, interval)
    photo = BufferedInputFile(buf.read(), filename="chart.png")

    with suppress(TelegramBadRequest):
        await callback.message.edit_media(
            InputMediaPhoto(media=photo, caption=_caption(interval)),
            reply_markup=chart_keyboard(user, interval),
        )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _caption(interval: str) -> str:
    return f"TON/USDT  [{interval}]"


async def _build_in_executor(candles: list[dict], interval: str):
    """Run the CPU-bound chart build in a thread executor."""
    loop = asyncio.get_event_loop()
    fn = partial(build_chart, candles, interval)
    return await loop.run_in_executor(None, fn)
