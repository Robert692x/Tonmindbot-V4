import logging
from openai import AsyncOpenAI
from config import settings

log = logging.getLogger(__name__)

SYSTEM = """Ты TON Mind — элитный AI-ассистент по TON блокчейну и крипто-трейдингу.

Специализация: TON, Jetton-токены, DeFi (STON.fi, DeDust, Evaa), whale-аналитика, торговые стратегии.
Стиль: кратко, по делу, с данными. Используй HTML-форматирование Telegram.
Отвечай на языке пользователя (RU/EN). Добавляй ⚠️ DYOR к торговым идеям."""


class AIService:
    def __init__(self):
        self._client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    async def chat(self, message: str, is_premium: bool = False,
                   history: list = None, max_tokens: int = 800) -> tuple[str, int]:
        model = settings.OPENAI_MODEL_PREMIUM if is_premium else settings.OPENAI_MODEL
        messages = [{"role": "system", "content": SYSTEM}]
        if history:
            messages.extend(history[-6:])
        messages.append({"role": "user", "content": message})
        try:
            r = await self._client.chat.completions.create(
                model=model, messages=messages,
                max_tokens=max_tokens, temperature=0.7
            )
            reply = r.choices[0].message.content or ""
            tokens = r.usage.total_tokens if r.usage else 0
            return reply, tokens
        except Exception as e:
            log.error("AI error: %s", e)
            raise

    async def market_analysis(self, is_premium=False) -> str:
        prompt = (
            "Сделай краткий анализ TON-экосистемы прямо сейчас:\n"
            "1. Тренд цены и ключевые уровни\n"
            "2. Активность DeFi на STON.fi/DeDust\n"
            "3. Топ-2 возможности сегодня с уровнями риска\n"
            "Формат: Telegram HTML. До 300 слов."
        )
        reply, _ = await self.chat(prompt, is_premium=is_premium)
        return reply

    async def wallet_analysis(self, address: str, balance: float,
                               tx_summary: str, is_premium=False) -> str:
        prompt = (
            f"Анализ TON-кошелька:\n"
            f"Адрес: {address}\nБаланс: {balance:.4f} TON\n"
            f"Последние транзакции:\n{tx_summary}\n\n"
            f"Дай: поведенческий паттерн, риск-профиль, интересные наблюдения."
        )
        reply, _ = await self.chat(prompt, is_premium=is_premium)
        return reply


ai_service = AIService()
