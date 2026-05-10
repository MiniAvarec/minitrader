"""init

Revision ID: 0001
Revises:
Create Date: 2026-05-10

"""
from alembic import op
import sqlalchemy as sa


revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(254), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column(
            "mode",
            sa.Enum("signal_only", "auto_execute", name="tradingmode"),
            nullable=False,
            server_default="signal_only",
        ),
        sa.Column("telegram_chat_id", sa.String(64), nullable=True),
        sa.Column("telegram_link_token", sa.String(64), nullable=True),
    )
    op.create_index("ix_users_email", "users", ["email"])

    op.create_table(
        "api_keys",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("exchange", sa.String(32), nullable=False),
        sa.Column("label", sa.String(64), server_default="default"),
        sa.Column("encrypted_key", sa.LargeBinary(), nullable=False),
        sa.Column("encrypted_secret", sa.LargeBinary(), nullable=False),
        sa.Column("testnet", sa.Boolean(), server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "exchange", "label"),
    )
    op.create_index("ix_api_keys_user_id", "api_keys", ["user_id"])

    op.create_table(
        "risk_configs",
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("max_notional_usdt", sa.Float(), server_default="50"),
        sa.Column("daily_loss_limit_usdt", sa.Float(), server_default="100"),
        sa.Column("max_concurrent_positions", sa.Integer(), server_default="3"),
        sa.Column("require_sl_tp", sa.Boolean(), server_default=sa.text("true")),
    )

    op.create_table(
        "signals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("symbol", sa.String(32), nullable=False),
        sa.Column("side", sa.Enum("buy", "sell", name="signalside"), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("entry", sa.Float(), nullable=False),
        sa.Column("sl", sa.Float(), nullable=True),
        sa.Column("tp", sa.Float(), nullable=True),
        sa.Column("breakdown", sa.JSON(), nullable=False),
        sa.Column("news_refs", sa.JSON(), server_default="[]"),
        sa.Column(
            "status",
            sa.Enum(
                "new", "dispatched", "executed", "dismissed", "failed", "suppressed",
                name="signalstatus",
            ),
            server_default="new",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_signals_symbol", "signals", ["symbol"])
    op.create_index("ix_signals_created_at", "signals", ["created_at"])

    op.create_table(
        "orders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("signal_id", sa.Integer(), sa.ForeignKey("signals.id"), nullable=True),
        sa.Column("symbol", sa.String(32), nullable=False),
        sa.Column("side", sa.Enum("buy", "sell", name="signalside"), nullable=False),
        sa.Column("qty", sa.Float(), nullable=False),
        sa.Column("notional_usdt", sa.Float(), nullable=False),
        sa.Column("entry_price", sa.Float(), nullable=False),
        sa.Column("sl", sa.Float(), nullable=True),
        sa.Column("tp", sa.Float(), nullable=True),
        sa.Column("exchange_order_id", sa.String(64), nullable=True),
        sa.Column("realized_pnl_usdt", sa.Float(), server_default="0"),
        sa.Column("status", sa.String(32), server_default="open"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_orders_user_id", "orders", ["user_id"])
    op.create_index("ix_orders_created_at", "orders", ["created_at"])

    op.create_table(
        "risk_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("signal_id", sa.Integer(), sa.ForeignKey("signals.id"), nullable=True),
        sa.Column("check_name", sa.String(64), nullable=False),
        sa.Column("ok", sa.Boolean(), nullable=False),
        sa.Column("reason", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_risk_events_user_id", "risk_events", ["user_id"])
    op.create_index("ix_risk_events_created_at", "risk_events", ["created_at"])

    op.create_table(
        "news_items",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("external_id", sa.String(128), nullable=False),
        sa.Column("headline", sa.String(512), nullable=False),
        sa.Column("url", sa.String(1024), nullable=False),
        sa.Column("symbols", sa.JSON(), server_default="[]"),
        sa.Column("sentiment", sa.Float(), server_default="0"),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("source", "external_id"),
    )
    op.create_index("ix_news_items_source", "news_items", ["source"])
    op.create_index("ix_news_items_external_id", "news_items", ["external_id"])
    op.create_index("ix_news_items_published_at", "news_items", ["published_at"])


def downgrade() -> None:
    op.drop_table("news_items")
    op.drop_table("risk_events")
    op.drop_table("orders")
    op.drop_table("signals")
    op.drop_table("risk_configs")
    op.drop_table("api_keys")
    op.drop_table("users")
    op.execute("DROP TYPE IF EXISTS signalstatus")
    op.execute("DROP TYPE IF EXISTS signalside")
    op.execute("DROP TYPE IF EXISTS tradingmode")
