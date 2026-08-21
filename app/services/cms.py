from datetime import timezone

from fastapi import HTTPException, Request
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.services.audit import log_audit
from app.models.cms import City, Country, State, Tour, TourCategory, TourSubcategory, TourSubcategoryMap
from app.schemas.cms import CategoryPayload, CityPayload, CountryPayload, StatePayload, StatusUpdate, SubcategoryPayload, TourPayload, slugify
from app.utils.operations import get_or_404, simple_paginate
from app.models.users import User


def _country(item: Country):
    return {"id": item.id, "country_name": item.country_name, "country_code": item.country_code, "phone_code": item.phone_code, "currency_code": item.currency_code, "status": item.status, "created_at": item.created_at, "updated_at": item.updated_at}


def _state(item: State):
    return {"id": item.id, "country_id": item.country_id, "country_name": item.country.country_name if item.country else "", "state_name": item.state_name, "state_code": item.state_code, "status": item.status, "created_at": item.created_at, "updated_at": item.updated_at}


def _city(item: City):
    return {"id": item.id, "country_id": item.country_id, "country_name": item.country.country_name if item.country else "", "state_id": item.state_id, "state_name": item.state.state_name if item.state else "", "city_name": item.city_name, "status": item.status, "created_at": item.created_at, "updated_at": item.updated_at}


def _category(item: TourCategory):
    return {"id": item.id, "category_name": item.category_name, "slug": item.slug, "description": item.description, "image": item.image, "status": item.status, "created_at": item.created_at, "updated_at": item.updated_at}


def _subcategory(item: TourSubcategory):
    return {"id": item.id, "category_id": item.category_id, "category_name": item.category.category_name if item.category else "", "subcategory_name": item.subcategory_name, "slug": item.slug, "description": item.description, "image": item.image, "status": item.status, "created_at": item.created_at, "updated_at": item.updated_at}


def _tour(item: Tour):
    return {
        "id": item.id,
        "tour_code": item.tour_code,
        "supplier_id": item.supplier_id,
        "supplier_name": item.supplier.supplier_name if item.supplier else "",
        "title": item.title,
        "slug": item.slug,
        "subtitle": item.subtitle,
        "price_start_per_person": item.price_start_per_person,
        "currency": item.currency,
        "country_id": item.country_id,
        "country_name": item.country.country_name if item.country else "",
        "state_id": item.state_id,
        "state_name": item.state.state_name if item.state else "",
        "city_id": item.city_id,
        "city_name": item.city.city_name if item.city else "",
        "category_id": item.category_id,
        "category_name": item.category.category_name if item.category else "",
        "subcategory_ids": [link.subcategory_id for link in item.subcategory_links],
        "subcategories": [_subcategory(link.subcategory) for link in item.subcategory_links if link.subcategory],
        "start_location": item.start_location,
        "finish_location": item.finish_location,
        "number_of_days": item.number_of_days,
        "number_of_hours": item.number_of_hours,
        "number_of_nights": item.number_of_nights,
        "max_group_size": item.max_group_size,
        "min_booking_size": item.min_booking_size,
        "tour_language": item.tour_language,
        "suitable_age_range": item.suitable_age_range,
        "tour_visibility": item.tour_visibility,
        "featured": item.featured,
        "short_description": item.short_description,
        "long_description": item.long_description,
        "pricing_type": item.pricing_type,
        "offer_price": item.offer_price,
        "infant_price": item.infant_price,
        "single_supplement": item.single_supplement,
        "tax_percentage": item.tax_percentage,
        "service_fee": item.service_fee,
        "booking_deposit": item.booking_deposit,
        "balance_payment_deadline_days": item.balance_payment_deadline_days,
        "requires_supplier_confirmation": item.requires_supplier_confirmation,
        "commission_percentage": str(item.commission_percentage) if item.commission_percentage is not None else None,
        "seo_title": item.seo_title,
        "seo_description": item.seo_description,
        "seo_keywords": item.seo_keywords,
        "focus_keyword": item.focus_keyword,
        "canonical_url": item.canonical_url,
        "open_graph_image": item.open_graph_image,
        "search_visibility": item.search_visibility,
        "image_alt_text": item.image_alt_text,
        "banner_image": item.banner_image,
        "map_image": item.map_image,
        "mobile_cover_image": item.mobile_cover_image,
        "tour_video_url": item.tour_video_url,
        "brochure_pdf": item.brochure_pdf,
        "status": item.status,
        # Set only while item.status stays "published" during an in-review
        # edit (see tour_versions._stage_pending_version) -- the frontend
        # uses this to show "Unpublished Changes"/"Repricing Required"
        # instead of a plain Published badge, without the tour ever
        # actually leaving the public site mid-review.
        "pending_review_kind": _pending_review_kind(item),
        "active_discount": _active_discount(item),
        "created_by": item.created_by,
        "updated_by": item.updated_by,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }


