"""Revoke customer-invoice access from the Supplier role.

Customer invoices contain Tourvaa's markup. Suppliers use their scoped
earnings and payout records instead.

Revision ID: 20260925_0006
Revises: 20260925_0005
Create Date: 2026-09-25
"""

from alembic import op
import sqlalchemy as sa


revision = "20260925_0006"
down_revision = "20260925_0005"
branch_labels = None
depends_on = None


INVOICE_PERMISSION_SLUGS = ("view-invoices", "invoices.view", "invoices.download")


def _ids(bind):
    role_id = bind.execute(
        sa.text("SELECT id FROM roles WHERE slug = :slug"),
        {"slug": "supplier"},
    ).scalar()
    permission_ids = list(
        bind.execute(
            sa.text("SELECT id FROM permissions WHERE slug IN :slugs").bindparams(
                sa.bindparam("slugs", expanding=True)
            ),
            {"slugs": INVOICE_PERMISSION_SLUGS},
        ).scalars()
    )
    return role_id, permission_ids


def upgrade():
    bind = op.get_bind()
    role_id, permission_ids = _ids(bind)
    if role_id is None or not permission_ids:
        return
    bind.execute(
        sa.text(
            "DELETE FROM role_permissions "
            "WHERE role_id = :role_id AND permission_id IN :permission_ids"
        ).bindparams(sa.bindparam("permission_ids", expanding=True)),
        {"role_id": role_id, "permission_ids": permission_ids},
    )


def downgrade():
    bind = op.get_bind()
    role_id, permission_ids = _ids(bind)
    if role_id is None:
        return
    for permission_id in permission_ids:
        exists = bind.execute(
            sa.text(
                "SELECT 1 FROM role_permissions "
                "WHERE role_id = :role_id AND permission_id = :permission_id"
            ),
            {"role_id": role_id, "permission_id": permission_id},
        ).first()
        if not exists:
            bind.execute(
                sa.text(
                    "INSERT INTO role_permissions (role_id, permission_id) "
                    "VALUES (:role_id, :permission_id)"
                ),
                {"role_id": role_id, "permission_id": permission_id},
            )
