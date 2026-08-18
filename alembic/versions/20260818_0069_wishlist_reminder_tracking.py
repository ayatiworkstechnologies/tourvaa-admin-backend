"""add customer_wishlist_items.last_reminder_sent_at

Client feedback ("Pricing & Tours Feedback" doc, page 15): "If a User adds
the Tour to a wishlist, we need to able to reminder emails in intervals of
time i.e. every week" - this column tracks when a wishlist item last had a
reminder sent, so the sweep in services.wishlist_reminders can resend at a
weekly cadence without duplicating within the same week.

Revision ID: 20260818_0069
Revises: 20260818_0068
"""

import sqlalchemy as sa
from alembic import op

revision = "20260818_0069"
down_revision = "20260818_0068"
branch_labels = None
depends_on = None


def _has_column(inspector, table_name, column_name):
    return column_name in {col["name"] for col in inspector.get_columns(table_name)}


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not _has_column(inspector, "customer_wishlist_items", "last_reminder_sent_at"):
        op.add_column("customer_wishlist_items", sa.Column("last_reminder_sent_at", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _has_column(inspector, "customer_wishlist_items", "last_reminder_sent_at"):
        op.drop_column("customer_wishlist_items", "last_reminder_sent_at")
