import logging
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from bot.database.crud import get_user, set_wallet
from bot.database.db import get_session
from bot.keyboards.keyboards import wallet_kb, wallet_connect_kb, back_kb
from bot.services.ton_service import ton_service
from bot.utils.texts import wallet_text, WALLET_NOT_CONNECTED_RU, WALLET_NOT_CONNECTED_EN

log = logging.getLogger(__name__)
router = Router()


class WalletState(StatesGroup):
    waiting = State()


@router.callback_query(F.data == "wallet")
async def cb_wallet(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    async with get_session() as session:
        user = await get_user(session, cb.from_user.id)
    lang = user.language if user else "ru"

    if not user or not user.ton_wallet:
        text = WALLET_NOT_CONNECTED_RU if lang == "ru" else WALLET_NOT_CONNECTED_EN
        await cb.message.edit_text(text, reply_markup=wallet_connect_kb(lang))
        await cb.answer()
        return

    await cb.answer("Загружаю..." if lang == "ru" else "Loading...")
    try:
        info = await ton_service.get_wallet_info(user.ton_wallet)
        text = wallet_text(info["address"], info["balance"], info["txs"], lang)
    except Exception as e:
        log.error("Wallet error: %s", e)
        text = "❌ Ошибка загрузки. Попробуй позже."
    await cb.message.edit_text(text, reply_markup=wallet_kb(lang))


@router.callback_query(F.data == "wallet_connect")
async def cb_wallet_connect(cb: CallbackQuery, state: FSMContext):
    async with get_session() as session:
        user = await get_user(session, cb.from_user.id)
    lang = user.language if user else "ru"
    await state.set_state(WalletState.waiting)
    prompt = (
        "📍 Отправь TON-адрес (EQ... или UQ...):"
        if lang == "ru" else
        "📍 Send your TON address (EQ... or UQ...):"
    )
    await cb.message.edit_text(prompt, reply_markup=back_kb(lang))
    await cb.answer()


@router.message(WalletState.waiting)
async def process_wallet(message: Message, state: FSMContext):
    addr = (message.text or "").strip()
    async with get_session() as session:
        user = await get_user(session, message.from_user.id)
    lang = user.language if user else "ru"

    if not ton_service.is_valid_address(addr):
        err = "❌ Неверный формат адреса." if lang == "ru" else "❌ Invalid address format."
        await message.answer(err)
        return

    async with get_session() as session:
        await set_wallet(session, message.from_user.id, addr)

    await state.clear()
    ok = f"✅ Кошелёк подключён!\n<code>{addr}</code>" if lang == "ru" else f"✅ Wallet connected!\n<code>{addr}</code>"
    from bot.keyboards.keyboards import wallet_kb
    await message.answer(ok, reply_markup=wallet_kb(lang))
