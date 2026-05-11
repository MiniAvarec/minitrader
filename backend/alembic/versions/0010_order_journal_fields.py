"""journal fields on orders

Revision ID: 0010
Revises: 0009
Create Date: 2026-05-11

Adds the fields needed by the trading-journal feature:
- exit_price: filled when the order closes
- fee_usdt: cumulative fees on the trade (placeholder until brokers emit fees)
- notes / tags: user-editable annotations
"""
from alembic import op
import sqlalchemy as sa


revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("exit_price", sa.Float(), nullable=True))
    op.add_column(
        "orders",
        sa.Column(
            "fee_usdt", sa.Float(), nullable=False, server_default=sa.text("0")
        ),
    )
    op.add_column("orders", sa.Column("notes", sa.String(length=2048), nullable=True))
    op.add_column(
        "orders",
        sa.Column(
            "tags", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")
        ),
    )


def downgrade() -> None:
    op.drop_column("orders", "tags")
    op.drop_column("orders", "notes")
    op.drop_column("orders", "fee_usdt")
    op.drop_column("orders", "exit_price")
