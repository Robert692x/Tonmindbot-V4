from __future__ import annotations

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, LinkPreviewOptions

from bot.services.i18n import get_text

_NO_PREVIEW = LinkPreviewOptions(is_disabled=True)


def welcome_text(subject: object) -> str:
    return get_text(subject, "menu_welcome")


async def edit_panel(callback: CallbackQuery, text: str, reply_markup: InlineKeyboardMarkup) -> None:
    try:
        await callback.message.edit_text(
            text,
            reply_markup=reply_markup,
            link_preview_options=_NO_PREVIEW,
        )
    except TelegramBadRequest:
        await callback.message.answer(
            text,
            reply_markup=reply_markup,
            link_preview_options=_NO_PREVIEW,
        )
