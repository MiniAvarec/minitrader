"""composite indexes for list-by-user-recent queries

Revision ID: 0009
Revises: 0008
Create Date: 2026-05-11

The /signals and /orders list endpoints filter by user_id and order by
created_at DESC. Add composite indexes that cover the common access pattern.
"""
from alembic import op


revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_signals_user_created",
        "signals",
        ["user_id", "created_at"],
    )
    op.create_index(
        "ix_orders_user_created",
        "orders",
        ["user_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_orders_user_created", table_name="orders")
    op.drop_index("ix_signals_user_created", table_name="signals")
