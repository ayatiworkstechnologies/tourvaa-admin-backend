"""Single source of truth for "what's the best currently-active discount for
this tour" - used both to compute the customer-facing highlighted/storefront
price (services.cms._active_discount, routers.public._active_discount_map)
and to compute what's actually charged at booking creation
(services.bookings._resolve_discount), so the two can never diverge.

A discount applies to a tour either directly (discount_scope="tour",
tour_id set) or scope-wide across every tour in a category/country
(discount_scope="category"/"country", tour_id left null) - see
app.models.tours.TourDiscount.
"""
from datetime import datetime, timezone

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.models.tours import TourDiscount


def find_best_discount_row(session: Session, tour) -> TourDiscount | None:
    """Best active TourDiscount applicable to `tour`, across all three
    scopes. Highest resulting percent-off wins; ties favor the tour-specific
    discount over a category/country-wide one."""
    if not tour or not tour.id:
        return None
    now = datetime.now(timezone.utc)
    scope_conditions = [TourDiscount.tour_id == tour.id]
    if tour.category_id:
        scope_conditions.append(and_(
            TourDiscount.tour_id.is_(None),
            TourDiscount.discount_scope == "category",
            TourDiscount.category_id == tour.category_id,
        ))
    if tour.country_id:
        scope_conditions.append(and_(
            TourDiscount.tour_id.is_(None),
            TourDiscount.discount_scope == "country",
            TourDiscount.country_id == tour.country_id,
        ))
    rows = (
        session.query(TourDiscount)
        .filter(
            TourDiscount.status == "active",
            or_(TourDiscount.start_date.is_(None), TourDiscount.start_date <= now),
            or_(TourDiscount.end_date.is_(None), TourDiscount.end_date >= now),
            or_(*scope_conditions),
        )
        .all()
    )
    if not rows:
        return None

    base_price = float(tour.price_start_per_person or 0)

    def pct_for(row: TourDiscount) -> float:
        if base_price <= 0:
            return 0.0
        pct = float(row.discount_value) if row.discount_type == "percentage" else (float(row.discount_value) / base_price) * 100
        return round(min(90.0, max(0.0, pct)), 2)

    best = max(rows, key=lambda row: (row.tour_id == tour.id, pct_for(row)))
    return best if pct_for(best) > 0 else None


def discount_percent_for_display(row: TourDiscount, base_price: float) -> float:
    """Percentage-equivalent for the "Save X% today" badge -- a fixed-amount
    discount is converted against `base_price` the same way a percentage one
    is expressed."""
    if base_price <= 0:
        return 0.0
    pct = float(row.discount_value) if row.discount_type == "percentage" else (float(row.discount_value) / base_price) * 100
    return round(min(90.0, max(0.0, pct)))


def discount_amount_for(row: TourDiscount | None, subtotal: float) -> float:
    """Currency amount to subtract from `subtotal` for this discount row."""
    if not row or subtotal <= 0:
        return 0.0
    if row.discount_type == "percentage":
        return round(subtotal * (float(row.discount_value) / 100), 2)
    return round(min(float(row.discount_value), subtotal), 2)
