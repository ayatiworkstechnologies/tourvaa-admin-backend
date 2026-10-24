"""Add payment summaries to existing booking email templates.

Revision ID: 20261024_0049
Revises: 20261023_0048
"""

from alembic import op


revision = "20261024_0049"
down_revision = "20261023_0048"
branch_labels = None
depends_on = None


def upgrade():
    # Do not replace administrator-authored copy. Add the supported placeholder
    # only when it is absent, so the service can render the authoritative
    # booking payment summary for both stock and customised templates.
    op.execute(
        "UPDATE email_templates "
        "SET body = CONCAT(RTRIM(body), '\n\n{{payment_summary}}') "
        "WHERE `key` IN ('booking_confirmation', 'booking_confirmed', 'booking_status_update') "
        "AND body NOT LIKE '%{{payment_summary}}%'"
    )
    op.execute(
        "UPDATE email_templates "
        "SET body = CONCAT(RTRIM(body), '\nRemaining balance: {{currency}} {{amount_pending}}') "
        "WHERE `key` = 'deposit_payment_received' "
        "AND body NOT LIKE '%{{amount_pending}}%'"
    )


def downgrade():
    # The appended placeholder may coexist with administrator edits after the
    # migration, so downgrade intentionally leaves template content intact.
    pass