def _pending_review_kind(item: Tour) -> str | None:
    if item.status != "published" or not item.id:
        return None
    from app.models.tour_versions import TourVersion
    from sqlalchemy.orm import object_session
    session = object_session(item)
    if session is None:
        return None
    pending = (
        session.query(TourVersion)
        .filter(TourVersion.tour_id == item.id, TourVersion.status == "pending_approval")
        .order_by(TourVersion.version_number.desc())
        .first()
    )
    return pending.change_kind if pending else None


def _active_discount(item: Tour) -> dict | None:
    """Best currently-active, tour-scoped TourDiscount expressed as a
    percentage off price_start_per_person - mirrors public.py's
    _active_discount_map so the admin/supplier "Basic tour details" preview
    matches exactly what customers see on the storefront."""
    if not item.id:
        return None
    from datetime import datetime, timezone
    from sqlalchemy import or_
    from sqlalchemy.orm import object_session
    from app.models.tours import TourDiscount
    session = object_session(item)
    if session is None:
        return None
    now = datetime.now(timezone.utc)
    rows = (
        session.query(TourDiscount)
        .filter(
            TourDiscount.tour_id == item.id,
            TourDiscount.status == "active",
            or_(TourDiscount.start_date.is_(None), TourDiscount.start_date <= now),
            or_(TourDiscount.end_date.is_(None), TourDiscount.end_date >= now),
        )
        .all()
    )
    base_price = float(item.price_start_per_person or 0)
    if not rows or base_price <= 0:
        return None
    best: dict | None = None
    for row in rows:
        pct = float(row.discount_value) if row.discount_type == "percentage" else (float(row.discount_value) / base_price) * 100
        pct = round(min(90.0, max(0.0, pct)))
        if pct <= 0:
            continue
        if not best or pct > best["discount_percentage"]:
            best = {
                "discount_percentage": pct,
                "original_price_per_person": base_price,
                "discounted_price_per_person": round(base_price * (1 - pct / 100), 2),
            }
    return best


def _unique_slug(db: Session, model, slug: str, current_id: int | None = None):
    base = slugify(slug)
    candidate = base
    index = 2
    while True:
        query = db.query(model).filter(model.slug == candidate)
        if current_id:
            query = query.filter(model.id != current_id)
        if not query.first():
            return candidate
        candidate = f"{base}-{index}"
        index += 1


def list_countries(db: Session, page: int, limit: int, search: str = ""):
    query = db.query(Country)
    if search:
        pattern = f"%{search.strip()}%"
        query = query.filter(or_(Country.country_name.ilike(pattern), Country.country_code.ilike(pattern)))
    return simple_paginate(query.order_by(Country.country_name.asc()), page, limit, _country)


def save_country(db: Session, data: CountryPayload, actor: User, request: Request | None = None, country_id: int | None = None):
    item = get_or_404(db, Country, country_id, "Country") if country_id else Country()
    old = _country(item) if country_id else None
    for key, value in data.model_dump().items():
        setattr(item, key, value)
    db.add(item)
    db.flush()
    log_audit(db, actor=actor, action="update_country" if country_id else "create_country", entity_type="country", entity_id=item.id, old_values=old, new_values=_country(item), request=request)
    db.commit()
    db.refresh(item)
    return _country(item)


def list_states(db: Session, page: int, limit: int, search: str = "", country_id: str = ""):
    query = db.query(State)
    if search:
        pattern = f"%{search.strip()}%"
        query = query.filter(or_(State.state_name.ilike(pattern), State.state_code.ilike(pattern)))
    if country_id:
        query = query.filter(State.country_id == int(country_id))
    return simple_paginate(query.order_by(State.state_name.asc()), page, limit, _state)


