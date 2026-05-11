"""app_settings table for system-wide integration keys

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-11

Adds a single `app_settings` key/value table storing encrypted third-party API
credentials (Finnhub, CryptoPanic, CryptoCompare, NewsData.io, Reddit UA).
Values use the same Fernet key as user exchange credentials.
"""
from alembic import op
import sqlalchemy as sa


revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("encrypted_value", sa.LargeBinary(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("app_settings")
