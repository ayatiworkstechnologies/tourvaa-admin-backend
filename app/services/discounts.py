"""Single source of truth for "what's the best currently-active discount for
this tour" - used both to compute the customer-facing highlighted/storefront
price (services.cms._active_discount, routers.public._active_discount_map)
and to compute what's actually charged at booking creation
(services.bookings._resolve_discount), so the two can never diverge.

A discount applies to a tour either directly (discount_scope="tour",
tour_id set), scope-wide across every tour in a category/country
(discount_scope="category"/"country", tour_id left null), or platform-wide
across every tour (discount_scope="all_tours", tour_id left null) - see
app.models.tours.TourDiscount and the admin-wide creation UI at
routers.tours' global-discounts endpoints (services.tours.create_global_discount).
"""
from datetime import datetime, timezone

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.models.tours import TourDiscount, TourDiscountHistory
from app.models.users import User


def _scope_conditions(tour) -> list:
    """SQL conditions for "this discount applies to `tour`": tour-specific,
    platform-wide, or scoped to the tour's category/country (those rows
    leave tour_id null)."""
    conditions = [TourDiscount.tour_id == tour.id, TourDiscount.discount_scope == "all_tours"]
    if tour.category_id:
        conditions.append(and_(
            TourDiscount.tour_id.is_(None),
            TourDiscount.discount_scope == "category",
            TourDiscount.category_id == tour.category_id,
        ))
    if tour.country_id:
        conditions.append(and_(
            TourDiscount.tour_id.is_(None),
            TourDiscount.discount_scope == "country",
            TourDiscount.country_id == tour.country_id,
        ))
    return conditions


def _live_window_conditions(now: datetime) -> list:
    """Started, and not past its end date. An end date is picked as a
    calendar day in the admin (stored as that day's 00:00), so a discount
    "valid till 31 Dec" stays live for all of 31 Dec. Same rule as the
    promo-code check in services.bookings._resolve_discount."""
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return [
        or_(TourDiscount.start_date.is_(None), TourDiscount.start_date <= now),
        or_(TourDiscount.end_date.is_(None), TourDiscount.end_date >= today_start),
    ]


def list_public_offers(session: Session, tour) -> list[dict]:
    """Live discounts a customer can see for `tour` on the tour page and at
    checkout: automatic ones (no code) and promo codes the admin has marked
    "show on website". Private codes are never listed (they still work when
    typed). Exhausted codes (usage limit reached) are left out."""
    if not tour or not tour.id:
        return []
    now = datetime.now(timezone.utc)
    rows = (
        session.query(TourDiscount)
        .filter(
            TourDiscount.status == "active",
            *_live_window_conditions(now),
            or_(*_scope_conditions(tour)),
        )
        .all()
    )
    offers = []
    for d in rows:
        requires_code = bool(d.discount_code)
        if requires_code and not d.show_on_website:
            continue
        if d.usage_limit is not None and (d.used_count or 0) >= d.usage_limit:
            continue
        offers.append({
            "label": d.discount_name,
            "discount_name": d.discount_name,
            "discount_type": d.discount_type,
            "value": float(d.discount_value),
            "requires_code": requires_code,
            "discount_code": d.discount_code if requires_code else None,
            "minimum_booking_amount": float(d.minimum_booking_amount) if d.minimum_booking_amount else None,
            "valid_from": d.start_date.date().isoformat() if d.start_date else None,
            "valid_to": d.end_date.date().isoformat() if d.end_date else None,
        })
    return offers


def _discount_source(session: Session, row: TourDiscount) -> str:
    """Return who owns the discount, independent of the legacy funded_by value.

    Older admin-created discounts were accidentally persisted as SUPPLIER
    because the editor never sent funded_by.  The immutable version-1 history
    is therefore authoritative when available.  funded_by remains the fallback
    for imported/legacy rows without history.
    """
    first = (
        session.query(TourDiscountHistory.changed_by)
        .filter(TourDiscountHistory.discount_id == row.id, TourDiscountHistory.version_number == 1)
        .first()
    )
    if first and first[0]:
        user = session.query(User).filter(User.id == first[0]).first()
        if user:
            from app.services.supplier_scope import is_supplier_user
            return "SUPPLIER" if is_supplier_user(user) else "TOURVAA"
    return "TOURVAA" if (row.funded_by or "SUPPLIER").upper() == "TOURVAA" else "SUPPLIER"