def save_state(db: Session, data: StatePayload, actor: User, request: Request | None = None, state_id: int | None = None):
    get_or_404(db, Country, data.country_id, "Country")
    item = get_or_404(db, State, state_id, "State") if state_id else State()
    old = _state(item) if state_id else None
    for key, value in data.model_dump().items():
        setattr(item, key, value)
    db.add(item)
    db.flush()
    log_audit(db, actor=actor, action="update_state" if state_id else "create_state", entity_type="state", entity_id=item.id, old_values=old, new_values=_state(item), request=request)
    db.commit()
    db.refresh(item)
    return _state(item)


def list_cities(db: Session, page: int, limit: int, search: str = "", country_id: str = "", state_id: str = ""):
    query = db.query(City)
    if search:
        query = query.filter(City.city_name.ilike(f"%{search.strip()}%"))
    if country_id:
        query = query.filter(City.country_id == int(country_id))
    if state_id:
        query = query.filter(City.state_id == int(state_id))
    return simple_paginate(query.order_by(City.city_name.asc()), page, limit, _city)


def save_city(db: Session, data: CityPayload, actor: User, request: Request | None = None, city_id: int | None = None):
    get_or_404(db, Country, data.country_id, "Country")
    if data.state_id:
        state = get_or_404(db, State, data.state_id, "State")
        if state.country_id != data.country_id:
            raise HTTPException(status_code=422, detail="State does not belong to the selected country")
    item = get_or_404(db, City, city_id, "City") if city_id else City()
    old = _city(item) if city_id else None
    for key, value in data.model_dump().items():
        setattr(item, key, value)
    db.add(item)
    db.flush()
    log_audit(db, actor=actor, action="update_city" if city_id else "create_city", entity_type="city", entity_id=item.id, old_values=old, new_values=_city(item), request=request)
    db.commit()
    db.refresh(item)
    return _city(item)


def list_categories(db: Session, page: int, limit: int, search: str = ""):
    query = db.query(TourCategory)
    if search:
        query = query.filter(TourCategory.category_name.ilike(f"%{search.strip()}%"))
    return simple_paginate(query.order_by(TourCategory.id.desc()), page, limit, _category)


def save_category(db: Session, data: CategoryPayload, actor: User, request: Request | None = None, category_id: int | None = None):
    item = get_or_404(db, TourCategory, category_id, "Category") if category_id else TourCategory()
    old = _category(item) if category_id else None
    payload = data.model_dump()
    payload["slug"] = _unique_slug(db, TourCategory, payload["slug"] or payload["category_name"], category_id)
    for key, value in payload.items():
        setattr(item, key, value)
    db.add(item)
    db.flush()
    log_audit(db, actor=actor, action="update_category" if category_id else "create_category", entity_type="category", entity_id=item.id, old_values=old, new_values=_category(item), request=request)
    db.commit()
    db.refresh(item)
    return _category(item)


def list_subcategories(db: Session, page: int, limit: int, search: str = "", category_id: str = ""):
    query = db.query(TourSubcategory)
    if search:
        query = query.filter(TourSubcategory.subcategory_name.ilike(f"%{search.strip()}%"))
    if category_id:
        query = query.filter(TourSubcategory.category_id == int(category_id))
    return simple_paginate(query.order_by(TourSubcategory.id.desc()), page, limit, _subcategory)


def save_subcategory(db: Session, data: SubcategoryPayload, actor: User, request: Request | None = None, subcategory_id: int | None = None):
    get_or_404(db, TourCategory, data.category_id, "Category")
    item = get_or_404(db, TourSubcategory, subcategory_id, "Subcategory") if subcategory_id else TourSubcategory()
    old = _subcategory(item) if subcategory_id else None
    payload = data.model_dump()
    payload["slug"] = _unique_slug(db, TourSubcategory, payload["slug"] or payload["subcategory_name"], subcategory_id)
    for key, value in payload.items():
        setattr(item, key, value)
    db.add(item)
    db.flush()
    log_audit(db, actor=actor, action="update_subcategory" if subcategory_id else "create_subcategory", entity_type="subcategory", entity_id=item.id, old_values=old, new_values=_subcategory(item), request=request)
    db.commit()
    db.refresh(item)
    return _subcategory(item)


