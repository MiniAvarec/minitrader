"""market sentiment + reddit hype tables

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-11

Adds:
  - `market_sentiment` time series (Fear & Greed Index and similar regime scores).
  - `reddit_hype` table holding the latest hype score per symbol.
"""
from alembic import op
import sqlalchemy as sa


revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "market_sentiment",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("classification", sa.String(64), nullable=True),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_market_sentiment_source", "market_sentiment", ["source"])
    op.create_index("ix_market_sentiment_fetched_at", "market_sentiment", ["fetched_at"])

    op.create_table(
        "reddit_hype",
        sa.Column("symbol", sa.String(32), primary_key=True),
        sa.Column("score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("mentions_60m", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("upvotes_60m", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_reddit_hype_updated_at", "reddit_hype", ["updated_at"])


def downgrade() -> None:
    op.drop_index("ix_reddit_hype_updated_at", table_name="reddit_hype")
    op.drop_table("reddit_hype")
    op.drop_index("ix_market_sentiment_fetched_at", table_name="market_sentiment")
    op.drop_index("ix_market_sentiment_source", table_name="market_sentiment")
    op.drop_table("market_sentiment")
