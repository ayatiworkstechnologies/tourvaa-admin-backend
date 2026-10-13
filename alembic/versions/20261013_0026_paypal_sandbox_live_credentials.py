"""Store separate encrypted PayPal Sandbox and Live credentials."""

from alembic import op
import sqlalchemy as sa

revision = "20261013_0026"
down_revision = "20261012_0025"
branch_labels = None
depends_on = None


def _columns():
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns("payment_settings")}


def upgrade():
    existing = _columns()
    for name in ("sandbox_client_id", "sandbox_secret", "live_client_id", "live_secret"):
        if name not in existing:
            op.add_column("payment_settings", sa.Column(name, sa.Text(), nullable=True))
    # Existing PayPal credentials were configured for the row's existing
    # mode. Preserve them as Sandbox by default so upgrading never disables
    # an established development checkout.
    op.execute("""
        UPDATE payment_settings
        SET sandbox_client_id = public_key,
            sandbox_secret = secret_key
        WHERE provider_name = 'paypal'
          AND (mode IS NULL OR LOWER(mode) IN ('sandbox', 'test'))
          AND sandbox_client_id IS NULL
          AND sandbox_secret IS NULL
    """)


def downgrade():
    existing = _columns()
    for name in ("live_secret", "live_client_id", "sandbox_secret", "sandbox_client_id"):
        if name in existing:
            op.drop_column("payment_settings", name)
