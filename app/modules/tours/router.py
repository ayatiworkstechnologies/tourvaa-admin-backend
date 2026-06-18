from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.modules.common.auth import require_any_permission
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
    UnavailableDatePayload,
)
from app.modules.tours.service import (
    add_similar_tour,
    calculate_price,
    create_accommodation,
    create_activity,
    create_calendar_entry,
    create_discount,
    create_exclusion,
    create_extension,
    create_gallery_image,
    create_highlight,
    create_inclusion,
    create_itinerary,
    create_pricing,
    create_unavailable_date,
    delete_accommodation,
    delete_activity,
    delete_calendar_entry,
    delete_discount,
    delete_exclusion,
    delete_extension,
    delete_gallery_image,
    delete_highlight,
    delete_inclusion,
    delete_itinerary,
    delete_pricing,
    delete_similar_tour,
    delete_unavailable_date,
    get_overview,
    list_accommodations,
    list_activities,
    list_calendar,
    list_discounts,
    list_exclusions,
    list_extensions,
    list_gallery,
    list_highlights,
    list_inclusions,
    list_itineraries,
    list_pricing,
    list_similar_tours,
    list_unavailable_dates,
    reorder_itineraries,
    save_overview,
    update_accommodation,
    update_activity,
    update_calendar_entry,
    update_discount,
    update_exclusion,
    update_extension,
    update_gallery_image,
    update_highlight,
    update_inclusion,
    update_itinerary,
    update_pricing,
)
from app.modules.users.models import User

router = APIRouter(prefix="/tours", tags=["Tour Detail"])

VIEW = "tours.view"
EDIT = "tours.edit"


# ── Overview ──────────────────────────────────────────────────────────────────

@router.get("/{tour_id}/overview")
def tour_overview(tour_id: int, db: Session = Depends(get_db), _: User = Depends(require_any_permission(VIEW))):
    return {"status": "success", "data": get_overview(db, tour_id)}


@router.post("/{tour_id}/overview")
def save_tour_overview(tour_id: int, data: TourOverviewPayload, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission(EDIT))):
    return {"status": "success", "data": save_overview(db, tour_id, data, current_user, request)}


@router.put("/{tour_id}/overview")
def update_tour_overview(tour_id: int, data: TourOverviewPayload, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission(EDIT))):
    return {"status": "success", "data": save_overview(db, tour_id, data, current_user, request)}


# ── Itinerary ─────────────────────────────────────────────────────────────────

@router.get("/{tour_id}/itineraries")
def tour_itineraries(tour_id: int, db: Session = Depends(get_db), _: User = Depends(require_any_permission(VIEW))):
    return {"status": "success", "data": list_itineraries(db, tour_id)}


@router.post("/{tour_id}/itineraries")
def add_itinerary(tour_id: int, data: ItineraryPayload, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission(EDIT))):
    return {"status": "success", "data": create_itinerary(db, tour_id, data, current_user, request)}


@router.get("/{tour_id}/itineraries/{itinerary_id}")
def get_itinerary(tour_id: int, itinerary_id: int, db: Session = Depends(get_db), _: User = Depends(require_any_permission(VIEW))):
    from app.modules.tours.service import _child_or_404, _ser_itinerary, TourItinerary
    return {"status": "success", "data": _ser_itinerary(_child_or_404(db, TourItinerary, itinerary_id, tour_id, "Itinerary"))}


@router.put("/{tour_id}/itineraries/{itinerary_id}")
def edit_itinerary(tour_id: int, itinerary_id: int, data: ItineraryPayload, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission(EDIT))):
    return {"status": "success", "data": update_itinerary(db, tour_id, itinerary_id, data, current_user, request)}


@router.delete("/{tour_id}/itineraries/{itinerary_id}")
def remove_itinerary(tour_id: int, itinerary_id: int, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission(EDIT))):
    delete_itinerary(db, tour_id, itinerary_id, current_user, request)
    return {"status": "success", "message": "Itinerary day deleted"}


@router.patch("/{tour_id}/itineraries/reorder")
def reorder_tour_itineraries(tour_id: int, data: ReorderPayload, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission(EDIT))):
    reorder_itineraries(db, tour_id, data, current_user, request)
    return {"status": "success", "message": "Itineraries reordered"}


# ── Inclusions ────────────────────────────────────────────────────────────────

