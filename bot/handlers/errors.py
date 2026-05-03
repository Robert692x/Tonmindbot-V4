from __future__ import annotations

import logging

from aiogram import Router
from aiogram.types import ErrorEvent

from bot.services.i18n import get_text

log = logging.getLogger(__name__)
router = Router(name="errors")


@router.errors()
async def error_handler(event: ErrorEvent) -> bool:
    log.exception("Unhandled bot error", exc_info=event.exception)
    update = event.update
    if update.message:
        await update.message.answer(get_text(update.message.from_user or "en", "error_generic"))
    elif update.callback_query:
        await update.callback_query.answer(get_text(update.callback_query.from_user or "en", "error_generic"), show_alert=True)
    return True
