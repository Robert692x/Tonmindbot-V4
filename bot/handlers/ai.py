from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import User
from bot.database.repositories import UsageLimitRepository
from bot.handlers.common import edit_panel
from bot.keyboards.inline import ai_keyboard, premium_keyboard
from bot.services.container import ServiceContainer
from bot.services.i18n import get_text
from bot.states import AIStates
from bot.utils.formatters import format_ai_landing

log = logging.getLogger(__name__)
router = Router(name="ai")
AI_FEATURE_NAME = "ai_analyst"

# Intents for which there is no point pre-fetching TON market context
_NO_MARKET_CONTEXT_INTENTS = frozenset({"wallet", "trending", "whale"})


async def _ai_usage(session: AsyncSession, user: User) -> int:
    return await UsageLimitRepository(session).get_usage_count(user.id, AI_FEATURE_NAME)


async def _ensure_quota(
    *,
    session: AsyncSession,
    user: User,
    services: ServiceContainer,
    reply_target: Message | CallbackQuery,
) -> bool:
    used = await _ai_usage(session, user)
    if user.is_premium:
        return True
    if used < services.settings.FREE_AI_REQUESTS:
        return True

    text = get_text(user, "ai_quota_reached")
    if isinstance(reply_target, Message):
        await reply_target.answer(text, reply_markup=premium_keyboard(user, False, False))
    else:
        await reply_target.answer(get_text(user, "ai_quota_reached_short"), show_alert=True)
    return False


async def _send_ai_reply(message: Message, content: str, **kwargs) -> None:
    """Send AI response as HTML; fall back to plain text if tags are malformed."""
    try:
        await message.answer(content, **kwargs)
    except TelegramBadRequest as exc:
        if "can't parse entities" in str(exc).lower():
            log.warning("HTML parse error — falling back to plain text: %s", exc)
            import re
            plain_content = re.sub(r"<[^>]+>", "", content)
            await message.answer(
                plain_content,
                parse_mode=None,
                **{k: v for k, v in kwargs.items() if k != "parse_mode"},
            )
        else:
            raise


async def _run_ai(
    *,
    prompt: str,
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    services: ServiceContainer,
) -> None:
    """Shared AI execution core used by the /ai command and FSM message handler."""
    if not await _ensure_quota(session=session, user=user, services=services, reply_target=message):
        return

    history = (await state.get_data()).get("history", [])
    intent = services.ai.detect_intent(prompt)

    # Pre-fetch wallet report when the prompt is clearly wallet-related
    wallet_report = None
    if intent == "wallet":
        wallet_address = services.ai.extract_wallet_address(prompt)
        if wallet_address is None and any(
            w in prompt.lower() for w in ("my wallet", "мой кошелек", "мой кошелёк")
        ):
            wallet_address = user.wallet_address
        if wallet_address:
            try:
                wallet_report = await services.tonapi.get_wallet_report(wallet_address)
            except Exception as exc:
                log.warning("Pre-fetch wallet report failed: %s", exc)

    # Pre-fetch market context only for token/general questions
    market_context = None
    if intent not in _NO_MARKET_CONTEXT_INTENTS:
        try:
            market_context = await services.market.get_signal_context()
        except Exception as exc:
            log.warning("Pre-fetch market context failed: %s", exc)

    await message.bot.send_chat_action(message.chat.id, "typing")

    # Give the tool executor the user's wallet address for "my wallet" lookups
    if services.ai._tool_executor and user.wallet_address:
        services.ai._tool_executor.user_wallet = user.wallet_address

    result = await services.ai.analyze(
        prompt=prompt,
        is_premium=user.is_premium,
        language_code=user.language_code,
        history=history,
        wallet_report=wallet_report,
        market_context=market_context,
    )

    if not user.is_premium:
        await UsageLimitRepository(session).increment(user.id, AI_FEATURE_NAME)

    next_history = history + [
        {"role": "user", "content": prompt},
        {"role": "assistant", "content": result.content},
    ]
    await state.update_data(history=next_history[-8:])
    await _send_ai_reply(message, result.content, reply_markup=ai_keyboard(user, user.is_premium))