@router.get("/{tour_id}/inclusions")
def tour_inclusions(tour_id: int, db: Session = Depends(get_db), _: User = Depends(require_any_permission(VIEW))):
    return {"status": "success", "data": list_inclusions(db, tour_id)}


@router.post("/{tour_id}/inclusions")
def add_inclusion(tour_id: int, data: InclusionPayload, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission(EDIT))):
    return {"status": "success", "data": create_inclusion(db, tour_id, data, current_user, request)}


@router.put("/{tour_id}/inclusions/{inclusion_id}")
def edit_inclusion(tour_id: int, inclusion_id: int, data: InclusionPayload, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission(EDIT))):
    return {"status": "success", "data": update_inclusion(db, tour_id, inclusion_id, data, current_user, request)}


@router.delete("/{tour_id}/inclusions/{inclusion_id}")
def remove_inclusion(tour_id: int, inclusion_id: int, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission(EDIT))):
    delete_inclusion(db, tour_id, inclusion_id, current_user, request)
    return {"status": "success", "message": "Inclusion deleted"}


# ── Exclusions ────────────────────────────────────────────────────────────────

@router.get("/{tour_id}/exclusions")
def tour_exclusions(tour_id: int, db: Session = Depends(get_db), _: User = Depends(require_any_permission(VIEW))):
    return {"status": "success", "data": list_exclusions(db, tour_id)}


@router.post("/{tour_id}/exclusions")
def add_exclusion(tour_id: int, data: InclusionPayload, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission(EDIT))):
    return {"status": "success", "data": create_exclusion(db, tour_id, data, current_user, request)}


@router.put("/{tour_id}/exclusions/{exclusion_id}")
def edit_exclusion(tour_id: int, exclusion_id: int, data: InclusionPayload, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission(EDIT))):
    return {"status": "success", "data": update_exclusion(db, tour_id, exclusion_id, data, current_user, request)}


@router.delete("/{tour_id}/exclusions/{exclusion_id}")
def remove_exclusion(tour_id: int, exclusion_id: int, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission(EDIT))):
    delete_exclusion(db, tour_id, exclusion_id, current_user, request)
    return {"status": "success", "message": "Exclusion deleted"}


# ── Highlights ────────────────────────────────────────────────────────────────

@router.get("/{tour_id}/highlights")
def tour_highlights(tour_id: int, db: Session = Depends(get_db), _: User = Depends(require_any_permission(VIEW))):
    return {"status": "success", "data": list_highlights(db, tour_id)}


@router.post("/{tour_id}/highlights")
def add_highlight(tour_id: int, data: HighlightPayload, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission(EDIT))):
    return {"status": "success", "data": create_highlight(db, tour_id, data, current_user, request)}


@router.put("/{tour_id}/highlights/{highlight_id}")
def edit_highlight(tour_id: int, highlight_id: int, data: HighlightPayload, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission(EDIT))):
    return {"status": "success", "data": update_highlight(db, tour_id, highlight_id, data, current_user, request)}


@router.delete("/{tour_id}/highlights/{highlight_id}")
def remove_highlight(tour_id: int, highlight_id: int, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission(EDIT))):
    delete_highlight(db, tour_id, highlight_id, current_user, request)
    return {"status": "success", "message": "Highlight deleted"}


# ── Similar Tours ─────────────────────────────────────────────────────────────

@router.get("/{tour_id}/similar-tours")
def tour_similar(tour_id: int, db: Session = Depends(get_db), _: User = Depends(require_any_permission(VIEW))):
    return {"status": "success", "data": list_similar_tours(db, tour_id)}


@router.post("/{tour_id}/similar-tours")
def add_tour_similar(tour_id: int, data: SimilarTourPayload, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission(EDIT))):
    return {"status": "success", "data": add_similar_tour(db, tour_id, data, current_user, request)}


@router.delete("/{tour_id}/similar-tours/{similar_id}")
def remove_similar(tour_id: int, similar_id: int, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission(EDIT))):
    delete_similar_tour(db, tour_id, similar_id, current_user, request)
    return {"status": "success", "message": "Similar tour removed"}


# ── Extensions ────────────────────────────────────────────────────────────────

@router.get("/{tour_id}/extensions")
def tour_extensions(tour_id: int, db: Session = Depends(get_db), _: User = Depends(require_any_permission(VIEW))):
    return {"status": "success", "data": list_extensions(db, tour_id)}


