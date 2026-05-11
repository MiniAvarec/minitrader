"""trading intelligence run tables

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-11
"""
from alembic import op
import sqlalchemy as sa


revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def _run_table(name: str, *extra: sa.Column) -> None:
    op.create_table(
        name,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="completed"),
        sa.Column("input", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        *extra,
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(f"ix_{name}_user_id", name, ["user_id"])
    op.create_index(f"ix_{name}_created_at", name, ["created_at"])


def upgrade() -> None:
    _run_table(
        "portfolio_rebalance_runs",
        sa.Column("order_ids", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
    )
    _run_table(
        "execution_route_quotes",
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id"), nullable=True),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
    )
    _run_table(
        "optimizer_runs",
        sa.Column("strategy_id", sa.Integer(), sa.ForeignKey("strategies.id", ondelete="SET NULL"), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    _run_table("scenario_runs")


def downgrade() -> None:
    op.drop_table("scenario_runs")
    op.drop_table("optimizer_runs")
    op.drop_table("execution_route_quotes")
    op.drop_table("portfolio_rebalance_runs")
