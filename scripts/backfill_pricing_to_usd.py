"""One-off backfill: normalize every Tour/TourPricing row already stored in a
non-USD currency to USD, the platform's single accounting currency.

Context: TourPricing.adult_price/child_price/supplier_price and
Tour.booking_deposit/service_fee used to be persisted verbatim in whatever
currency an admin/supplier picked in the form (see app/services/tours.py's
_normalize_pricing_to_usd and app/services/cms.py's save_tour, which now
convert on every future write). This script fixes the rows written before
that change, using the same live/fallback FX rates
(app/services/currency.convert_amount) so historical and future data agree.

Also recomputes each affected tour's derived storefront/supplier_final
pricing fields and Tour.price_start_per_person, since those were computed
from the pre-conversion (wrong-currency) numbers.

Usage:
    python -m scripts.backfill_pricing_to_usd            # dry run (default)
    python -m scripts.backfill_pricing_to_usd --apply    # actually commit
"""

from __future__ import annotations

import argparse
from decimal import Decimal

import app.main  # noqa: F401 - registers every SQLAlchemy model before querying
from app.database import SessionLocal
from app.models.cms import Tour
from app.models.tours import TourPricing
from app.services.currency import BASE_CURRENCY, convert_amount, normalize_currency
from app.services.tours import recalculate_price_start


def _apply_markup(markup_type: str, markup_value: float, base: float) -> float:
    if markup_type == "percentage":
        return round(max(0.0, base * (1 + markup_value / 100)), 2)
    return round(max(0.0, base + markup_value), 2)


def backfill(db, apply: bool) -> None:
    slab_rows = db.query(TourPricing).filter(TourPricing.currency != BASE_CURRENCY).all()
    print(f"Pricing slabs to convert: {len(slab_rows)}")
    affected_tour_ids: set[int] = set()
    for slab in slab_rows:
        entered = normalize_currency(slab.currency, BASE_CURRENCY)
        before = (slab.adult_price, slab.child_price, slab.supplier_price)
        for field in ("adult_price", "child_price", "supplier_price"):
            value = getattr(slab, field, None)
            if value:
                converted, _, _ = convert_amount(Decimal(str(value)), entered, BASE_CURRENCY)
                setattr(slab, field, float(converted))
        slab.final_price = slab.adult_price
        commission = float(slab.commission_percentage or 0)
        slab.supplier_final_adult_price = round(max(0.0, slab.adult_price * (1 - commission / 100)), 2)
        slab.supplier_final_child_price = round(max(0.0, slab.child_price * (1 - commission / 100)), 2)
        slab.storefront_adult_price = _apply_markup(slab.admin_markup_type, float(slab.admin_markup_value or 0), slab.adult_price)
        slab.storefront_child_price = _apply_markup(slab.admin_markup_type, float(slab.admin_markup_value or 0), slab.child_price)
        slab.currency = BASE_CURRENCY
        affected_tour_ids.add(slab.tour_id)
        print(f"  slab #{slab.id} (tour {slab.tour_id}) {entered} {before} -> USD "
              f"({slab.adult_price}, {slab.child_price}, {slab.supplier_price})")

    tour_rows = db.query(Tour).filter(Tour.currency != BASE_CURRENCY).all()
    print(f"Tours to convert: {len(tour_rows)}")
    for tour in tour_rows:
        entered = normalize_currency(tour.currency, BASE_CURRENCY)
        before = (tour.booking_deposit, tour.service_fee)
        for field in ("booking_deposit", "service_fee"):
            value = getattr(tour, field, None)
            if value:
                converted, _, _ = convert_amount(Decimal(str(value)), entered, BASE_CURRENCY)
                setattr(tour, field, float(converted))
        tour.currency = BASE_CURRENCY
        affected_tour_ids.add(tour.id)
        print(f"  tour #{tour.id} {entered} {before} -> USD ({tour.booking_deposit}, {tour.service_fee})")

    for tour_id in affected_tour_ids:
        recalculate_price_start(db, tour_id)

    if apply:
        db.commit()
        print(f"\nCommitted. {len(slab_rows)} slabs, {len(tour_rows)} tours, "
              f"{len(affected_tour_ids)} tours re-priced.")
    else:
        db.rollback()
        print("\nDry run only - no changes committed. Re-run with --apply to persist.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Actually commit the conversion (default: dry run)")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        backfill(db, apply=args.apply)
    finally:
        db.close()


if __name__ == "__main__":
    main()
