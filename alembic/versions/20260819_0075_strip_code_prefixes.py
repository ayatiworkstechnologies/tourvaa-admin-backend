"""strip TVA-BKG-/TVA-CUS- prefixes from stored booking/customer codes

Revision ID: 20260819_0075
Revises: 20260819_0074
"""

import sqlalchemy as sa
from alembic import op

revision = "20260819_0075"
down_revision = "20260819_0074"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    bind.execute(sa.text("UPDATE bookings SET booking_code = REPLACE(booking_code, 'TVA-BKG-', '') WHERE booking_code LIKE 'TVA-BKG-%'"))
    bind.execute(sa.text("UPDATE customers SET customer_code = REPLACE(customer_code, 'TVA-CUS-', '') WHERE customer_code LIKE 'TVA-CUS-%'"))


def downgrade():
    bind = op.get_bind()
    bind.execute(sa.text("UPDATE bookings SET booking_code = CONCAT('TVA-BKG-', booking_code) WHERE booking_code REGEXP '^[0-9]+$'"))
    bind.execute(sa.text("UPDATE customers SET customer_code = CONCAT('TVA-CUS-', customer_code) WHERE customer_code REGEXP '^[0-9]+$'"))