def list_tours(db: Session, page: int, limit: int, search: str = "", country_id: str = "", city_id: str = "", category_id: str = "", status: str = "", supplier_id: str = ""):
    query = db.query(Tour)
    if search:
        pattern = f"%{search.strip()}%"
        query = query.filter(or_(Tour.tour_code.ilike(pattern), Tour.title.ilike(pattern), Tour.slug.ilike(pattern)))
    if country_id:
        query = query.filter(Tour.country_id == int(country_id))
    if city_id:
        query = query.filter(Tour.city_id == int(city_id))
    if category_id:
        query = query.filter(Tour.category_id == int(category_id))
    if status:
        query = query.filter(Tour.status == status.strip().lower())
    if supplier_id:
        query = query.filter(Tour.supplier_id == int(supplier_id))
    return simple_paginate(query.order_by(Tour.id.desc()), page, limit, _tour)


def get_tour(db: Session, tour_id: int):
    return get_or_404(db, Tour, tour_id, "Tour")


def save_tour(db: Session, data: TourPayload, actor: User, request: Request | None = None, tour_id: int | None = None):
    item = get_tour(db, tour_id) if tour_id else Tour(created_by=actor.id)
    old = _tour(item) if tour_id else None

    if tour_id and data.expected_updated_at is not None and item.updated_at is not None:
        expected = data.expected_updated_at
        current = item.updated_at
        # Normalize both to naive UTC before comparing -- MySQL's
        # DateTime(timezone=True) columns round-trip as naive here, while a
        # client-submitted ISO string with a UTC offset parses as tz-aware.
        if expected.tzinfo is not None:
            expected = expected.astimezone(timezone.utc).replace(tzinfo=None)
        if current.tzinfo is not None:
            current = current.astimezone(timezone.utc).replace(tzinfo=None)
        if abs((current - expected).total_seconds()) > 0.001:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "This tour was updated by another user. Reload the latest changes before saving.",
                    "current_updated_at": item.updated_at.isoformat(),
                    "current_updated_by": item.updated_by,
                    "submitted_expected_at": data.expected_updated_at.isoformat(),
                },
            )

    payload = data.model_dump()
    payload.pop("expected_updated_at", None)
    subcategory_ids = payload.pop("subcategory_ids", [])
    # Status is workflow-controlled: only the publish/disable toggle
    # (PATCH /tours/{id}/status) and the version-approval flow may change it.
    # New tours always start as draft; existing status is left untouched here.
    payload.pop("status", None)
    # Price From is system-calculated from the lowest approved Supplier
    # Pricing slab (see services.tours.recalculate_price_start) -- never a
    # client-editable marketing field, so any submitted value is ignored.
    payload.pop("price_start_per_person", None)

    # Validate FK IDs exist before attempting insert
    if payload.get("supplier_id"):
        from app.models.suppliers import Supplier
        get_or_404(db, Supplier, payload["supplier_id"], "Supplier")
    if payload.get("country_id"):
        get_or_404(db, Country, payload["country_id"], "Country")
    if payload.get("state_id"):
        get_or_404(db, State, payload["state_id"], "State")
    if payload.get("city_id"):
        get_or_404(db, City, payload["city_id"], "City")
    if payload.get("category_id"):
        get_or_404(db, TourCategory, payload["category_id"], "Tour category")
    for sub_id in subcategory_ids:
        get_or_404(db, TourSubcategory, sub_id, "Tour subcategory")

    payload["slug"] = _unique_slug(db, Tour, payload["slug"] or payload["title"], tour_id)
    for key, value in payload.items():
        setattr(item, key, value)
    if not tour_id:
        item.status = "draft"
    item.updated_by = actor.id
    db.add(item)
    db.flush()
    if not item.tour_code:
        item.tour_code = f"{item.id:05d}"
    item.subcategory_links = [TourSubcategoryMap(subcategory_id=subcategory_id) for subcategory_id in subcategory_ids]
    if tour_id:
        # Editing an already-live tour's own fields is the same live-edit gap
        # as editing its child resources (itinerary/pricing/etc.) -- pull it
        # back into review instead of letting the change go out silently.
        from app.services.tour_versions import maybe_resubmit_for_review
        maybe_resubmit_for_review(db, item.id, actor)
    log_audit(db, actor=actor, action="update_tour" if tour_id else "create_tour", entity_type="tour", entity_id=item.id, old_values=old, new_values=_tour(item), request=request)
    db.commit()
    db.refresh(item)
    return _tour(item)


