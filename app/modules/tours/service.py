from datetime import datetime, timezone

from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from app.modules.audit.service import log_audit
from app.modules.cms.models import Tour
from app.modules.operations import get_or_404
from app.modules.tours.models import (
    TourAccommodationExtra,
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
from app.modules.tours.schemas import (
    AccommodationExtraPayload,
    CalendarPayload,
    DiscountPayload,
    ExtensionPayload,
    GalleryImagePayload,
    HighlightPayload,
    InclusionPayload,
    ItineraryPayload,
    OptionalActivityPayload,
    PriceCalculationRequest,
    PricingPayload,
    ReorderPayload,
    SimilarTourPayload,
    TourOverviewPayload,
)
from app.modules.users.models import User


# ── Helpers ───────────────────────────────────────────────────────────────────

def _require_tour(db: Session, tour_id: int) -> Tour:
    return get_or_404(db, Tour, tour_id, "Tour")


def _child_or_404(db: Session, model, record_id: int, tour_id: int, label: str):
    obj = db.query(model).filter(model.id == record_id, model.tour_id == tour_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail=f"{label} not found")
    return obj


# ── Overview ──────────────────────────────────────────────────────────────────

def _ser_overview(o: TourOverview) -> dict:
    return {
        "id": o.id, "tour_id": o.tour_id,
        "duration_text": o.duration_text, "start_location": o.start_location,
        "end_location": o.end_location, "group_size": o.group_size,
        "tour_type": o.tour_type, "physical_rating": o.physical_rating,
        "overview_icon_data": o.overview_icon_data,
        "created_at": o.created_at, "updated_at": o.updated_at,
    }


def get_overview(db: Session, tour_id: int) -> dict | None:
    _require_tour(db, tour_id)
    o = db.query(TourOverview).filter(TourOverview.tour_id == tour_id).first()
    return _ser_overview(o) if o else None


def save_overview(db: Session, tour_id: int, data: TourOverviewPayload, actor: User, request: Request | None = None) -> dict:
    _require_tour(db, tour_id)
    o = db.query(TourOverview).filter(TourOverview.tour_id == tour_id).first()
    if not o:
        o = TourOverview(tour_id=tour_id)
        db.add(o)
    payload = data.model_dump()
    for key, value in payload.items():
        setattr(o, key, value)
    log_audit(db, actor=actor, action="save_tour_overview", entity_type="tour", entity_id=tour_id, request=request)
    db.commit()
    db.refresh(o)
    return _ser_overview(o)


# ── Itinerary ─────────────────────────────────────────────────────────────────

def _ser_itinerary(i: TourItinerary) -> dict:
    return {
        "id": i.id, "tour_id": i.tour_id, "day_number": i.day_number,
        "day_title": i.day_title, "location_name": i.location_name,
        "short_description": i.short_description, "long_description": i.long_description,
        "activities": i.activities, "image": i.image, "image_alt_text": i.image_alt_text,
        "display_order": i.display_order, "status": i.status,
        "created_at": i.created_at, "updated_at": i.updated_at,
    }


def list_itineraries(db: Session, tour_id: int) -> list[dict]:
    _require_tour(db, tour_id)
    return [_ser_itinerary(i) for i in db.query(TourItinerary).filter(TourItinerary.tour_id == tour_id).order_by(TourItinerary.display_order, TourItinerary.day_number).all()]


def create_itinerary(db: Session, tour_id: int, data: ItineraryPayload, actor: User, request: Request | None = None) -> dict:
    _require_tour(db, tour_id)
    o = TourItinerary(tour_id=tour_id, **data.model_dump())
    db.add(o)
    log_audit(db, actor=actor, action="create_itinerary", entity_type="tour", entity_id=tour_id, request=request)
    db.commit()
    db.refresh(o)
    return _ser_itinerary(o)


def update_itinerary(db: Session, tour_id: int, itinerary_id: int, data: ItineraryPayload, actor: User, request: Request | None = None) -> dict:
    o = _child_or_404(db, TourItinerary, itinerary_id, tour_id, "Itinerary")
    for key, value in data.model_dump().items():
        setattr(o, key, value)
    log_audit(db, actor=actor, action="update_itinerary", entity_type="tour", entity_id=tour_id, request=request)
    db.commit()
    db.refresh(o)
    return _ser_itinerary(o)


def delete_itinerary(db: Session, tour_id: int, itinerary_id: int, actor: User, request: Request | None = None):
    o = _child_or_404(db, TourItinerary, itinerary_id, tour_id, "Itinerary")
    log_audit(db, actor=actor, action="delete_itinerary", entity_type="tour", entity_id=tour_id, request=request)
    db.delete(o)
    db.commit()


def reorder_itineraries(db: Session, tour_id: int, data: ReorderPayload, actor: User, request: Request | None = None):
    _require_tour(db, tour_id)
    for order, record_id in enumerate(data.ordered_ids):
        db.query(TourItinerary).filter(TourItinerary.id == record_id, TourItinerary.tour_id == tour_id).update({"display_order": order})
    log_audit(db, actor=actor, action="reorder_itineraries", entity_type="tour", entity_id=tour_id, request=request)
    db.commit()


# ── Generic list/create/update/delete for simple child models ─────────────────

def _simple_crud(Model, serializer):
    def list_fn(db: Session, tour_id: int) -> list[dict]:
        _require_tour(db, tour_id)
        q = db.query(Model).filter(Model.tour_id == tour_id)
        if hasattr(Model, "display_order"):
            q = q.order_by(Model.display_order)
        return [serializer(o) for o in q.all()]

    def create_fn(db: Session, tour_id: int, data, actor: User, action: str, request: Request | None = None) -> dict:
        _require_tour(db, tour_id)
        o = Model(tour_id=tour_id, **data.model_dump())
        db.add(o)
        log_audit(db, actor=actor, action=action, entity_type="tour", entity_id=tour_id, request=request)
        db.commit()
        db.refresh(o)
        return serializer(o)

    def update_fn(db: Session, tour_id: int, record_id: int, data, actor: User, action: str, label: str, request: Request | None = None) -> dict:
        o = _child_or_404(db, Model, record_id, tour_id, label)
        for key, value in data.model_dump().items():
            setattr(o, key, value)
        log_audit(db, actor=actor, action=action, entity_type="tour", entity_id=tour_id, request=request)
        db.commit()
        db.refresh(o)
        return serializer(o)

    def delete_fn(db: Session, tour_id: int, record_id: int, actor: User, action: str, label: str, request: Request | None = None):
        o = _child_or_404(db, Model, record_id, tour_id, label)
        log_audit(db, actor=actor, action=action, entity_type="tour", entity_id=tour_id, request=request)
        db.delete(o)
        db.commit()

    return list_fn, create_fn, update_fn, delete_fn


# ── Inclusion ─────────────────────────────────────────────────────────────────

def _ser_inclusion(o: TourInclusion) -> dict:
    return {"id": o.id, "tour_id": o.tour_id, "icon": o.icon, "title": o.title, "description": o.description, "display_order": o.display_order, "status": o.status, "created_at": o.created_at, "updated_at": o.updated_at}

_list_inclusions_fn, _create_inclusion_fn, _update_inclusion_fn, _delete_inclusion_fn = _simple_crud(TourInclusion, _ser_inclusion)

def list_inclusions(db, tour_id): return _list_inclusions_fn(db, tour_id)
def create_inclusion(db, tour_id, data, actor, request=None): return _create_inclusion_fn(db, tour_id, data, actor, "create_inclusion", request)
def update_inclusion(db, tour_id, rid, data, actor, request=None): return _update_inclusion_fn(db, tour_id, rid, data, actor, "update_inclusion", "Inclusion", request)
def delete_inclusion(db, tour_id, rid, actor, request=None): return _delete_inclusion_fn(db, tour_id, rid, actor, "delete_inclusion", "Inclusion", request)


# ── Exclusion ─────────────────────────────────────────────────────────────────

def _ser_exclusion(o: TourExclusion) -> dict:
    return {"id": o.id, "tour_id": o.tour_id, "icon": o.icon, "title": o.title, "description": o.description, "display_order": o.display_order, "status": o.status, "created_at": o.created_at, "updated_at": o.updated_at}

_list_exclusions_fn, _create_exclusion_fn, _update_exclusion_fn, _delete_exclusion_fn = _simple_crud(TourExclusion, _ser_exclusion)

def list_exclusions(db, tour_id): return _list_exclusions_fn(db, tour_id)
def create_exclusion(db, tour_id, data, actor, request=None): return _create_exclusion_fn(db, tour_id, data, actor, "create_exclusion", request)
def update_exclusion(db, tour_id, rid, data, actor, request=None): return _update_exclusion_fn(db, tour_id, rid, data, actor, "update_exclusion", "Exclusion", request)
def delete_exclusion(db, tour_id, rid, actor, request=None): return _delete_exclusion_fn(db, tour_id, rid, actor, "delete_exclusion", "Exclusion", request)


# ── Highlight ─────────────────────────────────────────────────────────────────

def _ser_highlight(o: TourHighlight) -> dict:
    return {"id": o.id, "tour_id": o.tour_id, "image": o.image, "title": o.title, "short_description": o.short_description, "display_order": o.display_order, "status": o.status, "created_at": o.created_at, "updated_at": o.updated_at}

_list_highlights_fn, _create_highlight_fn, _update_highlight_fn, _delete_highlight_fn = _simple_crud(TourHighlight, _ser_highlight)

def list_highlights(db, tour_id): return _list_highlights_fn(db, tour_id)
def create_highlight(db, tour_id, data, actor, request=None): return _create_highlight_fn(db, tour_id, data, actor, "create_highlight", request)
def update_highlight(db, tour_id, rid, data, actor, request=None): return _update_highlight_fn(db, tour_id, rid, data, actor, "update_highlight", "Highlight", request)
def delete_highlight(db, tour_id, rid, actor, request=None): return _delete_highlight_fn(db, tour_id, rid, actor, "delete_highlight", "Highlight", request)


# ── Gallery ───────────────────────────────────────────────────────────────────

def _ser_gallery(o: TourGalleryImage) -> dict:
    return {"id": o.id, "tour_id": o.tour_id, "image_path": o.image_path, "image_title": o.image_title, "image_alt_text": o.image_alt_text, "image_caption": o.image_caption, "image_type": o.image_type, "display_order": o.display_order, "status": o.status, "created_at": o.created_at, "updated_at": o.updated_at}

_list_gallery_fn, _create_gallery_fn, _update_gallery_fn, _delete_gallery_fn = _simple_crud(TourGalleryImage, _ser_gallery)

def list_gallery(db, tour_id): return _list_gallery_fn(db, tour_id)
def create_gallery_image(db, tour_id, data, actor, request=None): return _create_gallery_fn(db, tour_id, data, actor, "create_gallery_image", request)
def update_gallery_image(db, tour_id, rid, data, actor, request=None): return _update_gallery_fn(db, tour_id, rid, data, actor, "update_gallery_image", "Gallery image", request)
def delete_gallery_image(db, tour_id, rid, actor, request=None): return _delete_gallery_fn(db, tour_id, rid, actor, "delete_gallery_image", "Gallery image", request)


# ── Similar Tours ─────────────────────────────────────────────────────────────

def _ser_similar(o: TourSimilar) -> dict:
    return {
        "id": o.id, "tour_id": o.tour_id, "similar_tour_id": o.similar_tour_id,
        "similar_tour_title": o.similar_tour.title if o.similar_tour else "",
        "similar_tour_code": o.similar_tour.tour_code if o.similar_tour else "",
        "display_order": o.display_order, "status": o.status, "created_at": o.created_at,
    }


def list_similar_tours(db: Session, tour_id: int) -> list[dict]:
    _require_tour(db, tour_id)
    return [_ser_similar(o) for o in db.query(TourSimilar).filter(TourSimilar.tour_id == tour_id).order_by(TourSimilar.display_order).all()]


def add_similar_tour(db: Session, tour_id: int, data: SimilarTourPayload, actor: User, request: Request | None = None) -> dict:
    _require_tour(db, tour_id)
    if data.similar_tour_id == tour_id:
        raise HTTPException(status_code=400, detail="A tour cannot be similar to itself")
    _require_tour(db, data.similar_tour_id)
    existing = db.query(TourSimilar).filter(TourSimilar.tour_id == tour_id, TourSimilar.similar_tour_id == data.similar_tour_id).first()
    if existing:
        raise HTTPException(status_code=409, detail="This similar tour mapping already exists")
    o = TourSimilar(tour_id=tour_id, similar_tour_id=data.similar_tour_id, display_order=data.display_order)
    db.add(o)
    log_audit(db, actor=actor, action="add_similar_tour", entity_type="tour", entity_id=tour_id, request=request)
    db.commit()
    db.refresh(o)
    return _ser_similar(o)


def delete_similar_tour(db: Session, tour_id: int, similar_id: int, actor: User, request: Request | None = None):
    o = _child_or_404(db, TourSimilar, similar_id, tour_id, "Similar tour")
    log_audit(db, actor=actor, action="delete_similar_tour", entity_type="tour", entity_id=tour_id, request=request)
    db.delete(o)
    db.commit()


# ── Extension ─────────────────────────────────────────────────────────────────

def _ser_extension(o: TourExtension) -> dict:
    return {
        "id": o.id, "tour_id": o.tour_id, "extension_tour_id": o.extension_tour_id,
        "extension_tour_title": o.extension_tour.title if o.extension_tour else "",
        "extension_title": o.extension_title, "extension_note": o.extension_note,
        "extra_price": o.extra_price, "display_order": o.display_order, "status": o.status,
        "created_at": o.created_at, "updated_at": o.updated_at,
    }


def list_extensions(db: Session, tour_id: int) -> list[dict]:
    _require_tour(db, tour_id)
    return [_ser_extension(o) for o in db.query(TourExtension).filter(TourExtension.tour_id == tour_id).order_by(TourExtension.display_order).all()]


def create_extension(db: Session, tour_id: int, data: ExtensionPayload, actor: User, request: Request | None = None) -> dict:
    _require_tour(db, tour_id)
    _require_tour(db, data.extension_tour_id)
    o = TourExtension(tour_id=tour_id, **data.model_dump())
    db.add(o)
    log_audit(db, actor=actor, action="create_extension", entity_type="tour", entity_id=tour_id, request=request)
    db.commit()
    db.refresh(o)
    return _ser_extension(o)


def update_extension(db: Session, tour_id: int, ext_id: int, data: ExtensionPayload, actor: User, request: Request | None = None) -> dict:
    o = _child_or_404(db, TourExtension, ext_id, tour_id, "Extension")
    for key, value in data.model_dump().items():
        setattr(o, key, value)
    log_audit(db, actor=actor, action="update_extension", entity_type="tour", entity_id=tour_id, request=request)
    db.commit()
    db.refresh(o)
    return _ser_extension(o)


def delete_extension(db: Session, tour_id: int, ext_id: int, actor: User, request: Request | None = None):
    o = _child_or_404(db, TourExtension, ext_id, tour_id, "Extension")
    log_audit(db, actor=actor, action="delete_extension", entity_type="tour", entity_id=tour_id, request=request)
    db.delete(o)
    db.commit()


# ── Pricing ───────────────────────────────────────────────────────────────────

def _ser_pricing(o: TourPricing) -> dict:
    return {
        "id": o.id, "tour_id": o.tour_id,
        "passenger_from": o.passenger_from, "passenger_to": o.passenger_to,
        "adult_price": o.adult_price, "child_price": o.child_price,
        "supplier_price": o.supplier_price, "markup_type": o.markup_type,
        "markup_value": o.markup_value, "final_price": o.final_price,
        "currency": o.currency, "status": o.status,
        "created_at": o.created_at, "updated_at": o.updated_at,
    }

_list_pricing_fn, _create_pricing_fn, _update_pricing_fn, _delete_pricing_fn = _simple_crud(TourPricing, _ser_pricing)

def list_pricing(db, tour_id): return _list_pricing_fn(db, tour_id)
def create_pricing(db, tour_id, data, actor, request=None): return _create_pricing_fn(db, tour_id, data, actor, "create_pricing", request)
def update_pricing(db, tour_id, rid, data, actor, request=None): return _update_pricing_fn(db, tour_id, rid, data, actor, "update_pricing", "Pricing slab", request)
def delete_pricing(db, tour_id, rid, actor, request=None): return _delete_pricing_fn(db, tour_id, rid, actor, "delete_pricing", "Pricing slab", request)


# ── Optional Activity ─────────────────────────────────────────────────────────

def _ser_activity(o: TourOptionalActivity) -> dict:
    return {"id": o.id, "tour_id": o.tour_id, "activity_name": o.activity_name, "description": o.description, "price_per_person": o.price_per_person, "image": o.image, "status": o.status, "created_at": o.created_at, "updated_at": o.updated_at}

_list_activities_fn, _create_activity_fn, _update_activity_fn, _delete_activity_fn = _simple_crud(TourOptionalActivity, _ser_activity)

def list_activities(db, tour_id): return _list_activities_fn(db, tour_id)
def create_activity(db, tour_id, data, actor, request=None): return _create_activity_fn(db, tour_id, data, actor, "create_optional_activity", request)
def update_activity(db, tour_id, rid, data, actor, request=None): return _update_activity_fn(db, tour_id, rid, data, actor, "update_optional_activity", "Activity", request)
def delete_activity(db, tour_id, rid, actor, request=None): return _delete_activity_fn(db, tour_id, rid, actor, "delete_optional_activity", "Activity", request)


# ── Accommodation Extra ───────────────────────────────────────────────────────

def _ser_accommodation(o: TourAccommodationExtra) -> dict:
    return {"id": o.id, "tour_id": o.tour_id, "accommodation_name": o.accommodation_name, "description": o.description, "extra_price": o.extra_price, "price_type": o.price_type, "is_default": bool(o.is_default), "status": o.status, "created_at": o.created_at, "updated_at": o.updated_at}


def list_accommodations(db: Session, tour_id: int) -> list[dict]:
    _require_tour(db, tour_id)
    return [_ser_accommodation(o) for o in db.query(TourAccommodationExtra).filter(TourAccommodationExtra.tour_id == tour_id).all()]


def create_accommodation(db: Session, tour_id: int, data: AccommodationExtraPayload, actor: User, request: Request | None = None) -> dict:
    _require_tour(db, tour_id)
    payload = data.model_dump()
    payload["is_default"] = 1 if payload.pop("is_default") else 0
    o = TourAccommodationExtra(tour_id=tour_id, **payload)
    db.add(o)
    log_audit(db, actor=actor, action="create_accommodation_extra", entity_type="tour", entity_id=tour_id, request=request)
    db.commit()
    db.refresh(o)
    return _ser_accommodation(o)


def update_accommodation(db: Session, tour_id: int, extra_id: int, data: AccommodationExtraPayload, actor: User, request: Request | None = None) -> dict:
    o = _child_or_404(db, TourAccommodationExtra, extra_id, tour_id, "Accommodation extra")
    payload = data.model_dump()
    payload["is_default"] = 1 if payload.pop("is_default") else 0
    for key, value in payload.items():
        setattr(o, key, value)
    log_audit(db, actor=actor, action="update_accommodation_extra", entity_type="tour", entity_id=tour_id, request=request)
    db.commit()
    db.refresh(o)
    return _ser_accommodation(o)


def delete_accommodation(db: Session, tour_id: int, extra_id: int, actor: User, request: Request | None = None):
    o = _child_or_404(db, TourAccommodationExtra, extra_id, tour_id, "Accommodation extra")
    log_audit(db, actor=actor, action="delete_accommodation_extra", entity_type="tour", entity_id=tour_id, request=request)
    db.delete(o)
    db.commit()


# ── Calendar ──────────────────────────────────────────────────────────────────

def _ser_calendar(o: TourCalendar) -> dict:
    return {"id": o.id, "tour_id": o.tour_id, "tour_date": o.tour_date, "start_date": o.start_date, "end_date": o.end_date, "available_seats": o.available_seats, "booked_seats": o.booked_seats, "status": o.status, "created_at": o.created_at, "updated_at": o.updated_at}


def list_calendar(db: Session, tour_id: int) -> list[dict]:
    _require_tour(db, tour_id)
    return [_ser_calendar(o) for o in db.query(TourCalendar).filter(TourCalendar.tour_id == tour_id).order_by(TourCalendar.tour_date).all()]


def create_calendar_entry(db: Session, tour_id: int, data: CalendarPayload, actor: User, request: Request | None = None) -> dict:
    _require_tour(db, tour_id)
    o = TourCalendar(tour_id=tour_id, **data.model_dump())
    db.add(o)
    log_audit(db, actor=actor, action="create_calendar_entry", entity_type="tour", entity_id=tour_id, request=request)
    db.commit()
    db.refresh(o)
    return _ser_calendar(o)


def update_calendar_entry(db: Session, tour_id: int, cal_id: int, data: CalendarPayload, actor: User, request: Request | None = None) -> dict:
    o = _child_or_404(db, TourCalendar, cal_id, tour_id, "Calendar entry")
    for key, value in data.model_dump().items():
        setattr(o, key, value)
    log_audit(db, actor=actor, action="update_calendar_entry", entity_type="tour", entity_id=tour_id, request=request)
    db.commit()
    db.refresh(o)
    return _ser_calendar(o)


def delete_calendar_entry(db: Session, tour_id: int, cal_id: int, actor: User, request: Request | None = None):
    o = _child_or_404(db, TourCalendar, cal_id, tour_id, "Calendar entry")
    log_audit(db, actor=actor, action="delete_calendar_entry", entity_type="tour", entity_id=tour_id, request=request)
    db.delete(o)
    db.commit()


# ── Unavailable Dates ─────────────────────────────────────────────────────────

def _ser_unavailable(o: TourUnavailableDate) -> dict:
    return {"id": o.id, "tour_id": o.tour_id, "unavailable_date": o.unavailable_date, "reason": o.reason, "created_at": o.created_at, "updated_at": o.updated_at}


def list_unavailable_dates(db: Session, tour_id: int) -> list[dict]:
    _require_tour(db, tour_id)
    return [_ser_unavailable(o) for o in db.query(TourUnavailableDate).filter(TourUnavailableDate.tour_id == tour_id).order_by(TourUnavailableDate.unavailable_date).all()]


def create_unavailable_date(db: Session, tour_id: int, data, actor: User, request: Request | None = None) -> dict:
    _require_tour(db, tour_id)
    o = TourUnavailableDate(tour_id=tour_id, **data.model_dump())
    db.add(o)
    log_audit(db, actor=actor, action="create_unavailable_date", entity_type="tour", entity_id=tour_id, request=request)
    db.commit()
    db.refresh(o)
    return _ser_unavailable(o)


def delete_unavailable_date(db: Session, tour_id: int, date_id: int, actor: User, request: Request | None = None):
    o = _child_or_404(db, TourUnavailableDate, date_id, tour_id, "Unavailable date")
    log_audit(db, actor=actor, action="delete_unavailable_date", entity_type="tour", entity_id=tour_id, request=request)
    db.delete(o)
    db.commit()


# ── Discounts ─────────────────────────────────────────────────────────────────

def _ser_discount(o: TourDiscount) -> dict:
    return {
        "id": o.id, "tour_id": o.tour_id, "category_id": o.category_id, "country_id": o.country_id,
        "discount_name": o.discount_name, "discount_code": o.discount_code,
        "discount_type": o.discount_type, "discount_value": o.discount_value,
        "discount_scope": o.discount_scope, "start_date": o.start_date, "end_date": o.end_date,
        "usage_limit": o.usage_limit, "used_count": o.used_count,
        "minimum_booking_amount": o.minimum_booking_amount, "status": o.status,
        "created_at": o.created_at, "updated_at": o.updated_at,
    }


def list_discounts(db: Session, tour_id: int) -> list[dict]:
    _require_tour(db, tour_id)
    return [_ser_discount(o) for o in db.query(TourDiscount).filter(TourDiscount.tour_id == tour_id).all()]


def create_discount(db: Session, tour_id: int, data: DiscountPayload, actor: User, request: Request | None = None) -> dict:
    _require_tour(db, tour_id)
    if data.discount_code:
        existing = db.query(TourDiscount).filter(TourDiscount.discount_code == data.discount_code).first()
        if existing:
            raise HTTPException(status_code=409, detail="Discount code already exists")
    payload = data.model_dump()
    o = TourDiscount(tour_id=tour_id, **payload)
    db.add(o)
    log_audit(db, actor=actor, action="create_discount", entity_type="tour", entity_id=tour_id, request=request)
    db.commit()
    db.refresh(o)
    return _ser_discount(o)


def update_discount(db: Session, tour_id: int, disc_id: int, data: DiscountPayload, actor: User, request: Request | None = None) -> dict:
    o = _child_or_404(db, TourDiscount, disc_id, tour_id, "Discount")
    if data.discount_code and data.discount_code != o.discount_code:
        existing = db.query(TourDiscount).filter(TourDiscount.discount_code == data.discount_code, TourDiscount.id != disc_id).first()
        if existing:
            raise HTTPException(status_code=409, detail="Discount code already exists")
    for key, value in data.model_dump().items():
        setattr(o, key, value)
    log_audit(db, actor=actor, action="update_discount", entity_type="tour", entity_id=tour_id, request=request)
    db.commit()
    db.refresh(o)
    return _ser_discount(o)


def delete_discount(db: Session, tour_id: int, disc_id: int, actor: User, request: Request | None = None):
    o = _child_or_404(db, TourDiscount, disc_id, tour_id, "Discount")
    log_audit(db, actor=actor, action="delete_discount", entity_type="tour", entity_id=tour_id, request=request)
    db.delete(o)
    db.commit()


# ── Price Calculation ─────────────────────────────────────────────────────────

def calculate_price(db: Session, tour_id: int, req: PriceCalculationRequest) -> dict:
    tour = _require_tour(db, tour_id)
    total_pax = req.adults_count + req.children_count
    now = datetime.now(tz=timezone.utc)

    # Find best pricing slab
    slab: TourPricing | None = (
        db.query(TourPricing)
        .filter(
            TourPricing.tour_id == tour_id,
            TourPricing.status == "active",
            TourPricing.passenger_from <= total_pax,
            TourPricing.passenger_to >= total_pax,
        )
        .first()
    )

    currency = slab.currency if slab else tour.currency
    adult_unit = slab.adult_price if slab else float(tour.price_start_per_person)
    child_unit = slab.child_price if slab else 0.0

    adult_total = adult_unit * req.adults_count
    child_total = child_unit * req.children_count
    base_price = adult_total + child_total

    # Optional activities
    activity_total = 0.0
    activity_breakdown = []
    if req.optional_activity_ids:
        acts = db.query(TourOptionalActivity).filter(
            TourOptionalActivity.id.in_(req.optional_activity_ids),
            TourOptionalActivity.tour_id == tour_id,
            TourOptionalActivity.status == "active",
        ).all()
        for act in acts:
            cost = act.price_per_person * total_pax
            activity_total += cost
            activity_breakdown.append({"id": act.id, "name": act.activity_name, "amount": cost})

    # Accommodation extras
    accommodation_total = 0.0
    accommodation_breakdown = []
    if req.accommodation_extra_ids:
        extras = db.query(TourAccommodationExtra).filter(
            TourAccommodationExtra.id.in_(req.accommodation_extra_ids),
            TourAccommodationExtra.tour_id == tour_id,
            TourAccommodationExtra.status == "active",
        ).all()
        for extra in extras:
            cost = extra.extra_price * (total_pax if extra.price_type == "per_person" else 1)
            accommodation_total += cost
            accommodation_breakdown.append({"id": extra.id, "name": extra.accommodation_name, "amount": cost})

    # Tour extensions
    extension_total = 0.0
    extension_breakdown = []
    if req.tour_extension_ids:
        exts = db.query(TourExtension).filter(
            TourExtension.id.in_(req.tour_extension_ids),
            TourExtension.tour_id == tour_id,
            TourExtension.status == "active",
        ).all()
        for ext in exts:
            extension_total += ext.extra_price
            extension_breakdown.append({"id": ext.id, "title": ext.extension_title, "amount": ext.extra_price})

    subtotal = base_price + activity_total + accommodation_total + extension_total

    # Apply discount / promo code
    discount_amount = 0.0
    discount_info = None
    discount: TourDiscount | None = None

    if req.promo_code:
        discount = db.query(TourDiscount).filter(
            TourDiscount.discount_code == req.promo_code,
            TourDiscount.status == "active",
        ).first()
        if not discount:
            raise HTTPException(status_code=400, detail="Invalid or expired promo code")

    if not discount:
        # Best automatic discount for this tour
        discount = (
            db.query(TourDiscount)
            .filter(
                TourDiscount.status == "active",
                (TourDiscount.tour_id == tour_id) | (TourDiscount.discount_scope == "all_tours"),
            )
            .first()
        )

    if discount:
        expiry_ok = (not discount.end_date) or discount.end_date.replace(tzinfo=timezone.utc) >= now
        start_ok = (not discount.start_date) or discount.start_date.replace(tzinfo=timezone.utc) <= now
        limit_ok = (not discount.usage_limit) or discount.used_count < discount.usage_limit
        min_ok = subtotal >= discount.minimum_booking_amount

        if expiry_ok and start_ok and limit_ok and min_ok:
            if discount.discount_type == "percentage":
                discount_amount = subtotal * discount.discount_value / 100
            else:
                discount_amount = min(discount.discount_value, subtotal)
            discount_info = {
                "id": discount.id,
                "name": discount.discount_name,
                "code": discount.discount_code,
                "type": discount.discount_type,
                "value": discount.discount_value,
                "amount": discount_amount,
            }

    tax_amount = 0.0
    final_total = max(subtotal - discount_amount, 0.0)

    return {
        "currency": currency,
        "adults_count": req.adults_count,
        "children_count": req.children_count,
        "adult_unit_price": adult_unit,
        "child_unit_price": child_unit,
        "adult_price": adult_total,
        "child_price": child_total,
        "base_price": base_price,
        "optional_activity_total": activity_total,
        "accommodation_extra_total": accommodation_total,
        "tour_extension_total": extension_total,
        "subtotal": subtotal,
        "discount_amount": discount_amount,
        "discount": discount_info,
        "tax_amount": tax_amount,
        "final_total": final_total,
        "price_breakdown": {
            "activities": activity_breakdown,
            "accommodations": accommodation_breakdown,
            "extensions": extension_breakdown,
        },
    }
