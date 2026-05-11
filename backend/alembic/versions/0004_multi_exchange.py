"""multi-exchange support

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-11

Adds:
  - `exchange` column to signals / orders / user_strategy_selections (backfilled
    to 'binance', then NOT NULL). The PK of user_strategy_selections becomes
    (user_id, exchange, symbol) so the same symbol can run on two venues.
  - `instruments` table caching exchangeInfo per (exchange, symbol).
  - `user_watchlist` table for per-user pair subscriptions.
  - `encrypted_passphrase` on api_keys (OKX requires it).
"""
from alembic import op
import sqlalchemy as sa


revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) Add nullable exchange columns to the three tables.
    op.add_column(
        "signals",
        sa.Column("exchange", sa.String(16), nullable=True),
    )
    op.add_column(
        "orders",
        sa.Column("exchange", sa.String(16), nullable=True),
    )
    op.add_column(
        "user_strategy_selections",
        sa.Column("exchange", sa.String(16), nullable=True),
    )

    # 2) Backfill existing rows with 'binance'.
    bind = op.get_bind()
    bind.execute(sa.text("UPDATE signals SET exchange = 'binance' WHERE exchange IS NULL"))
    bind.execute(sa.text("UPDATE orders SET exchange = 'binance' WHERE exchange IS NULL"))
    bind.execute(
        sa.text(
            "UPDATE user_strategy_selections SET exchange = 'binance' WHERE exchange IS NULL"
        )
    )

    # 3) NOT NULL.
    op.alter_column("signals", "exchange", nullable=False)
    op.alter_column("orders", "exchange", nullable=False)
    op.alter_column("user_strategy_selections", "exchange", nullable=False)

    # 4) Re-key user_strategy_selections on (user_id, exchange, symbol).
    op.execute(
        "ALTER TABLE user_strategy_selections DROP CONSTRAINT user_strategy_selections_pkey"
    )
    op.create_primary_key(
        "user_strategy_selections_pkey",
        "user_strategy_selections",
        ["user_id", "exchange", "symbol"],
    )
    op.create_index(
        "ix_user_strategy_selections_user_exchange",
        "user_strategy_selections",
        ["user_id", "exchange"],
    )

    # 5) Helpful indexes.
    op.create_index("ix_signals_exchange_symbol", "signals", ["exchange", "symbol"])
    op.create_index("ix_orders_exchange_symbol", "orders", ["exchange", "symbol"])

    # 6) instruments table (cached exchangeInfo).
    op.create_table(
        "instruments",
        sa.Column("exchange", sa.String(16), primary_key=True),
        sa.Column("symbol", sa.String(32), primary_key=True),
        sa.Column("base", sa.String(16), nullable=False),
        sa.Column("quote", sa.String(16), nullable=False),
        sa.Column("contract_type", sa.String(16), nullable=False, server_default="usdt-perp"),
        sa.Column("tick_size", sa.Float(), nullable=False, server_default="0"),
        sa.Column("lot_size", sa.Float(), nullable=False, server_default="0"),
        sa.Column("min_qty", sa.Float(), nullable=False, server_default="0"),
        sa.Column("min_notional", sa.Float(), nullable=False, server_default="0"),
        sa.Column("ccxt_symbol", sa.String(64), nullable=False, server_default=""),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_instruments_active", "instruments", ["active"])
    op.create_index("ix_instruments_base", "instruments", ["base"])

    # 7) user_watchlist table (per-user pair subscriptions).
    op.create_table(
        "user_watchlist",
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("exchange", sa.String(16), primary_key=True),
        sa.Column("symbol", sa.String(32), primary_key=True),
        sa.Column(
            "enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["exchange", "symbol"],
            ["instruments.exchange", "instruments.symbol"],
            ondelete="CASCADE",
            name="fk_user_watchlist_instrument",
        ),
    )
    op.create_index("ix_user_watchlist_user", "user_watchlist", ["user_id"])

    # 8) api_keys: optional passphrase (OKX).
    op.add_column(
        "api_keys",
        sa.Column("encrypted_passphrase", sa.LargeBinary(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("api_keys", "encrypted_passphrase")
    op.drop_index("ix_user_watchlist_user", table_name="user_watchlist")
    op.drop_table("user_watchlist")
    op.drop_index("ix_instruments_base", table_name="instruments")
    op.drop_index("ix_instruments_active", table_name="instruments")
    op.drop_table("instruments")
    op.drop_index("ix_orders_exchange_symbol", table_name="orders")
    op.drop_index("ix_signals_exchange_symbol", table_name="signals")
    op.drop_index(
        "ix_user_strategy_selections_user_exchange", table_name="user_strategy_selections"
    )
    op.execute(
        "ALTER TABLE user_strategy_selections DROP CONSTRAINT user_strategy_selections_pkey"
    )
    op.create_primary_key(
        "user_strategy_selections_pkey",
        "user_strategy_selections",
        ["user_id", "symbol"],
    )
    op.drop_column("user_strategy_selections", "exchange")
    op.drop_column("orders", "exchange")
    op.drop_column("signals", "exchange")
