"""backfill verification for approved legacy suppliers

Revision ID: 20260724_0036
Revises: 20260724_0035
"""

from alembic import op


revision = "20260724_0036"
down_revision = "20260724_0035"
branch_labels = None
depends_on = None


def upgrade():
    # Earlier releases could approve and activate a supplier before the
    # users.email_verified fields existed. Keep the approval guard strict and
    # normalize only those legacy records that are already fully operational.
    op.execute(
        """
        UPDATE users AS u
        INNER JOIN suppliers AS s ON s.user_id = u.id
        SET u.email_verified = TRUE,
            u.email_verified_at = COALESCE(
                u.email_verified_at,
                u.password_created_at,
                u.created_at,
                CURRENT_TIMESTAMP
            ),
            u.approval_status = 'APPROVED'
        WHERE u.user_type = 'SUPPLIER'
          AND UPPER(s.approval_status) = 'APPROVED'
          AND LOWER(s.status) = 'active'
          AND u.account_status = 'ACTIVE'
          AND u.is_active = TRUE
          AND u.password IS NOT NULL
          AND (u.email_verified = FALSE OR u.email_verified_at IS NULL)
        """
    )


def downgrade():
    # Data normalization is intentionally irreversible: an approved supplier
    # may have legitimately verified their email after this migration ran.
    pass
