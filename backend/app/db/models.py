from datetime import datetime, timezone
from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    JSON,
    LargeBinary,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum

from app.db.base import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TradingMode(str, enum.Enum):
    signal_only = "signal_only"
    auto_execute = "auto_execute"


class SignalSide(str, enum.Enum):
    buy = "buy"
    sell = "sell"


class SignalStatus(str, enum.Enum):
    new = "new"
    dispatched = "dispatched"
    executed = "executed"
    dismissed = "dismissed"
    failed = "failed"
    suppressed = "suppressed"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    # trading prefs
    mode: Mapped[TradingMode] = mapped_column(
        Enum(TradingMode), default=TradingMode.signal_only
    )
    telegram_chat_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    telegram_link_token: Mapped[str | None] = mapped_column(String(64), nullable=True)

    api_keys: Mapped[list["ApiKey"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    risk_config: Mapped["RiskConfig | None"] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )


class ApiKey(Base):
    __tablename__ = "api_keys"
    __table_args__ = (UniqueConstraint("user_id", "exchange", "label"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    exchange: Mapped[str] = mapped_column(String(32))  # "binance" | "okx" | "bybit"
    label: Mapped[str] = mapped_column(String(64), default="default")
    encrypted_key: Mapped[bytes] = mapped_column(LargeBinary)
    encrypted_secret: Mapped[bytes] = mapped_column(LargeBinary)
    encrypted_passphrase: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    testnet: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped[User] = relationship(back_populates="api_keys")


class RiskConfig(Base):
    __tablename__ = "risk_configs"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    max_notional_usdt: Mapped[float] = mapped_column(Float, default=50.0)
    daily_loss_limit_usdt: Mapped[float] = mapped_column(Float, default=100.0)
    max_concurrent_positions: Mapped[int] = mapped_column(Integer, default=3)
    require_sl_tp: Mapped[bool] = mapped_column(Boolean, default=True)

    user: Mapped[User] = relationship(back_populates="risk_config")


class Signal(Base):
    __tablename__ = "signals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    strategy_id: Mapped[int | None] = mapped_column(
        ForeignKey("strategies.id", ondelete="SET NULL"), nullable=True, index=True
    )
    exchange: Mapped[str] = mapped_column(String(16), default="binance", index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    side: Mapped[SignalSide] = mapped_column(Enum(SignalSide))
    confidence: Mapped[float] = mapped_column(Float)
    entry: Mapped[float] = mapped_column(Float)
    sl: Mapped[float | None] = mapped_column(Float, nullable=True)
    tp: Mapped[float | None] = mapped_column(Float, nullable=True)
    breakdown: Mapped[dict] = mapped_column(JSON)
    news_refs: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[SignalStatus] = mapped_column(Enum(SignalStatus), default=SignalStatus.new)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )


class Strategy(Base):
    __tablename__ = "strategies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("strategies.id", ondelete="SET NULL"), nullable=True
    )
    slug: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str] = mapped_column(String(2048), default="")
    code: Mapped[str] = mapped_column(String(16384))  # YAML text
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=False)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (UniqueConstraint("user_id", "slug", name="uq_strategy_user_slug"),)


class UserStrategySelection(Base):
    __tablename__ = "user_strategy_selections"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    exchange: Mapped[str] = mapped_column(String(16), primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), primary_key=True)
    strategy_id: Mapped[int] = mapped_column(
        ForeignKey("strategies.id", ondelete="CASCADE"), index=True
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    signal_id: Mapped[int | None] = mapped_column(ForeignKey("signals.id"), nullable=True)
    exchange: Mapped[str] = mapped_column(String(16), default="binance", index=True)
    symbol: Mapped[str] = mapped_column(String(32))
    side: Mapped[SignalSide] = mapped_column(Enum(SignalSide))
    qty: Mapped[float] = mapped_column(Float)
    notional_usdt: Mapped[float] = mapped_column(Float)
    entry_price: Mapped[float] = mapped_column(Float)
    sl: Mapped[float | None] = mapped_column(Float, nullable=True)
    tp: Mapped[float | None] = mapped_column(Float, nullable=True)
    exchange_order_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    realized_pnl_usdt: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(32), default="open")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RiskEvent(Base):
    __tablename__ = "risk_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    signal_id: Mapped[int | None] = mapped_column(ForeignKey("signals.id"), nullable=True)
    check_name: Mapped[str] = mapped_column(String(64))
    ok: Mapped[bool] = mapped_column(Boolean)
    reason: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )


class Instrument(Base):
    __tablename__ = "instruments"

    exchange: Mapped[str] = mapped_column(String(16), primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), primary_key=True)
    base: Mapped[str] = mapped_column(String(16))
    quote: Mapped[str] = mapped_column(String(16))
    contract_type: Mapped[str] = mapped_column(String(16), default="usdt-perp")
    tick_size: Mapped[float] = mapped_column(Float, default=0.0)
    lot_size: Mapped[float] = mapped_column(Float, default=0.0)
    min_qty: Mapped[float] = mapped_column(Float, default=0.0)
    min_notional: Mapped[float] = mapped_column(Float, default=0.0)
    ccxt_symbol: Mapped[str] = mapped_column(String(64), default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class UserWatchlistEntry(Base):
    __tablename__ = "user_watchlist"
    __table_args__ = (
        ForeignKeyConstraint(
            ["exchange", "symbol"],
            ["instruments.exchange", "instruments.symbol"],
            ondelete="CASCADE",
            name="fk_user_watchlist_instrument",
        ),
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    exchange: Mapped[str] = mapped_column(String(16), primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class NewsItem(Base):
    __tablename__ = "news_items"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(32), index=True)
    external_id: Mapped[str] = mapped_column(String(128), index=True)
    headline: Mapped[str] = mapped_column(String(512))
    url: Mapped[str] = mapped_column(String(1024))
    symbols: Mapped[list] = mapped_column(JSON, default=list)
    sentiment: Mapped[float] = mapped_column(Float, default=0.0)  # -1..1
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (UniqueConstraint("source", "external_id"),)


class MarketSentiment(Base):
    """Time series of market-regime scores (e.g. Fear & Greed Index)."""
    __tablename__ = "market_sentiment"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(32), index=True)
    value: Mapped[float] = mapped_column(Float)
    classification: Mapped[str | None] = mapped_column(String(64), nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )


class RedditHype(Base):
    """Latest community-hype score per symbol from Reddit polling."""
    __tablename__ = "reddit_hype"

    symbol: Mapped[str] = mapped_column(String(32), primary_key=True)
    score: Mapped[float] = mapped_column(Float, default=0.0)  # 0..1
    mentions_60m: Mapped[int] = mapped_column(Integer, default=0)
    upvotes_60m: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )


class AppSetting(Base):
    """System-wide configuration values (e.g. third-party API keys).

    Values are stored encrypted at rest with the same Fernet key used for
    user exchange credentials. Used for shared integrations whose data the
    news/signals workers consume on behalf of all users.
    """
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    encrypted_value: Mapped[bytes] = mapped_column(LargeBinary)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
