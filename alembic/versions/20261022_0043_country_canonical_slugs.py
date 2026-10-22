"""Persist stable canonical slugs for public country routes.

Revision ID: 20261022_0043
Revises: 20261022_0042
"""

import re

from alembic import op
import sqlalchemy as sa


revision = "20261022_0043"
down_revision = "20261022_0042"
branch_labels = None
depends_on = None


def _slug(value: str) -> str:
    result = re.sub(r"[^a-z0-9]+", "-", (value or "").lower()).strip("-")
    return result or "country"


def upgrade() -> None:
    op.add_column("countries", sa.Column("slug", sa.String(length=150), nullable=True))
    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id, country_name FROM countries ORDER BY id")).mappings()
    used: set[str] = set()
    for row in rows:
        base = _slug(row["country_name"])
        candidate = base
        suffix = 2
        while candidate in used:
            candidate = f"{base}-{suffix}"
            suffix += 1
        used.add(candidate)
        bind.execute(sa.text("UPDATE countries SET slug = :slug WHERE id = :id"), {"slug": candidate, "id": row["id"]})
    op.alter_column("countries", "slug", existing_type=sa.String(length=150), nullable=False)
    op.create_index("ix_countries_slug", "countries", ["slug"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_countries_slug", table_name="countries")
    op.drop_column("countries", "slug")
