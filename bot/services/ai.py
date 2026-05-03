"""
AI service for TON Mind Bot.

Uses the OpenAI Responses API (`client.responses.create`) with:
  - Agentic tool-call loop (up to MAX_TOOL_ROUNDS rounds)
  - Tenacity retry on transient network errors
  - Strict system prompt that forbids hallucination
  - Structured output format enforced in prompt

Tool schemas live in ai_tools.py; execution is delegated to ToolExecutor
which calls the FastAPI backend (server.py).
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from inspect import isawaitable
from typing import Any

from openai import AsyncOpenAI, AuthenticationError, APIConnectionError, APIStatusError, APITimeoutError
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from bot.services.ai_tools import TOOLS, ToolExecutor
from bot.services.tonapi import WalletReport
from config import Settings

log = logging.getLogger(__name__)

TOKEN_HINT_RE = re.compile(
    r"\$[A-Za-z0-9]{2,10}\b|\b(?:token|jetton|coin|swap|dex|токен|джеттон|монета)\b",
    re.IGNORECASE,
)
_HTML_TAG_RE = re.compile(r"</?(?:b|i|u|s|code|pre|a|tg-emoji|tg-spoiler)[^>]*>", re.IGNORECASE)

AI_FALLBACK = "Insufficient on-chain data. The data provider may be temporarily unavailable. Please try again."
AI_TIMEOUT_SECONDS = 50.0
RESPONSE_MAX_CHARS = 4000
MAX_TOOL_ROUNDS = 4  # Maximum agentic tool-call iterations per request

# ── System prompt ──────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are TON Mind Bot — a blockchain intelligence system.
You are NOT a chatbot. You are a data analysis engine.

════════════════════════════════════
MANDATORY RULES — NEVER BREAK THESE
════════════════════════════════════
1. NEVER answer a blockchain or market question without calling the appropriate tool first.
2. If a tool returns an error or empty data → reply with exactly:
   "Insufficient on-chain data. [reason from tool error]"
   Do NOT fabricate or estimate any values.
3. NEVER guess prices, balances, transactions, or any on-chain data.
4. Call multiple tools in parallel when a question requires multiple data points.

════════════════════════
REQUIRED RESPONSE FORMAT
════════════════════════
Every response MUST follow this exact structure:

<b>Summary</b>
[1-2 sentences. What is the answer to the user's question.]

<b>Data</b>
[Raw numbers from tool results. Exact values only — no rounding.]

<b>Interpretation</b>
[What the data means in context. Be specific and factual.]

<b>Risk</b>
[Low / Medium / High — with one concise reason from the data.]

════════════════════
AVAILABLE TOOLS
════════════════════
• get_wallet_activity(address)  — balance, txs, risk for a TON wallet
• get_token_data(token)         — price, market cap, 24h change
• get_swap_activity(token)      — STON.fi DEX pools and volume
• get_whale_activity(token)     — large TON transfers above threshold
• get_volume_spike(token)       — volume anomaly detection
• get_token_risk(token)         — full risk score with flags

"my wallet" or "мой кошелёк" → pass address="my_wallet"

════════════════════
FORMATTING RULES
════════════════════
• Telegram HTML only: <b>bold</b>, <i>italic</i>, <code>code</code>
• No markdown (no **, __, ```, #)
• No emojis
• No hype language ("moon", "bullish opportunity", "DYOR")
• Maximum 500 words
• Numbers: always show units (TON, USD, %)
"""


@dataclass(slots=True)
class AIResult:
    content: str
    model: str
    intent: str


