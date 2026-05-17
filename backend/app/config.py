from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    APP_ENV: str = "dev"
    JWT_SECRET: str
    MASTER_KEY: str  # Fernet key for encrypting API keys at rest

    # First user registering with this email is auto-approved + granted admin.
    # All other registrations are pending until an admin approves them.
    ADMIN_EMAIL: str = ""

    DATABASE_URL: str
    REDIS_URL: str = "redis://redis:6379/0"

    # Multi-exchange: which exchanges this deployment is allowed to talk to.
    ENABLED_EXCHANGES: str = "binance,okx,bybit"
    BINANCE_USE_TESTNET: bool = True
    OKX_USE_TESTNET: bool = True
    BYBIT_USE_TESTNET: bool = True
    # Exness has no demo/live *flag* — it's the server name. This only drives
    # the UI "demo/live" label and the testnet default; the real switch is the
    # EXNESS_SERVER / per-key server value (Exness-MT5TrialN vs Exness-MT5RealN).
    EXNESS_USE_TESTNET: bool = True

    # Timeframes the ingestor subscribes to by default. Per-user strategies can
    # use any subset of these.
    DEFAULT_TIMEFRAMES: str = "1m,3m,15m,1h"

    FINNHUB_API_KEY: str = ""
    CRYPTOPANIC_API_KEY: str = ""
    CRYPTOCOMPARE_API_KEY: str = ""
    NEWSDATA_API_KEY: str = ""
    # Reddit's public JSON endpoints require a non-default User-Agent.
    REDDIT_USER_AGENT: str = "minitrader/0.1"

    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_WEBHOOK_SECRET: str = "dev"
    WORKER_SHARED_SECRET: str = "dev"

    FRONTEND_ORIGIN: str = "http://localhost:5173"

    @property
    def enabled_exchanges(self) -> list[str]:
        return [e.strip().lower() for e in self.ENABLED_EXCHANGES.split(",") if e.strip()]

    @property
    def default_timeframes(self) -> list[str]:
        return [t.strip() for t in self.DEFAULT_TIMEFRAMES.split(",") if t.strip()]

    def testnet_for(self, exchange: str) -> bool:
        return {
            "binance": self.BINANCE_USE_TESTNET,
            "okx": self.OKX_USE_TESTNET,
            "bybit": self.BYBIT_USE_TESTNET,
            "exness": self.EXNESS_USE_TESTNET,
        }.get(exchange, True)


@lru_cache
def get_settings() -> Settings:
    return Settings()
