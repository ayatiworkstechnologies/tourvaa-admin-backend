"""suppliers/users -> normalize approval_status to lowercase

Suppliers stored approval_status upper-case ("PENDING", "APPROVED", ...)
while agents and affiliates already stored it lower-case ("pending",
"approved", ...). Several read paths (dashboard alerts, admin reports)
compared against the lower-case literal directly without normalizing case
first, so those checks silently never matched for suppliers. This makes
storage consistent with the majority convention so those comparisons work,
and application code no longer needs to special-case suppliers' casing.

Revision ID: 20260821_0078
Revises: 20260821_0077
"""

import sqlalchemy as sa
from alembic import op

revision = "20260821_0078"
down_revision = "20260821_0077"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    bind.execute(sa.text("UPDATE suppliers SET approval_status = LOWER(approval_status) WHERE approval_status IS NOT NULL"))
    # users.approval_status is only ever upper-case for SUPPLIER/AFFILIATE
    # account types ("PENDING"/"NOT_REQUIRED"/"MORE_INFORMATION_REQUIRED");
    # every other user type already keeps the model's lower-case default.
    bind.execute(sa.text("UPDATE users SET approval_status = LOWER(approval_status) WHERE approval_status IS NOT NULL"))


def downgrade():
    # Casing-only normalization; the prior mixed-case values are not
    # meaningfully recoverable (and comparisons that previously relied on
    # case-insensitive matching keep working either way), so downgrade is a
    # no-op rather than reintroducing inconsistent casing.
    pass