class AIService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client = AsyncOpenAI(
            api_key=settings.OPENAI_API_KEY,
            timeout=AI_TIMEOUT_SECONDS,
        )
        self._tool_executor: ToolExecutor | None = None

    def set_tool_executor(self, executor: ToolExecutor) -> None:
        self._tool_executor = executor

    async def close(self) -> None:
        if self._tool_executor is not None:
            await self._tool_executor.close()
        close_fn = getattr(self._client, "close", None)
        if close_fn is not None:
            result = close_fn()
            if isawaitable(result):
                await result

    # ── Intent detection ───────────────────────────────────────────────────────

    def extract_wallet_address(self, text: str) -> str | None:
        from bot.services.tonapi import TonApiService
        return TonApiService.extract_wallet_address(text)

    def detect_intent(self, text: str) -> str:
        if self.extract_wallet_address(text):
            return "wallet"
        lowered = text.lower()
        if any(w in lowered for w in ("my wallet", "wallet", "кошелек", "кошелёк")):
            return "wallet"
        if any(w in lowered for w in ("trending", "тренд", "popular", "hot coins", "горяч")):
            return "trending"
        if any(w in lowered for w in ("whale", "кит", "large transfer", "крупн",
                                       "who is buying", "who bought", "кто покупает")):
            return "whale"
        if TOKEN_HINT_RE.search(text):
            return "token"
        return "question"

    # ── Post-processing ────────────────────────────────────────────────────────

    def strip_html(self, text: str) -> str:
        return _HTML_TAG_RE.sub("", text)

    def post_process(self, content: str) -> str:
        if len(content) <= RESPONSE_MAX_CHARS:
            return content
        truncated = content[:RESPONSE_MAX_CHARS]
        last_nl = truncated.rfind("\n", RESPONSE_MAX_CHARS - 200)
        if last_nl > RESPONSE_MAX_CHARS // 2:
            truncated = truncated[:last_nl]
        return truncated + "\n\n<i>… response truncated</i>"

    # ── Message construction ───────────────────────────────────────────────────

    def _build_input(
        self,
        prompt: str,
        language_code: str,
        wallet_report: WalletReport | None,
        market_context: dict[str, Any] | None,
        history: list[dict[str, str]] | None,
    ) -> list[dict]:
        lang = "Respond in Russian." if language_code == "ru" else "Respond in English."
        system_content = f"{SYSTEM_PROMPT}\n{lang}"

        if wallet_report is not None:
            txs_preview = "; ".join(
                f"{tx.direction} {tx.amount_ton:.2f} TON"
                + (f" [{tx.comment}]" if tx.comment else "")
                for tx in wallet_report.transactions[:3]
            )
            system_content += (
                f"\n\nPre-fetched wallet context (supplement tool data):\n"
                f"Address: {wallet_report.address}\n"
                f"Balance: {wallet_report.balance_ton:.4f} TON\n"
                f"Risk: {wallet_report.risk.level}\n"
                f"Recent: {txs_preview or 'no transactions'}"
            )

        if market_context is not None:
            system_content += f"\n\nMarket context: {json.dumps(market_context)}"

        input_messages: list[dict] = [{"role": "system", "content": system_content}]

        if history:
            input_messages.extend(history[-8:])

        input_messages.append({"role": "user", "content": prompt})
        return input_messages

    # ── Tool execution ─────────────────────────────────────────────────────────

    async def _run_tool(self, name: str, arguments: str) -> str:
        if self._tool_executor is None:
            return json.dumps({"error": "Tool executor not initialised"})
        try:
            args = json.loads(arguments)
        except json.JSONDecodeError:
            args = {}
        log.info("Tool call: %s | args: %s", name, args)
        result = await self._tool_executor.execute(name, args)
        log.debug("Tool result: %s | %s", name, result[:160])
        return result

    # ── OpenAI Responses API call (with retry) ─────────────────────────────────

    @retry(
        retry=retry_if_exception_type((APIConnectionError, APITimeoutError)),
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=2, max=8),
        reraise=True,
    )
    async def _api_call(
        self,
        model: str,
        input_messages: list,
        tools: list | None,
    ) -> Any:
        kwargs: dict[str, Any] = {
            "model": model,
            "input": input_messages,
            "temperature": 0.2,
            "max_output_tokens": 1200,
        }
        if tools:
            kwargs["tools"] = tools
            # "auto" lets the model decide; it will use tools when needed
            kwargs["tool_choice"] = "auto"

        return await self._client.responses.create(**kwargs)

    # ── Core analysis entry point ──────────────────────────────────────────────

    async def analyze(
        self,
        *,
        prompt: str,
        is_premium: bool,
        language_code: str = "en",
        history: list[dict[str, str]] | None = None,
        wallet_report: WalletReport | None = None,
        market_context: dict[str, Any] | None = None,
    ) -> AIResult:
        intent = self.detect_intent(prompt)
        model = self.settings.OPENAI_MODEL_PREMIUM if is_premium else self.settings.OPENAI_MODEL
        log.debug("AI analyze | prompt=%r | model=%s | intent=%s", prompt[:80], model, intent)

        input_messages = self._build_input(
            prompt=prompt,
            language_code=language_code,
            wallet_report=wallet_report,
            market_context=market_context,
            history=history,
        )
        tools = TOOLS if self._tool_executor else None

        try:
            response = await self._api_call(model, input_messages, tools)

            # ── Agentic tool-call loop ─────────────────────────────────────────
            for round_num in range(MAX_TOOL_ROUNDS):
                tool_calls = [
                    item for item in response.output
                    if getattr(item, "type", None) == "function_call"
                ]
                if not tool_calls:
                    break  # No more tool calls — proceed to final answer

                log.info("Tool round %d: %d call(s)", round_num + 1, len(tool_calls))

                # Append the full assistant turn (all output items)
                input_messages.extend(response.output)

                # Execute tools and append results
                for tc in tool_calls:
                    tool_result = await self._run_tool(tc.name, tc.arguments)
                    input_messages.append({
                        "type": "function_call_output",
                        "call_id": tc.call_id,
                        "output": tool_result,
                    })

                # Get the next response with tool results injected
                response = await self._api_call(model, input_messages, tools)

            # ── Extract final text ─────────────────────────────────────────────
            final_text = ""
            for item in response.output:
                if getattr(item, "type", None) == "message":
                    for part in getattr(item, "content", []):
                        text = getattr(part, "text", None)
                        if text:
                            final_text += text

            if not final_text.strip():
                final_text = "Insufficient on-chain data."

            content = self.post_process(final_text)
            log.debug("AI response done | intent=%s | chars=%d | model=%s", intent, len(content), model)
            return AIResult(content=content, model=model, intent=intent)

        except AuthenticationError:
            log.critical(
                "OpenAI API key invalid (401). "
                "Update OPENAI_API_KEY in .env — get a key at https://platform.openai.com/api-keys"
            )
            return AIResult(
                content="AI unavailable: invalid API key. Contact the bot administrator.",
                model=model,
                intent=intent,
            )
        except APITimeoutError:
            log.error("AI request timed out after %.0fs", AI_TIMEOUT_SECONDS)
            return AIResult(content=AI_FALLBACK, model=model, intent=intent)
        except APIConnectionError as exc:
            log.error("AI connection error: %s", exc)
            return AIResult(content=AI_FALLBACK, model=model, intent=intent)
        except APIStatusError as exc:
            log.error("AI API error %s: %s", exc.status_code, getattr(exc, "message", str(exc)))
            if exc.status_code == 429:
                return AIResult(
                    content="AI rate limit reached. Please wait a moment and try again.",
                    model=model,
                    intent=intent,
                )
            return AIResult(content=AI_FALLBACK, model=model, intent=intent)
        except Exception as exc:
            log.exception("Unexpected AI error: %s", exc)
            return AIResult(content=AI_FALLBACK, model=model, intent=intent)

    # ── Signal generation ──────────────────────────────────────────────────────

    async def generate_signal(
        self,
        *,
        is_premium: bool,
        market_context: dict[str, Any],
        language_code: str = "en",
    ) -> AIResult:
        return await self.analyze(
            prompt=(
                "Produce one TON market signal for the next 24 hours. "
                "Call get_token_data('TON') and get_volume_spike('TON') first, "
                "then give: bias (bullish/bearish/neutral), key trigger, "
                "invalidation level, and one specific risk note."
            ),
            is_premium=is_premium,
            market_context=market_context,
            language_code=language_code,
        )
