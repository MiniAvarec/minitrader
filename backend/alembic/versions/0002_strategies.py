"""strategies

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-10

"""
from datetime import datetime, timezone
from pathlib import Path

from alembic import op
import sqlalchemy as sa


revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ---- new tables ----
    op.create_table(
        "strategies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("parent_id", sa.Integer(), sa.ForeignKey("strategies.id", ondelete="SET NULL"), nullable=True),
        sa.Column("slug", sa.String(64), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("description", sa.String(2048), server_default=""),
        sa.Column("code", sa.String(16384), nullable=False),
        sa.Column("is_builtin", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("version", sa.Integer(), server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "slug", name="uq_strategy_user_slug"),
    )
    op.create_index("ix_strategies_user_id", "strategies", ["user_id"])
    op.create_index("ix_strategies_slug", "strategies", ["slug"])

    op.create_table(
        "user_strategy_selections",
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("symbol", sa.String(32), primary_key=True),
        sa.Column(
            "strategy_id",
            sa.Integer(),
            sa.ForeignKey("strategies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "ix_user_strategy_selections_strategy_id",
        "user_strategy_selections",
        ["strategy_id"],
    )

    # ---- amend signals: user_id, strategy_id ----
    op.add_column(
        "signals",
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
    op.add_column(
        "signals",
        sa.Column(
            "strategy_id",
            sa.Integer(),
            sa.ForeignKey("strategies.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_signals_user_id", "signals", ["user_id"])
    op.create_index("ix_signals_strategy_id", "signals", ["strategy_id"])

    # ---- seed built-in strategies from disk ----
    builtins_dir = Path(__file__).resolve().parent.parent.parent / "app" / "signals" / "dsl" / "builtins"
    bind = op.get_bind()
    now = datetime.now(timezone.utc)
    for path in sorted(builtins_dir.glob("*.yaml")):
        slug = path.stem
        text = path.read_text()
        # Extract name from YAML (cheap parse to avoid alembic <-> pyyaml import order issues
        # at migration time — we already require pyyaml in the runtime image).
        try:
            import yaml

            doc = yaml.safe_load(text) or {}
            name = doc.get("name") or slug
            description = doc.get("description") or ""
        except Exception:
            name, description = slug, ""
        bind.execute(
            sa.text(
                """
                INSERT INTO strategies (user_id, slug, name, description, code, is_builtin, version, created_at, updated_at)
                SELECT NULL, CAST(:slug AS varchar), :name, :description, :code, true, 1, :ts, :ts
                WHERE NOT EXISTS (
                    SELECT 1 FROM strategies WHERE user_id IS NULL AND slug = CAST(:slug AS varchar)
                )
                """
            ),
            {
                "slug": slug,
                "name": name,
                "description": description,
                "code": text,
                "ts": now,
            },
        )


def downgrade() -> None:
    op.drop_index("ix_signals_strategy_id", table_name="signals")
    op.drop_index("ix_signals_user_id", table_name="signals")
    op.drop_column("signals", "strategy_id")
    op.drop_column("signals", "user_id")
    op.drop_index("ix_user_strategy_selections_strategy_id", table_name="user_strategy_selections")
    op.drop_table("user_strategy_selections")
    op.drop_index("ix_strategies_slug", table_name="strategies")
    op.drop_index("ix_strategies_user_id", table_name="strategies")
    op.drop_table("strategies")