@router.post("/{tour_id}/extensions")
def add_extension(tour_id: int, data: ExtensionPayload, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission(EDIT))):
    return {"status": "success", "data": create_extension(db, tour_id, data, current_user, request)}


@router.put("/{tour_id}/extensions/{extension_id}")
def edit_extension(tour_id: int, extension_id: int, data: ExtensionPayload, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission(EDIT))):
    return {"status": "success", "data": update_extension(db, tour_id, extension_id, data, current_user, request)}


@router.delete("/{tour_id}/extensions/{extension_id}")
def remove_extension(tour_id: int, extension_id: int, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission(EDIT))):
    delete_extension(db, tour_id, extension_id, current_user, request)
    return {"status": "success", "message": "Extension deleted"}


# ── Gallery ───────────────────────────────────────────────────────────────────

@router.get("/{tour_id}/gallery")
def tour_gallery(tour_id: int, db: Session = Depends(get_db), _: User = Depends(require_any_permission(VIEW))):
    return {"status": "success", "data": list_gallery(db, tour_id)}


@router.post("/{tour_id}/gallery")
def add_gallery_image(tour_id: int, data: GalleryImagePayload, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission(EDIT))):
    return {"status": "success", "data": create_gallery_image(db, tour_id, data, current_user, request)}


@router.put("/{tour_id}/gallery/{image_id}")
def edit_gallery_image(tour_id: int, image_id: int, data: GalleryImagePayload, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission(EDIT))):
    return {"status": "success", "data": update_gallery_image(db, tour_id, image_id, data, current_user, request)}


@router.delete("/{tour_id}/gallery/{image_id}")
def remove_gallery_image(tour_id: int, image_id: int, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission(EDIT))):
    delete_gallery_image(db, tour_id, image_id, current_user, request)
    return {"status": "success", "message": "Image deleted"}


# ── Pricing ───────────────────────────────────────────────────────────────────

@router.get("/{tour_id}/pricing")
def tour_pricing(tour_id: int, db: Session = Depends(get_db), _: User = Depends(require_any_permission(VIEW))):
    return {"status": "success", "data": list_pricing(db, tour_id)}


@router.post("/{tour_id}/pricing")
def add_pricing(tour_id: int, data: PricingPayload, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission(EDIT))):
    return {"status": "success", "data": create_pricing(db, tour_id, data, current_user, request)}


@router.put("/{tour_id}/pricing/{pricing_id}")
def edit_pricing(tour_id: int, pricing_id: int, data: PricingPayload, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission(EDIT))):
    return {"status": "success", "data": update_pricing(db, tour_id, pricing_id, data, current_user, request)}


@router.delete("/{tour_id}/pricing/{pricing_id}")
def remove_pricing(tour_id: int, pricing_id: int, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission(EDIT))):
    delete_pricing(db, tour_id, pricing_id, current_user, request)
    return {"status": "success", "message": "Pricing slab deleted"}


# ── Optional Activities ───────────────────────────────────────────────────────

@router.get("/{tour_id}/optional-activities")
def tour_activities(tour_id: int, db: Session = Depends(get_db), _: User = Depends(require_any_permission(VIEW))):
    return {"status": "success", "data": list_activities(db, tour_id)}


@router.post("/{tour_id}/optional-activities")
def add_activity(tour_id: int, data: OptionalActivityPayload, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission(EDIT))):
    return {"status": "success", "data": create_activity(db, tour_id, data, current_user, request)}


@router.put("/{tour_id}/optional-activities/{activity_id}")
def edit_activity(tour_id: int, activity_id: int, data: OptionalActivityPayload, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission(EDIT))):
    return {"status": "success", "data": update_activity(db, tour_id, activity_id, data, current_user, request)}


@router.delete("/{tour_id}/optional-activities/{activity_id}")
def remove_activity(tour_id: int, activity_id: int, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission(EDIT))):
    delete_activity(db, tour_id, activity_id, current_user, request)
    return {"status": "success", "message": "Activity deleted"}


# ── Accommodation Extras ──────────────────────────────────────────────────────

@router.get("/{tour_id}/accommodation-extras")
def tour_accommodations(tour_id: int, db: Session = Depends(get_db), _: User = Depends(require_any_permission(VIEW))):
    return {"status": "success", "data": list_accommodations(db, tour_id)}


