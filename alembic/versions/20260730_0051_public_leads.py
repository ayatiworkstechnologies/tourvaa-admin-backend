"""add newsletter_subscribers and contact_messages tables

Public site newsletter signup and contact form used to only send an email
to support -- if the send failed, or nobody checked the inbox, the lead
was gone. This gives both a durable row.

Revision ID: 20260730_0051
Revises: 20260728_0050
"""

import sqlalchemy as sa
from alembic import op

revision = "20260730_0051"
down_revision = "20260728_0050"
branch_labels = None
depends_on = None


def _has_table(inspector, table_name):
    return table_name in inspector.get_table_names()


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _has_table(inspector, "newsletter_subscribers"):
        op.create_table(
            "newsletter_subscribers",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("email", sa.String(length=255), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_newsletter_subscribers_id"), "newsletter_subscribers", ["id"], unique=False)
        op.create_index(op.f("ix_newsletter_subscribers_email"), "newsletter_subscribers", ["email"], unique=True)

    if not _has_table(inspector, "contact_messages"):
        op.create_table(
            "contact_messages",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(length=150), nullable=False),
            sa.Column("email", sa.String(length=255), nullable=False),
            sa.Column("phone", sa.String(length=30), nullable=True),
            sa.Column("enquiry_type", sa.String(length=50), nullable=False, server_default="General enquiry"),
            sa.Column("subject", sa.String(length=200), nullable=False),
            sa.Column("message", sa.Text(), nullable=False),
            sa.Column("is_replied", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_contact_messages_id"), "contact_messages", ["id"], unique=False)
        op.create_index(op.f("ix_contact_messages_email"), "contact_messages", ["email"], unique=False)


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_table(inspector, "contact_messages"):
        op.drop_index(op.f("ix_contact_messages_email"), table_name="contact_messages")
        op.drop_index(op.f("ix_contact_messages_id"), table_name="contact_messages")
        op.drop_table("contact_messages")

    if _has_table(inspector, "newsletter_subscribers"):
        op.drop_index(op.f("ix_newsletter_subscribers_email"), table_name="newsletter_subscribers")
        op.drop_index(op.f("ix_newsletter_subscribers_id"), table_name="newsletter_subscribers")
        op.drop_table("newsletter_subscribers")
