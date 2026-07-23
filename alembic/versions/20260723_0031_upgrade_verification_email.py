"""upgrade verification email copy

Revision ID: 20260723_0031
Revises: 20260723_0030
"""

from alembic import op
import sqlalchemy as sa


revision = "20260723_0031"
down_revision = "20260723_0030"
branch_labels = None
depends_on = None

OLD_SUBJECT = "Verify your Tourvaa email"
OLD_BODY = (
    "Hi {{name}}, please verify your email address to complete your account setup. "
    "This link expires in 24 hours.\n\nVerification link: {{verification_url}}"
)
NEW_SUBJECT = "Verify your Tourvaa email and create your password"
NEW_BODY = (
    "Thanks for registering with Tourvaa.\n\n"
    "Use the secure button below to verify your email and create your password. "
    "After that, your account will be sent to our team for activation.\n\n"
    "For your security, this single-use link expires in 24 hours."
)


def upgrade():
    email_templates = sa.table(
        "email_templates",
        sa.column("key", sa.String()),
        sa.column("subject", sa.String()),
        sa.column("body", sa.Text()),
    )
    op.execute(
        email_templates.update()
        .where(email_templates.c.key == "email_verification")
        .where(email_templates.c.subject == OLD_SUBJECT)
        .values(subject=NEW_SUBJECT, body=NEW_BODY)
    )


def downgrade():
    email_templates = sa.table(
        "email_templates",
        sa.column("key", sa.String()),
        sa.column("subject", sa.String()),
        sa.column("body", sa.Text()),
    )
    op.execute(
        email_templates.update()
        .where(email_templates.c.key == "email_verification")
        .where(email_templates.c.subject == NEW_SUBJECT)
        .values(subject=OLD_SUBJECT, body=OLD_BODY)
    )
