"""add tour_review_comments and tour_versions.change_kind

Section/field-level admin feedback on a tour edit had nowhere to live --
rejecting a version only ever recorded one free-text rejection_reason for
the whole submission. This adds tour_review_comments (section, field_name,
comment, severity, open/resolved status) so the supplier editor can show
feedback inline on the exact step it applies to.

Also adds tour_versions.change_kind, which records whether a pending
version is an ordinary content resubmission or a Supplier Pricing change on
an already-published tour ("repricing_required") -- needed because a
published tour's Tour.status is no longer flipped away from "published"
while a version is under review (see _stage_pending_version), so the
review "kind" has to be recorded somewhere other than Tour.status itself.

Revision ID: 20260804_0055
Revises: 20260803_0054
"""

import sqlalchemy as sa
from alembic import op

revision = "20260804_0055"
down_revision = "20260803_0054"
branch_labels = None
depends_on = None


def _has_column(inspector, table_name, column_name):
    return column_name in {col["name"] for col in inspector.get_columns(table_name)}


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _has_column(inspector, "tour_versions", "change_kind"):
        op.add_column(
            "tour_versions",
            sa.Column("change_kind", sa.String(30), nullable=False, server_default="pending_approval"),
        )

    if "tour_review_comments" not in inspector.get_table_names():
        op.create_table(
            "tour_review_comments",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("tour_id", sa.Integer(), sa.ForeignKey("tours.id"), nullable=False, index=True),
            sa.Column("version_id", sa.Integer(), sa.ForeignKey("tour_versions.id"), nullable=True, index=True),
            sa.Column("section", sa.String(50), nullable=False),
            sa.Column("field_name", sa.String(100), nullable=True),
            sa.Column("comment", sa.Text(), nullable=False),
            sa.Column("severity", sa.String(20), nullable=False, server_default="minor"),
            sa.Column("status", sa.String(20), nullable=False, server_default="open", index=True),
            sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("resolved_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        )


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "tour_review_comments" in inspector.get_table_names():
        op.drop_table("tour_review_comments")
    if _has_column(inspector, "tour_versions", "change_kind"):
        op.drop_column("tour_versions", "change_kind")
