from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    BOT_TOKEN: str = Field(...)
    BOT_USERNAME: str = Field("tonmindbot")
    ADMIN_IDS: list[int] = Field(default_factory=list)

    DATABASE_URL: str = Field("postgresql+asyncpg://postgres:postgres@localhost:5432/tonmindbot")
    REDIS_URL: str = Field("redis://localhost:6379/0")

    OPENAI_API_KEY: str = Field(...)
    OPENAI_MODEL: str = Field("gpt-4o-mini")
    OPENAI_MODEL_PREMIUM: str = Field("gpt-4o")

    TON_API_KEY: str = Field(...)
    TON_API_BASE: str = Field("https://toncenter.com/api/v2")
    TON_WALLET: str = Field(...)

    PREMIUM_PRICE_TON: float = Field(5.0)
    PREMIUM_DAYS: int = Field(30)
    FREE_AI_REQUESTS: int = Field(5)
    REFERRAL_BONUS_DAYS: int = Field(7)
    ALGO_PREMIUM_THRESHOLD: int = Field(1000)
    WHALE_THRESHOLD_TON: float = Field(10000.0)

    STONFI_API_BASE: str = Field("https://api.ston.fi/v1")
    LOG_LEVEL: str = Field("INFO")


settings = Settings()
