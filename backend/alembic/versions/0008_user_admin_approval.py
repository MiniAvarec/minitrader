"""user admin + approval flags

Revision ID: 0008
Revises: 0007
Create Date: 2026-05-11

Adds is_admin / is_approved to users. Existing users are grandfathered as
approved (so deployments upgrading in place keep working). The user matching
the ADMIN_EMAIL env var (if any) is promoted to admin.
"""
import os

from alembic import op
import sqlalchemy as sa


revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "is_admin",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "is_approved",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    # Grandfather every existing user — anyone who already had an account
    # before this migration ran is implicitly approved.
    op.execute("UPDATE users SET is_approved = true")

    admin_email = (os.environ.get("ADMIN_EMAIL") or "").strip().lower()
    if admin_email:
        op.execute(
            sa.text("UPDATE users SET is_admin = true WHERE lower(email) = :email").bindparams(
                email=admin_email
            )
        )


def downgrade() -> None:
    op.drop_column("users", "is_approved")
    op.drop_column("users", "is_admin")
