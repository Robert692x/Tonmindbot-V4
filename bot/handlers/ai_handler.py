import logging
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from bot.database.crud import (get_user, get_ai_used, increment_ai,
                                save_message, check_premium)
from bot.database.db import get_session
from bot.keyboards.keyboards import ai_kb, premium_kb, back_kb
from bot.services.ai_service import ai_service
from bot.services.ton_service import ton_service
from bot.utils.texts import ai_intro_text
from config import settings

log = logging.getLogger(__name__)
router = Router()


class AIState(StatesGroup):
    chatting = State()


@router.callback_query(F.data == "ai")
async def cb_ai(cb: CallbackQuery, state: FSMContext):
    await state.set_state(AIState.chatting)
    async with get_session() as session:
        user = await get_user(session, cb.from_user.id)
        user = await check_premium(session, user)
        used = await get_ai_used(user)
    lang = user.language
    limit = 999 if user.is_premium else settings.FREE_AI_REQUESTS
    model = "GPT-4o" if user.is_premium else "GPT-4o-mini"
    text = ai_intro_text(used, limit, model, lang)
    await cb.message.edit_text(text, reply_markup=ai_kb(lang))
    await cb.answer()


@router.message(AIState.chatting)
async def handle_ai_msg(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if not text:
        return
    async with get_session() as session:
        user = await get_user(session, message.from_user.id)
        user = await check_premium(session, user)
        used = await get_ai_used(user)
        limit = 999 if user.is_premium else settings.FREE_AI_REQUESTS
        lang = user.language

        if used >= limit:
            msg = (
                f"⚠️ Лимит {limit} запросов/день исчерпан.\nОбнови до Premium:"
                if lang == "ru" else
                f"⚠️ Daily limit of {limit} requests reached.\nUpgrade to Premium:"
            )
            await message.answer(msg, reply_markup=premium_kb(lang))
            return

        await increment_ai(session, user)

    await message.bot.send_chat_action(message.chat.id, "typing")
    model_name = settings.OPENAI_MODEL_PREMIUM if user.is_premium else settings.OPENAI_MODEL

    try:
        reply, tokens = await ai_service.chat(text, is_premium=user.is_premium)
    except Exception as e:
        log.error("AI error: %s", e)
        await message.answer("❌ AI недоступен. Попробуй позже.")
        return

    async with get_session() as session:
        await save_message(session, user.id, text, reply, model_name)

    await message.answer(reply, reply_markup=ai_kb(lang))


@router.callback_query(F.data == "ai_market")
async def cb_ai_market(cb: CallbackQuery):
    async with get_session() as session:
        user = await get_user(session, cb.from_user.id)
        user = await check_premium(session, user)
    await cb.answer("Генерирую анализ..." if user.language == "ru" else "Generating...")
    await cb.bot.send_chat_action(cb.message.chat.id, "typing")
    try:
        result = await ai_service.market_analysis(user.is_premium)
        await cb.message.answer(result, reply_markup=ai_kb(user.language))
    except Exception:
        await cb.message.answer("❌ Ошибка AI. Попробуй позже.")


@router.callback_query(F.data == "ai_wallet")
async def cb_ai_wallet(cb: CallbackQuery):
    async with get_session() as session:
        user = await get_user(session, cb.from_user.id)
        user = await check_premium(session, user)
    lang = user.language
    if not user.ton_wallet:
        await cb.answer(
            "Подключи кошелёк сначала" if lang == "ru" else "Connect wallet first",
            show_alert=True
        )
        return
    await cb.answer("Анализирую..." if lang == "ru" else "Analyzing...")
    await cb.bot.send_chat_action(cb.message.chat.id, "typing")
    try:
        info = await ton_service.get_wallet_info(user.ton_wallet)
        summary = "\n".join(
            f"- {t['amount']:.2f} TON {'IN' if t['in'] else 'OUT'} | {t['date']}"
            for t in info["txs"][:5]
        )
        result = await ai_service.wallet_analysis(
            user.ton_wallet, info["balance"], summary, user.is_premium
        )
        await cb.message.answer(result, reply_markup=ai_kb(lang))
    except Exception:
        await cb.message.answer("❌ Ошибка анализа.")


@router.callback_query(F.data == "ai_clear")
async def cb_ai_clear(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    async with get_session() as session:
        user = await get_user(session, cb.from_user.id)
    lang = user.language if user else "ru"
    await cb.answer("✅ Чат очищен" if lang == "ru" else "✅ Chat cleared", show_alert=True)
    await cb.message.edit_text(
        "🤖 Новый чат начат." if lang == "ru" else "🤖 New chat started.",
        reply_markup=ai_kb(lang)
    )