# ── Handlers ───────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "ai")
async def ai_panel_handler(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    services: ServiceContainer,
) -> None:
    await state.set_state(AIStates.chatting)
    used = await _ai_usage(session, user)
    limit = None if user.is_premium else services.settings.FREE_AI_REQUESTS
    await edit_panel(
        callback,
        format_ai_landing(user, used, limit, user.is_premium),
        ai_keyboard(user, user.is_premium),
    )
    await callback.answer()


@router.message(Command("ai"))
async def ai_command_handler(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    services: ServiceContainer,
) -> None:
    raw = message.text or ""
    parts = raw.split(None, 1)
    prompt = parts[1].strip() if len(parts) > 1 else ""

    if not prompt:
        await message.answer(
            "Usage: <code>/ai your question</code>\n\n"
            "Examples:\n"
            "<code>/ai What is the TON price?</code>\n"
            "<code>/ai Analyze my wallet</code>\n"
            "<code>/ai What's trending today?</code>"
        )
        return

    log.info("AI command | user=%s | prompt=%r", user.id, prompt)
    await state.set_state(AIStates.chatting)
    await _run_ai(
        prompt=prompt,
        message=message,
        state=state,
        session=session,
        user=user,
        services=services,
    )


@router.message(AIStates.chatting)
async def ai_message_handler(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    services: ServiceContainer,
) -> None:
    prompt = (message.text or "").strip()
    if not prompt:
        return

    log.info("AI message | user=%s | prompt=%r", user.id, prompt)
    await _run_ai(
        prompt=prompt,
        message=message,
        state=state,
        session=session,
        user=user,
        services=services,
    )


@router.callback_query(F.data == "ai:clear")
async def ai_clear_handler(callback: CallbackQuery, state: FSMContext, user: User) -> None:
    await state.set_state(AIStates.chatting)
    await state.update_data(history=[])
    await edit_panel(callback, get_text(user, "ai_chat_reset"), ai_keyboard(user, user.is_premium))
    await callback.answer(get_text(user, "ai_chat_cleared"))


@router.callback_query(F.data == "ai:market")
async def ai_market_handler(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    services: ServiceContainer,
) -> None:
    if not await _ensure_quota(session=session, user=user, services=services, reply_target=callback):
        return
    await callback.answer(get_text(user, "ai_building_market"))

    market_context = None
    try:
        market_context = await services.market.get_signal_context()
    except Exception as exc:
        log.warning("Market context fetch failed: %s", exc)

    result = await services.ai.analyze(
        prompt="Provide a concise TON market brief with risks, trend, and DeFi context.",
        is_premium=user.is_premium,
        language_code=user.language_code,
        history=(await state.get_data()).get("history", []),
        market_context=market_context,
    )
    if not user.is_premium:
        await UsageLimitRepository(session).increment(user.id, AI_FEATURE_NAME)
    await _send_ai_reply(callback.message, result.content, reply_markup=ai_keyboard(user, user.is_premium))


@router.callback_query(F.data == "ai:signal")
async def ai_signal_handler(
    callback: CallbackQuery,
    session: AsyncSession,
    user: User,
    services: ServiceContainer,
) -> None:
    if not user.is_premium:
        await callback.answer(get_text(user, "ai_signal_premium_only"), show_alert=True)
        return
    if not await _ensure_quota(session=session, user=user, services=services, reply_target=callback):
        return
    await callback.answer(get_text(user, "ai_generating_signal"))

    market_context: dict = {}
    try:
        market_context = await services.market.get_signal_context()
    except Exception as exc:
        log.warning("Market context fetch failed for signal: %s", exc)

    signal = await services.ai.generate_signal(
        is_premium=True,
        market_context=market_context,
        language_code=user.language_code,
    )
    await _send_ai_reply(callback.message, signal.content, reply_markup=ai_keyboard(user, True))
