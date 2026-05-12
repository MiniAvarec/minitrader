"""IBKR + multi-currency foundation

Revision ID: 0012
Revises: 0011
Create Date: 2026-05-11

Schema groundwork for the IBKR broker integration:
- orders.quote_currency: which currency the *_usdt columns are denominated in
  for this row (kept the column names; semantics now generalize beyond USDT).
- instruments.currency: contract currency (USD, EUR, JPY, ...).
- api_keys.connection_config: JSON-encoded connection details for brokers that
  don't fit the api_key / api_secret model (IBKR uses host/port/clientId/account).
"""
from alembic import op
import sqlalchemy as sa


revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "orders",
        sa.Column(
            "quote_currency",
            sa.String(length=8),
            nullable=False,
            server_default="USDT",
        ),
    )
    op.add_column(
        "instruments",
        sa.Column(
            "currency",
            sa.String(length=8),
            nullable=False,
            server_default="USDT",
        ),
    )
    op.add_column(
        "api_keys",
        sa.Column("connection_config", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("api_keys", "connection_config")
    op.drop_column("instruments", "currency")
    op.drop_column("orders", "quote_currency")
