"""tour/agent/affiliate codes -> plain sequence; booking code -> TOURVAA-BOOKING-#####

Revision ID: 20260819_0076
Revises: 20260819_0075
"""

import sqlalchemy as sa
from alembic import op

revision = "20260819_0076"
down_revision = "20260819_0075"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    bind.execute(sa.text("UPDATE tours SET tour_code = LPAD(id, 5, '0') WHERE tour_code IS NOT NULL"))
    bind.execute(sa.text("UPDATE agents SET agent_code = LPAD(id, 5, '0') WHERE agent_code IS NOT NULL"))
    bind.execute(sa.text("UPDATE affiliates SET affiliate_code = LPAD(id, 5, '0') WHERE affiliate_code IS NOT NULL"))
    bind.execute(sa.text("UPDATE bookings SET booking_code = CONCAT('TOURVAA-BOOKING-', LPAD(id, 5, '0')) WHERE booking_code IS NOT NULL"))


def downgrade():
    bind = op.get_bind()
    bind.execute(sa.text("UPDATE tours SET tour_code = CONCAT('TVA-TOUR-', tour_code) WHERE tour_code REGEXP '^[0-9]+$'"))
    bind.execute(sa.text("UPDATE agents SET agent_code = CONCAT('TVA-AGT-', agent_code) WHERE agent_code REGEXP '^[0-9]+$'"))
    bind.execute(sa.text("UPDATE affiliates SET affiliate_code = CONCAT('TVA-AFF-', affiliate_code) WHERE affiliate_code REGEXP '^[0-9]+$'"))
    bind.execute(sa.text("UPDATE bookings SET booking_code = LPAD(id, 6, '0') WHERE booking_code LIKE 'TOURVAA-BOOKING-%'"))
