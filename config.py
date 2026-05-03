from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


DEFAULT_WHALE_WATCH_ADDRESSES = [
    "EQCxE6mUtQJKFnGfaROTKOt1lZbDiiX1kCixRv7Nw2Id_sDs",
    "EQB3ncyBUTjZUA5EnFKR5_EnOMI9V1tTEAAPaiU71gc4TiUt",
]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    BOT_TOKEN: str
    BOT_USERNAME: str
    ADMIN_IDS: list[int] = Field(default_factory=list)

    DATABASE_URL: str = "sqlite+aiosqlite:///./bot.db"
    REDIS_URL: str | None = None

    OPENAI_API_KEY: str
    OPENAI_MODEL: str = "gpt-4.1-mini"
    OPENAI_MODEL_PREMIUM: str = "gpt-4.1"

    # Local FastAPI backend — consumed by the AI tool executor
    BACKEND_URL: str = "http://127.0.0.1:8080"
    BACKEND_PORT: int = 8080

    TON_API_KEY: str | None = None
    TON_API_BASE: str = "https://tonapi.io"
    TON_PAYMENT_WALLET: str | None = None
    TON_WALLET: str | None = None
    ALGO_JETTON_ADDRESS: str = "EQCYKUdisY5yEv9Z5f9J5KZQAaOe3ouSAZXSusXUpzFb3r1i"

    STON_API_BASE: str = "https://api.ston.fi"
    COINGECKO_API_BASE: str = "https://api.coingecko.com/api/v3"

    PREMIUM_PRICE_TON: float = 1.0
    PREMIUM_DAYS: int = 30
    FREE_AI_REQUESTS: int = 5
    REFERRAL_BONUS_DAYS: int = 7
    WHALE_THRESHOLD_TON: float = 10_000.0
    WHALE_WATCH_ADDRESSES: list[str] = Field(default_factory=lambda: DEFAULT_WHALE_WATCH_ADDRESSES.copy())

    REQUEST_TIMEOUT_SECONDS: float = 15.0
    CACHE_TTL_WALLET_SECONDS: int = 45
    CACHE_TTL_PRICE_SECONDS: int = 60
    CACHE_TTL_WHALES_SECONDS: int = 90
    CACHE_TTL_DEX_SECONDS: int = 180
    CACHE_TTL_PORTFOLIO_SECONDS: int = 90
    CACHE_TTL_LEADERBOARD_SECONDS: int = 300
    RATE_LIMIT_WINDOW_SECONDS: int = 5
    RATE_LIMIT_MAX_EVENTS: int = 8
    PAYMENT_POLL_INTERVAL_SECONDS: int = 45
    WHALE_ALERT_POLL_INTERVAL_SECONDS: int = 120
    BACKGROUND_SEEN_TTL_SECONDS: int = 21_600
    LOG_LEVEL: str = "INFO"

    @field_validator("ADMIN_IDS", "WHALE_WATCH_ADDRESSES", mode="before")
    @classmethod
    def parse_list(cls, value: Any) -> list[Any]:
        if value is None:
            return []
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            raw = value.strip()
            if not raw:
                return []
            if raw.startswith("["):
                return json.loads(raw)
            return [item.strip() for item in raw.split(",") if item.strip()]
        raise TypeError("Unsupported list format")

    @field_validator("REDIS_URL", "TON_API_KEY", "TON_PAYMENT_WALLET", "TON_WALLET", mode="before")
    @classmethod
    def empty_to_none(cls, value: Any) -> Any:
        if value == "":
            return None
        return value

    @field_validator("TON_API_BASE", mode="before")
    @classmethod
    def normalize_ton_api_base(cls, value: Any) -> str:
        raw = str(value or "").strip()
        if not raw or "tonapi.io" not in raw:
            return "https://tonapi.io"
        return raw.rstrip("/")

    @property
    def payment_wallet(self) -> str:
        wallet = self.TON_PAYMENT_WALLET or self.TON_WALLET
        if not wallet:
            raise ValueError("TON_PAYMENT_WALLET or TON_WALLET must be configured")
        return wallet

    @property
    def bot_link(self) -> str:
        return f"https://t.me/{self.BOT_USERNAME}"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
