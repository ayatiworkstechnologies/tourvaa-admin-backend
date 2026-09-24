"""Allow long web push endpoints.

Push service URLs (notably Windows/Edge WNS ones) can exceed the old
VARCHAR(500) endpoint column, which made those subscriptions fail with
"Data too long". MySQL can't unique-index a longer utf8mb4 column, so the
endpoint becomes TEXT and uniqueness moves to a SHA-256 endpoint_hash.

Revision ID: 20260924_0001
Revises: 20260923_0004
Create Date: 2026-09-24
"""
import hashlib

from alembic import op
import sqlalchemy as sa

revision = "20260924_0001"
down_revision = "20260923_0004"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c["name"] for c in insp.get_columns("push_subscriptions")}
    if "endpoint_hash" not in cols:
        op.add_column("push_subscriptions", sa.Column("endpoint_hash", sa.String(64), nullable=True))
    rows = bind.execute(sa.text("SELECT id, endpoint FROM push_subscriptions")).fetchall()
    for row_id, endpoint in rows:
        bind.execute(
            sa.text("UPDATE push_subscriptions SET endpoint_hash = :h WHERE id = :id"),
            {"h": hashlib.sha256(endpoint.encode()).hexdigest(), "id": row_id},
        )
    if "uq_push_endpoint" in {c["name"] for c in insp.get_unique_constraints("push_subscriptions")}:
        op.drop_constraint("uq_push_endpoint", "push_subscriptions", type_="unique")
    op.alter_column("push_subscriptions", "endpoint", existing_type=sa.String(500), type_=sa.Text(), existing_nullable=False)
    op.alter_column("push_subscriptions", "endpoint_hash", existing_type=sa.String(64), nullable=False)
    op.create_unique_constraint("uq_push_endpoint_hash", "push_subscriptions", ["endpoint_hash"])


def downgrade():
    op.drop_constraint("uq_push_endpoint_hash", "push_subscriptions", type_="unique")
    op.alter_column("push_subscriptions", "endpoint", existing_type=sa.Text(), type_=sa.String(500), existing_nullable=False)
    op.create_unique_constraint("uq_push_endpoint", "push_subscriptions", ["endpoint"])
    op.drop_column("push_subscriptions", "endpoint_hash")
