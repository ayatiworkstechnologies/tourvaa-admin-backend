"""Add retry scheduling and worker leases to notification deliveries.

Revision ID: 20261022_0040
Revises: 20261022_0039
"""

from alembic import op
import sqlalchemy as sa


revision = "20261022_0040"
down_revision = "20261022_0039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("notification_deliveries") as batch_op:
        batch_op.add_column(sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("lease_token", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("smtp_accepted_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("exhausted_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.create_index("ix_notification_deliveries_next_attempt_at", ["next_attempt_at"])
        batch_op.create_index("ix_notification_deliveries_lease_token", ["lease_token"])
        batch_op.create_index("ix_notification_deliveries_lease_expires_at", ["lease_expires_at"])


def downgrade() -> None:
    with op.batch_alter_table("notification_deliveries") as batch_op:
        batch_op.drop_index("ix_notification_deliveries_lease_expires_at")
        batch_op.drop_index("ix_notification_deliveries_lease_token")
        batch_op.drop_index("ix_notification_deliveries_next_attempt_at")
        batch_op.drop_column("exhausted_at")
        batch_op.drop_column("smtp_accepted_at")
        batch_op.drop_column("lease_expires_at")
        batch_op.drop_column("lease_token")
        batch_op.drop_column("next_attempt_at")