@router.post("/{tour_id}/accommodation-extras")
def add_accommodation(tour_id: int, data: AccommodationExtraPayload, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission(EDIT))):
    return {"status": "success", "data": create_accommodation(db, tour_id, data, current_user, request)}


@router.put("/{tour_id}/accommodation-extras/{extra_id}")
def edit_accommodation(tour_id: int, extra_id: int, data: AccommodationExtraPayload, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission(EDIT))):
    return {"status": "success", "data": update_accommodation(db, tour_id, extra_id, data, current_user, request)}


@router.delete("/{tour_id}/accommodation-extras/{extra_id}")
def remove_accommodation(tour_id: int, extra_id: int, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission(EDIT))):
    delete_accommodation(db, tour_id, extra_id, current_user, request)
    return {"status": "success", "message": "Accommodation extra deleted"}


# ── Calendar ──────────────────────────────────────────────────────────────────

@router.get("/{tour_id}/calendar")
def tour_calendar(tour_id: int, db: Session = Depends(get_db), _: User = Depends(require_any_permission(VIEW))):
    return {"status": "success", "data": list_calendar(db, tour_id)}


@router.post("/{tour_id}/calendar")
def add_calendar(tour_id: int, data: CalendarPayload, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission(EDIT))):
    return {"status": "success", "data": create_calendar_entry(db, tour_id, data, current_user, request)}


@router.put("/{tour_id}/calendar/{calendar_id}")
def edit_calendar(tour_id: int, calendar_id: int, data: CalendarPayload, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission(EDIT))):
    return {"status": "success", "data": update_calendar_entry(db, tour_id, calendar_id, data, current_user, request)}


@router.delete("/{tour_id}/calendar/{calendar_id}")
def remove_calendar(tour_id: int, calendar_id: int, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission(EDIT))):
    delete_calendar_entry(db, tour_id, calendar_id, current_user, request)
    return {"status": "success", "message": "Calendar entry deleted"}


# ── Unavailable Dates ─────────────────────────────────────────────────────────

@router.get("/{tour_id}/unavailable-dates")
def tour_unavailable(tour_id: int, db: Session = Depends(get_db), _: User = Depends(require_any_permission(VIEW))):
    return {"status": "success", "data": list_unavailable_dates(db, tour_id)}


@router.post("/{tour_id}/unavailable-dates")
def add_unavailable(tour_id: int, data: UnavailableDatePayload, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission(EDIT))):
    return {"status": "success", "data": create_unavailable_date(db, tour_id, data, current_user, request)}


@router.delete("/{tour_id}/unavailable-dates/{date_id}")
def remove_unavailable(tour_id: int, date_id: int, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission(EDIT))):
    delete_unavailable_date(db, tour_id, date_id, current_user, request)
    return {"status": "success", "message": "Unavailable date deleted"}


# ── Discounts ─────────────────────────────────────────────────────────────────

@router.get("/{tour_id}/discounts")
def tour_discounts(tour_id: int, db: Session = Depends(get_db), _: User = Depends(require_any_permission(VIEW))):
    return {"status": "success", "data": list_discounts(db, tour_id)}


@router.post("/{tour_id}/discounts")
def add_discount(tour_id: int, data: DiscountPayload, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission(EDIT))):
    return {"status": "success", "data": create_discount(db, tour_id, data, current_user, request)}


@router.put("/{tour_id}/discounts/{discount_id}")
def edit_discount(tour_id: int, discount_id: int, data: DiscountPayload, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission(EDIT))):
    return {"status": "success", "data": update_discount(db, tour_id, discount_id, data, current_user, request)}


@router.delete("/{tour_id}/discounts/{discount_id}")
def remove_discount(tour_id: int, discount_id: int, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission(EDIT))):
    delete_discount(db, tour_id, discount_id, current_user, request)
    return {"status": "success", "message": "Discount deleted"}


# ── Price Calculation ─────────────────────────────────────────────────────────

@router.post("/{tour_id}/calculate-price")
def tour_calculate_price(tour_id: int, req: PriceCalculationRequest, db: Session = Depends(get_db), _: User = Depends(require_any_permission(VIEW))):
    return {"status": "success", "data": calculate_price(db, tour_id, req)}
