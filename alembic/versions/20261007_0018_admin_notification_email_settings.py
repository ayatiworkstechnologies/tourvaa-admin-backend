"""Add configured admin notification To, CC and BCC recipients."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "20261007_0018"
down_revision = "20261007_0017"
branch_labels = None
depends_on = None

def upgrade():
    existing = {c["name"] for c in inspect(op.get_bind()).get_columns("smtp_settings")}
    for name in ("admin_notification_to", "admin_notification_cc", "admin_notification_bcc"):
        if name not in existing:
            op.add_column("smtp_settings", sa.Column(name, sa.Text(), nullable=True))

def downgrade():
    with op.batch_alter_table("smtp_settings") as batch:
        batch.drop_column("admin_notification_bcc")
        batch.drop_column("admin_notification_cc")
        batch.drop_column("admin_notification_to")
