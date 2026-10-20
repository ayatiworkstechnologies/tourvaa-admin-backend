"""Tourvaa admin markup: which percentage applies to a pricing slab.

Resolution order (first one set wins):
  1. the slab's own markup      TourPricing.admin_markup_value
  2. the tour's markup          Tour.admin_markup_percentage
  3. the platform default       default_admin_markup_percentage (Settings)
NULL at a level means "inherit from the next one". The storefront prices
stored on each slab are always derived from this effective value and are
recomputed when the tour markup (set_tour_markup) or the default
(recompute_default_markup_slabs) changes, so the tour page, price-from and
checkout update immediately. Bookings already made keep their snapshot.
"""
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.cms import Tour
from app.models.tours import TourPricing
from app.utils.money import apply_markup, money


def default_markup_percentage(db: Session) -> Decimal:
    from app.services.settings import get_default_admin_markup_percentage

    return Decimal(str(get_default_admin_markup_percentage(db) or 0))


def tour_markup_percentage(db: Session, tour_id: int | None, default: Decimal | None = None) -> Decimal:
    """The tour's markup, or the platform default when the tour has none."""
    tour = db.query(Tour).filter(Tour.id == tour_id).first() if tour_id else None
    if tour is not None and tour.admin_markup_percentage is not None:
        return Decimal(str(tour.admin_markup_percentage))
    return default if default is not None else default_markup_percentage(db)


def effective_markup_percentage(db: Session, slab: TourPricing | None, default: Decimal | None = None) -> Decimal:
    """Slab markup, else tour markup, else platform default."""
    if slab is None:
        return Decimal("0")
    if slab.admin_markup_value is not None:
        return Decimal(str(slab.admin_markup_value))
    return tour_markup_percentage(db, slab.tour_id, default)


def storefront_price(db: Session, slab: TourPricing, supplier_amount, default: Decimal | None = None) -> Decimal:
    """Customer price from the published supplier rate plus Tourvaa markup.

    Supplier commission and supplier-funded discounts affect settlement, not
    the advertised unit price.  Keeping the customer calculation independent
    of commission makes the saved slab, public tour, quote and checkout agree.
    """
    base_price = max(Decimal("0"), Decimal(str(supplier_amount or 0)))
    return apply_markup(base_price, effective_markup_percentage(db, slab, default))


def apply_storefront(db: Session, slab: TourPricing, default: Decimal | None = None) -> None:
    """Refresh the slab's stored storefront prices from its effective markup."""
    slab.storefront_adult_price = storefront_price(db, slab, slab.adult_price, default)
    slab.storefront_child_price = storefront_price(db, slab, slab.child_price, default)
    slab.final_price = slab.storefront_adult_price


def _reprice(db: Session, slabs: list[TourPricing], default: Decimal) -> None:
    from app.services.tours import recalculate_price_start

    for slab in slabs:
        apply_storefront(db, slab, default)
    db.flush()
    for tour_id in {slab.tour_id for slab in slabs}:
        recalculate_price_start(db, tour_id)


def recompute_default_markup_slabs(db: Session) -> int:
    """Re-price every slab that inherits its markup (no slab markup) -- used
    when default_admin_markup_percentage changes. Slabs whose tour has its
    own markup are unaffected by the default but recomputing them is
    harmless. Returns the number of slabs updated."""
    slabs = db.query(TourPricing).filter(TourPricing.admin_markup_value.is_(None)).all()
    _reprice(db, slabs, default_markup_percentage(db))
    return len(slabs)


def set_tour_markup(db: Session, tour: Tour, percentage: Decimal | float | None) -> int:
    """Set (or clear, with None) the tour's markup and re-price its slabs
    that inherit markup. Returns the number of slabs re-priced."""
    tour.admin_markup_percentage = None if percentage is None else Decimal(str(percentage))
    db.flush()
    slabs = db.query(TourPricing).filter(TourPricing.tour_id == tour.id, TourPricing.admin_markup_value.is_(None)).all()
    _reprice(db, slabs, default_markup_percentage(db))
    # price-from also depends on slabs with their own markup; recompute once more
    # even when no slab inherits.
    if not slabs:
        from app.services.tours import recalculate_price_start
        recalculate_price_start(db, tour.id)
    return len(slabs)
