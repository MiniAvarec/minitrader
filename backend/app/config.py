from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    APP_ENV: str = "dev"
    JWT_SECRET: str
    MASTER_KEY: str  # Fernet key for encrypting API keys at rest

    DATABASE_URL: str
    REDIS_URL: str = "redis://redis:6379/0"

    BINANCE_USE_TESTNET: bool = True
    BINANCE_SYMBOLS: str = "BTCUSDT,ETHUSDT"
    BINANCE_TIMEFRAMES: str = "1m,3m,15m,1h"

    FINNHUB_API_KEY: str = ""
    CRYPTOPANIC_API_KEY: str = ""

    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_WEBHOOK_SECRET: str = "dev"
    WORKER_SHARED_SECRET: str = "dev"

    FRONTEND_ORIGIN: str = "http://localhost:5173"

    @property
    def symbols(self) -> list[str]:
        return [s.strip().upper() for s in self.BINANCE_SYMBOLS.split(",") if s.strip()]

    @property
    def timeframes(self) -> list[str]:
        return [t.strip() for t in self.BINANCE_TIMEFRAMES.split(",") if t.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
