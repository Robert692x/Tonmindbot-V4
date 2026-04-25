import logging
from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from bot.database.crud import get_or_create_user
from bot.database.db import get_session
from bot.keyboards.keyboards import main_menu_kb
from bot.utils.texts import START_RU, START_EN

log = logging.getLogger(__name__)
router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    tg = message.from_user
    ref_code = None
    if message.text and " " in message.text:
        parts = message.text.split()
        if len(parts) > 1:
            ref_code = parts[1]

    async with get_session() as session:
        user, created = await get_or_create_user(
            session, tg.id, tg.username, tg.first_name, ref_code
        )
        lang = user.language

    text = START_RU if lang == "ru" else START_EN
    await message.answer(text, reply_markup=main_menu_kb(lang))
    log.info("Start: tg=%d new=%s", tg.id, created)
