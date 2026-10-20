"""Apply storefront markup after supplier commission.

Revision ID: 20261020_0033
Revises: 20261020_0032
"""
from decimal import Decimal, ROUND_HALF_UP

from alembic import op
import sqlalchemy as sa

revision = "20261020_0033"
down_revision = "20261020_0032"
branch_labels = None
depends_on = None


def _money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def upgrade() -> None:
    bind = op.get_bind()
    # ``key`` is reserved syntax in MySQL. Quote both settings columns so the
    # data migration works on the production MySQL database as well as local
    # development databases.
    default = bind.execute(sa.text("SELECT `value` FROM app_settings WHERE `key` = 'default_admin_markup_percentage' LIMIT 1")).scalar() or "0"
    rows = bind.execute(sa.text("""
        SELECT p.id, p.adult_price, p.child_price, p.commission_percentage,
               p.admin_markup_value, t.admin_markup_percentage AS tour_markup
        FROM tour_pricing p LEFT JOIN tours t ON t.id = p.tour_id
    """)).mappings().all()
    for row in rows:
        markup = Decimal(str(row["admin_markup_value"] if row["admin_markup_value"] is not None else row["tour_markup"] if row["tour_markup"] is not None else default))
        commission = Decimal(str(row["commission_percentage"] or 0))
        multiplier = (Decimal("1") - commission / Decimal("100")) * (Decimal("1") + markup / Decimal("100"))
        bind.execute(sa.text("UPDATE tour_pricing SET storefront_adult_price = :adult, storefront_child_price = :child, final_price = :adult WHERE id = :id"), {
            "id": row["id"], "adult": _money(Decimal(str(row["adult_price"] or 0)) * multiplier), "child": _money(Decimal(str(row["child_price"] or 0)) * multiplier),
        })


def downgrade() -> None:
    # The former formula is intentionally not restored automatically: prices
    # changed by this business-rule migration must not be silently reversed.
    pass
