"""seed any new built-in strategies

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-10

The 0002 migration seeded every YAML in app/signals/dsl/builtins/ at the time
that migration ran. When we ship additional built-in strategies later, the
0002 INSERT won't fire again for existing DBs, so the new YAMLs would never
land. This revision re-runs the same idempotent (WHERE NOT EXISTS) seed.
"""
from datetime import datetime, timezone
from pathlib import Path

from alembic import op
import sqlalchemy as sa


revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    builtins_dir = Path(__file__).resolve().parent.parent.parent / "app" / "signals" / "dsl" / "builtins"
    bind = op.get_bind()
    now = datetime.now(timezone.utc)
    for path in sorted(builtins_dir.glob("*.yaml")):
        slug = path.stem
        text = path.read_text()
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
    # We don't unseed — built-ins are content, not schema, and may have been
    # cloned by users. Removing the row would break those clones via FK
    # ON DELETE SET NULL (parent_id) but is still preserved here for symmetry.
    pass
