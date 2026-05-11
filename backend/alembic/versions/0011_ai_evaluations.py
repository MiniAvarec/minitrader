"""AI deal evaluations (OpenRouter)

Revision ID: 0011
Revises: 0010
Create Date: 2026-05-11

Adds per-user AI settings (encrypted OpenRouter key + chosen 3 models)
and the order_evaluations table that stores each model's review.
"""
from alembic import op
import sqlalchemy as sa


revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_ai_settings",
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("encrypted_openrouter_key", sa.LargeBinary(), nullable=True),
        sa.Column(
            "model_a",
            sa.String(length=128),
            nullable=False,
            server_default="anthropic/claude-opus-4.7",
        ),
        sa.Column(
            "model_b",
            sa.String(length=128),
            nullable=False,
            server_default="openai/gpt-5",
        ),
        sa.Column(
            "model_c",
            sa.String(length=128),
            nullable=False,
            server_default="google/gemini-2.5-pro",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_table(
        "order_evaluations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "order_id",
            sa.Integer(),
            sa.ForeignKey("orders.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column(
            "status", sa.String(length=16), nullable=False, server_default="pending"
        ),
        sa.Column("verdict", sa.String(length=16), nullable=True),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column("summary", sa.String(length=2048), nullable=True),
        sa.Column(
            "strengths", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")
        ),
        sa.Column(
            "weaknesses",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'::json"),
        ),
        sa.Column(
            "suggestions",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'::json"),
        ),
        sa.Column("raw_response", sa.JSON(), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
        sa.Column("cost_usd", sa.Float(), nullable=True),
        sa.Column("error", sa.String(length=512), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_order_evaluations_user_id", "order_evaluations", ["user_id"]
    )
    op.create_index(
        "ix_order_evaluations_order_id", "order_evaluations", ["order_id"]
    )
    op.create_index(
        "ix_order_evaluations_created_at", "order_evaluations", ["created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_order_evaluations_created_at", table_name="order_evaluations")
    op.drop_index("ix_order_evaluations_order_id", table_name="order_evaluations")
    op.drop_index("ix_order_evaluations_user_id", table_name="order_evaluations")
    op.drop_table("order_evaluations")
    op.drop_table("user_ai_settings")