def find_active_discount_stack(session: Session, tour, lock: bool = False, effective_at: datetime | None = None) -> dict[str, TourDiscount | None]:
    """Best automatic supplier and Tourvaa discounts, independently.

    Supplier discounts reduce the supplier price before markup.  Tourvaa
    discounts reduce the resulting storefront price afterwards.  They are not
    competing rows: both may apply to the same booking.
    """
    result: dict[str, TourDiscount | None] = {"supplier": None, "tourvaa": None}
    if not tour or not tour.id:
        return result
    # Promotion windows apply to the booking date, not the departure date.
    # A traveller who books before the offer ends keeps that price even when
    # their tour departs after the offer window. Retain ``effective_at`` in
    # the signature only for compatibility with existing callers.
    del effective_at
    now = datetime.now(timezone.utc)
    query = session.query(TourDiscount).filter(
        TourDiscount.status == "active",
        TourDiscount.discount_code.is_(None),
        *_live_window_conditions(now),
        or_(*_scope_conditions(tour)),
    )
    if lock:
        query = query.with_for_update()
    rows = [r for r in query.all() if r.usage_limit is None or (r.used_count or 0) < r.usage_limit]
    base_price = float(tour.price_start_per_person or 0)

    def score(row: TourDiscount) -> tuple[bool, float]:
        if row.discount_type == "percentage":
            pct = float(row.discount_value)
        else:
            pct = (float(row.discount_value) / base_price * 100) if base_price > 0 else 0
        return row.tour_id == tour.id, min(90.0, max(0.0, pct))

    for source, key in (("SUPPLIER", "supplier"), ("TOURVAA", "tourvaa")):
        owned = [row for row in rows if _discount_source(session, row) == source]
        if owned:
            best = max(owned, key=score)
            if score(best)[1] > 0:
                result[key] = best
    return result


def find_best_discount_row(session: Session, tour, lock: bool = False) -> TourDiscount | None:
    """Best active TourDiscount applicable to `tour`, across all three
    scopes. Highest resulting percent-off wins; ties favor the tour-specific
    discount over a category/country-wide one.

    Pass lock=True when the caller is about to increment used_count (see
    services.bookings._resolve_discount) - without a row lock, two
    concurrent bookings can both read used_count < usage_limit and both
    increment it, letting the code be used more times than usage_limit
    permits (classic check-then-act race)."""
    stack = find_active_discount_stack(session, tour, lock=lock)
    # The public badge always advertises Tourvaa's offer when present;
    # otherwise it falls back to the supplier's original discount.
    return stack["tourvaa"] or stack["supplier"]


def discount_percent_for_display(row: TourDiscount, base_price: float) -> float:
    """Percentage-equivalent for the "Save X% today" badge -- a fixed-amount
    discount is converted against `base_price` the same way a percentage one
    is expressed."""
    if base_price <= 0:
        return 0.0
    pct = float(row.discount_value) if row.discount_type == "percentage" else (float(row.discount_value) / base_price) * 100
    return round(min(90.0, max(0.0, pct)))


def combined_discount_percent(supplier_pct: float, tourvaa_pct: float) -> float:
    """Return the effective saving from the two sequential storefront offers.

    A supplier 10% discount followed by a Tourvaa 15% discount saves 23.5%
    from the original public price, not 15% and not a misleading 25%.
    """
    supplier = min(100.0, max(0.0, float(supplier_pct or 0)))
    tourvaa = min(100.0, max(0.0, float(tourvaa_pct or 0)))
    return round(100 * (1 - (1 - supplier / 100) * (1 - tourvaa / 100)), 2)


def discount_amount_for(row: TourDiscount | None, subtotal: float) -> float:
    """Currency amount to subtract from `subtotal` for this discount row."""
    if not row or subtotal <= 0:
        return 0.0
    if row.discount_type == "percentage":
        return round(subtotal * (float(row.discount_value) / 100), 2)
    return round(min(float(row.discount_value), subtotal), 2)
