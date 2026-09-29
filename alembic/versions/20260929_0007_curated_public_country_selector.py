"""Configure the initial public country selector set.

The country master remains complete for CMS administration.  ``status`` is
the public-selector switch: the public countries endpoint returns only active
rows, so an administrator can later enable another country without a deploy.

Revision ID: 20260929_0007
Revises: 20260925_0006
"""

from alembic import op
import sqlalchemy as sa


revision = "20260929_0007"
down_revision = "20260925_0006"
branch_labels = None
depends_on = None


PUBLIC_COUNTRY_CODES = (
    "LU", "SG", "IE", "QA", "CH", "NO", "AE", "US", "DK", "NL", "IS",
    "AU", "SE", "AT", "BE", "DE", "CA", "FI", "IL", "GB", "NZ", "FR",
    "JP", "KR", "IN", "CN",
)


def upgrade():
    bind = op.get_bind()
    bind.execute(sa.text("UPDATE countries SET status = 'inactive'"))
    bind.execute(
        sa.text("UPDATE countries SET status = 'active' WHERE country_code IN :codes")
        .bindparams(sa.bindparam("codes", expanding=True)),
        {"codes": list(PUBLIC_COUNTRY_CODES)},
    )


def downgrade():
    # Revert to the historical behaviour where every seeded country appeared
    # in the public selector.
    op.execute("UPDATE countries SET status = 'active'")