def delete_tour(db: Session, tour_id: int, actor: User, request: Request | None = None) -> None:
    """Admin-only hard delete. Blocked if any booking ever referenced this
    tour (no ondelete cascade exists on Booking.tour_id, and a booking's
    history must never silently disappear) -- unpublish/disable the tour
    instead if it needs to stop taking new bookings. All of the tour's own
    detail-page child rows have no independent meaning without the tour, so
    those are deleted here rather than left as orphans."""
    item = get_or_404(db, Tour, tour_id, "Tour")

    from app.models.bookings import Booking
    has_bookings = db.query(Booking.id).filter(Booking.tour_id == tour_id).first() is not None
    if has_bookings:
        raise HTTPException(status_code=400, detail="This tour has existing bookings and cannot be deleted. Unpublish or disable it instead.")

    from app.models.customers import CustomerWishlistItem
    from app.models.tour_versions import TourReviewComment, TourVersion
    from app.models.tours import (
        TourAccommodationExtra,
        TourAvailabilityConfig,
        TourCalendar,
        TourDiscount,
        TourExclusion,
        TourExtension,
        TourGalleryImage,
        TourHighlight,
        TourInclusion,
        TourItinerary,
        TourOptionalActivity,
        TourOverview,
        TourPricing,
        TourSimilar,
        TourUnavailableDate,
    )

    old = _tour(item)
    child_deletes = [
        (TourVersion, TourVersion.tour_id),
        (TourReviewComment, TourReviewComment.tour_id),
        (CustomerWishlistItem, CustomerWishlistItem.tour_id),
        (TourOverview, TourOverview.tour_id),
        (TourItinerary, TourItinerary.tour_id),
        (TourInclusion, TourInclusion.tour_id),
        (TourExclusion, TourExclusion.tour_id),
        (TourHighlight, TourHighlight.tour_id),
        (TourGalleryImage, TourGalleryImage.tour_id),
        (TourPricing, TourPricing.tour_id),
        (TourOptionalActivity, TourOptionalActivity.tour_id),
        (TourAccommodationExtra, TourAccommodationExtra.tour_id),
        (TourCalendar, TourCalendar.tour_id),
        (TourAvailabilityConfig, TourAvailabilityConfig.tour_id),
        (TourUnavailableDate, TourUnavailableDate.tour_id),
        (TourDiscount, TourDiscount.tour_id),
    ]
    for model, column in child_deletes:
        db.query(model).filter(column == tour_id).delete(synchronize_session=False)
    # TourExtension/TourSimilar each reference tours.id twice (as the owning
    # tour and as the linked tour) - clear both directions.
    db.query(TourExtension).filter((TourExtension.tour_id == tour_id) | (TourExtension.extension_tour_id == tour_id)).delete(synchronize_session=False)
    db.query(TourSimilar).filter((TourSimilar.tour_id == tour_id) | (TourSimilar.similar_tour_id == tour_id)).delete(synchronize_session=False)

    log_audit(db, actor=actor, action="delete_tour", entity_type="tour", entity_id=tour_id, old_values=old, request=request)
    db.delete(item)
    db.commit()


def update_status(db: Session, model, serializer, item_id: int, data: StatusUpdate, actor: User, entity_type: str, request: Request | None = None):
    item = get_or_404(db, model, item_id, entity_type.title())
    old = serializer(item)
    item.status = data.status
    log_audit(db, actor=actor, action=f"update_{entity_type}_status", entity_type=entity_type, entity_id=item.id, old_values=old, new_values=serializer(item), request=request)
    db.commit()
    db.refresh(item)
    return serializer(item)


def update_tour_commission(db: Session, tour_id: int, data: "TourCommissionUpdate", actor: User, request: Request | None = None):
    """Admin-only per-tour override of Tourvaa's commission - see
    models.cms.Tour.commission_percentage. A non-null value must still
    respect the platform-wide minimum, same as a supplier's own rate
    (services.settings.get_commission_percentage); it is not bounded by the
    supplier's own commission_percentage, since this is Tourvaa's own
    decision to charge more or less on a specific tour."""
    item = get_tour(db, tour_id)
    old = _tour(item)
    if data.commission_percentage is not None:
        from app.services.settings import get_commission_percentage
        from decimal import Decimal
        minimum = get_commission_percentage(db)
        if Decimal(str(data.commission_percentage)) < minimum:
            raise HTTPException(status_code=400, detail=f"Tour commission cannot be lower than the platform minimum of {minimum}%")
    item.commission_percentage = data.commission_percentage
    log_audit(db, actor=actor, action="update_tour_commission", entity_type="tour", entity_id=item.id, old_values=old, new_values=_tour(item), request=request)
    db.commit()
    db.refresh(item)
    return _tour(item)
