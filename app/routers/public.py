"""
Public API - no authentication required.
Serves tour listing and detail for the public website.
"""
import html as html_escape
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.cms import City, Country, Tour, TourCategory, TourSubcategory
from app.models.cancellations import RefundRule
from app.models.public_leads import ContactMessage, NewsletterSubscriber
from app.services.cms import _category, _city, _country, _subcategory, _tour
from app.services.reviews import get_review_stats, list_tour_reviews
from app.services.settings import sanitize_public_contact_setting
from app.schemas.cms import slugify
from app.utils.ratelimit import check_rate_limit
from app.models.tours import (
    TourAccommodationExtra,
    TourCalendar,
    TourDiscount,
    TourExtension,
    TourExclusion,
    TourGalleryImage,
    TourGroupDiscountTier,
    TourHighlight,
    TourInclusion,
    TourItinerary,
    TourOptionalActivity,
    TourOverview,
    TourPricing,
    TourSimilar,
)

router = APIRouter(tags=["Public"])

PAGE_SIZE = 12


class ContactMessageRequest(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    email: EmailStr
    phone: str = Field(default="", max_length=30)
    enquiry_type: str = Field(default="General enquiry", max_length=50)
    subject: str = Field(min_length=1, max_length=200)
    message: str = Field(min_length=1, max_length=5000)


@router.post("/contact")
def submit_contact_message(request: Request, data: ContactMessageRequest, db: Session = Depends(get_db)):
    check_rate_limit(request, "contact", max_calls=5, window_seconds=300)
    from app.models.settings import AppSetting
    from app.utils.mailer import try_send_email

    message = ContactMessage(
        name=data.name,
        email=str(data.email),
        phone=data.phone or None,
        enquiry_type=data.enquiry_type,
        subject=data.subject,
        message=data.message,
    )
    db.add(message)
    db.commit()

    setting = db.query(AppSetting).filter(AppSetting.key == "support_email").first()
    support_email = sanitize_public_contact_setting("support_email", setting.value if setting else "")

    esc = html_escape.escape
    body = (
        f"<p><strong>New enquiry from the Tourvaa website contact form</strong></p>"
        f"<p><strong>Name:</strong> {esc(data.name)}</p>"
        f"<p><strong>Email:</strong> {esc(data.email)}</p>"
        f"<p><strong>Phone:</strong> {esc(data.phone) or '-'}</p>"
        f"<p><strong>Enquiry type:</strong> {esc(data.enquiry_type)}</p>"
        f"<p><strong>Subject:</strong> {esc(data.subject)}</p>"
        f"<p><strong>Message:</strong><br/>{esc(data.message).replace(chr(10), '<br/>')}</p>"
    )
    if support_email:
        try_send_email(support_email, f"New enquiry: {data.subject}", body, template_key="contact_enquiry")
    return {"status": "success", "message": "Your enquiry has been received."}


class NewsletterSubscribeRequest(BaseModel):
    email: EmailStr


@router.post("/newsletter/subscribe")
def subscribe_newsletter(request: Request, data: NewsletterSubscribeRequest, db: Session = Depends(get_db)):
    check_rate_limit(request, "newsletter-subscribe", max_calls=5, window_seconds=300)
    from app.models.settings import AppSetting
    from app.utils.mailer import try_send_email

    email = str(data.email).strip().lower()
    existing = db.query(NewsletterSubscriber).filter(NewsletterSubscriber.email == email).first()
    if existing:
        if not existing.is_active:
            existing.is_active = True
            db.commit()
    else:
        db.add(NewsletterSubscriber(email=email))
        db.commit()

    setting = db.query(AppSetting).filter(AppSetting.key == "support_email").first()
    support_email = sanitize_public_contact_setting("support_email", setting.value if setting else "")

    esc = html_escape.escape
    body = f"<p><strong>New newsletter signup from the Tourvaa website</strong></p><p><strong>Email:</strong> {esc(email)}</p>"
    if support_email:
        try_send_email(support_email, "New newsletter signup", body, template_key="newsletter_signup")
    return {"status": "success", "message": "You're subscribed! Watch your inbox for travel inspiration."}


def _safe_json_list(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return []
    return value if isinstance(value, list) else []


def _ser_overview(o: TourOverview):
    return {
        "duration_text": o.duration_text,
        "start_location": o.start_location,
        "end_location": o.end_location,
        "group_size": o.group_size,
        "tour_type": o.tour_type,
        "physical_rating": o.physical_rating,
        "why_choose_this_tour": o.why_choose_this_tour,
        "ideal_for": o.ideal_for,
        "best_season": o.best_season,
        "tour_pace": o.tour_pace,
        "transportation_summary": o.transportation_summary,
        "accommodation_summary": o.accommodation_summary,
        "meal_summary": o.meal_summary,
    }


def _active_discount_map(db: Session, tours: list[Tour]) -> dict[int, dict]:
    """Best active tour-scoped discount per tour, expressed as a percentage
    off price_start_per_person (a fixed-amount discount is converted to its
    percentage-equivalent for the "Save X% today" badge). Mirrors the
    active-window filter in public_tour_detail's own discounts query, but
    only ever matches TourDiscount.tour_id directly - category/country-scoped
    discounts (discount_scope) are not resolved here, consistent with the
    detail endpoint's existing behavior."""
    tour_ids = [t.id for t in tours]
    if not tour_ids:
        return {}
    now = datetime.now(timezone.utc)
    rows = (
        db.query(TourDiscount)
        .filter(
            TourDiscount.tour_id.in_(tour_ids),
            TourDiscount.status == "active",
            or_(TourDiscount.start_date.is_(None), TourDiscount.start_date <= now),
            or_(TourDiscount.end_date.is_(None), TourDiscount.end_date >= now),
        )
        .all()
    )
    if not rows:
        return {}
    price_by_tour = {t.id: float(t.price_start_per_person or 0) for t in tours}
    best: dict[int, dict] = {}
    for row in rows:
        base_price = price_by_tour.get(row.tour_id, 0)
        if base_price <= 0:
            continue
        pct = float(row.discount_value) if row.discount_type == "percentage" else (float(row.discount_value) / base_price) * 100
        pct = round(min(90.0, max(0.0, pct)))
        if pct <= 0:
            continue
        existing = best.get(row.tour_id)
        if not existing or pct > existing["discount_percentage"]:
            best[row.tour_id] = {
                "discount_percentage": pct,
                "original_price_per_person": base_price,
                "discounted_price_per_person": round(base_price * (1 - pct / 100), 2),
            }
    return best


def _public_pricing_rows(pricing: list[TourPricing], tiers: list[TourGroupDiscountTier]) -> list[dict]:
    """A tour now has one active base TourPricing row (1 person, see
    services.tours._apply_pricing_computation) plus separate
    TourGroupDiscountTier rows for group-size discounts. The public tour
    page still shows one row per traveller-count range, so this expands
    the base price into: the base row up to the first tier's min_pax, then
    one row per active tier with its own discounted price - using the same
    formula _price_booking / _resolve_group_discount applies at checkout,
    so the advertised price always matches what a booking is actually
    charged."""
    if not pricing:
        return []
    base = pricing[0]
    base_adult = float(base.storefront_adult_price if base.storefront_adult_price is not None else base.adult_price)
    rows = []
    solo_upper = (tiers[0].min_pax - 1) if tiers else base.passenger_to
    rows.append({"persons_from": base.passenger_from, "persons_to": solo_upper, "price_per_person": base_adult, "currency": base.currency})
    for tier in tiers:
        if tier.discount_type == "percentage":
            price = base_adult * (1 - float(tier.discount_value) / 100)
        else:
            price = base_adult - float(tier.discount_value)
        rows.append({"persons_from": tier.min_pax, "persons_to": tier.max_pax, "price_per_person": round(max(0.0, price), 2), "currency": base.currency})
    return rows


def _public_tour(item: Tour, departures: list[TourCalendar] | None = None, review_stats: dict[int, dict] | None = None, overview: TourOverview | None = None, discount_map: dict[int, dict] | None = None):
    country_name = item.country.country_name if item.country else ""
    country_slug = slugify(country_name or "worldwide")
    stats = (review_stats or {}).get(item.id)
    discount_info = (discount_map or {}).get(item.id)
    return {
        "id": item.id,
        "tour_code": item.tour_code,
        "supplier_name": item.supplier.supplier_name if item.supplier else "",
        "title": item.title,
        "slug": item.slug,
        "subtitle": item.subtitle,
        "price_start_per_person": item.price_start_per_person,
        "currency": item.currency,
        "discount_percentage": discount_info["discount_percentage"] if discount_info else None,
        "original_price_per_person": discount_info["original_price_per_person"] if discount_info else None,
        "discounted_price_per_person": discount_info["discounted_price_per_person"] if discount_info else None,
        "country_name": country_name,
        "country_slug": country_slug,
        "city_name": item.city.city_name if item.city else "",
        "category_name": item.category.category_name if item.category else "",
        "number_of_days": item.number_of_days,
        "number_of_hours": item.number_of_hours,
        "short_description": item.short_description,
        "banner_image": item.banner_image,
        "status": item.status,
        "canonical_path": f"/tours/{country_slug}/{item.slug}",
        "departures": [
            {
                "id": departure.id,
                "date": str(departure.tour_date.date()),
                "slots": max(0, departure.available_seats - departure.booked_seats),
                "status": departure.status,
            }
            for departure in (departures or [])
        ],
        "rating_average": stats["average"] if stats else None,
        "rating_count": stats["count"] if stats else 0,
        "start_location": overview.start_location if overview and overview.start_location else None,
        "end_location": overview.end_location if overview and overview.end_location else None,
        "group_size": overview.group_size if overview and overview.group_size else None,
    }


@router.get("/tours")
def public_tours(
    db: Session = Depends(get_db),
    search: str = Query(default=""),
    country: str = Query(default=""),
    city: str = Query(default=""),
    category: str = Query(default=""),
    subcategory: str = Query(default=""),
    min_days: str = Query(default=""),
    max_days: str = Query(default=""),
    min_price: str = Query(default=""),
    max_price: str = Query(default=""),
    departure_month: str = Query(default="", pattern=r"^$|^\d{4}-\d{2}$"),
    available_only: bool = Query(default=False),
    sort: str = Query(default="newest", pattern="^(newest|price_asc|price_desc|duration_asc)$"),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=PAGE_SIZE, ge=1, le=100),
):
    query = db.query(Tour).filter(Tour.status == "published")
    if search:
        pat = f"%{search.strip()}%"
        query = query.filter(
            or_(
                Tour.title.ilike(pat),
                Tour.tour_code.ilike(pat),
                Tour.slug.ilike(pat),
                Tour.short_description.ilike(pat),
                Tour.start_location.ilike(pat),
                Tour.finish_location.ilike(pat),
                Tour.country.has(Country.country_name.ilike(pat)),
                Tour.city.has(City.city_name.ilike(pat)),
                Tour.category.has(TourCategory.category_name.ilike(pat)),
            )
        )
    if country:
        c = db.query(Country).filter(Country.country_name.ilike(country)).first()
        if not c:
            c = next((item for item in db.query(Country).all() if slugify(item.country_name) == slugify(country)), None)
        if c:
            query = query.filter(Tour.country_id == c.id)
        else:
            query = query.filter(Tour.id == -1)
    if city:
        ci = db.query(City).filter(City.city_name.ilike(city)).first()
        if ci:
            query = query.filter(Tour.city_id == ci.id)
    if category:
        cat = db.query(TourCategory).filter(
            or_(TourCategory.slug == category, TourCategory.category_name.ilike(category))
        ).first()
        if cat:
            query = query.filter(Tour.category_id == cat.id)
    if subcategory:
        sub = db.query(TourSubcategory).filter(
            or_(TourSubcategory.slug == subcategory, TourSubcategory.subcategory_name.ilike(subcategory))
        ).first()
        if sub:
            from app.models.cms import TourSubcategoryMap
            tour_ids = [m.tour_id for m in db.query(TourSubcategoryMap).filter(TourSubcategoryMap.subcategory_id == sub.id).all()]
            query = query.filter(Tour.id.in_(tour_ids))
    if min_days:
        try:
            query = query.filter(Tour.number_of_days >= int(min_days))
        except ValueError:
            pass
    if max_days:
        try:
            query = query.filter(Tour.number_of_days <= int(max_days))
        except ValueError:
            pass
    if min_price:
        try:
            query = query.filter(Tour.price_start_per_person >= float(min_price))
        except ValueError:
            pass
    if max_price:
        try:
            query = query.filter(Tour.price_start_per_person <= float(max_price))
        except ValueError:
            pass

    calendar_query = db.query(TourCalendar.tour_id).filter(
        TourCalendar.status == "available",
        TourCalendar.available_seats > TourCalendar.booked_seats,
        TourCalendar.tour_date >= datetime.now(timezone.utc),
    )
    if departure_month:
        month_start = datetime.strptime(f"{departure_month}-01", "%Y-%m-%d").replace(tzinfo=timezone.utc)
        next_month = datetime(month_start.year + (month_start.month == 12), (month_start.month % 12) + 1, 1, tzinfo=timezone.utc)
        calendar_query = calendar_query.filter(TourCalendar.tour_date >= month_start, TourCalendar.tour_date < next_month)
        query = query.filter(Tour.id.in_(calendar_query))
    elif available_only:
        query = query.filter(Tour.id.in_(calendar_query))

    total = query.count()
    if sort == "price_asc":
        query = query.order_by(Tour.price_start_per_person.asc(), Tour.id.desc())
    elif sort == "price_desc":
        query = query.order_by(Tour.price_start_per_person.desc(), Tour.id.desc())
    elif sort == "duration_asc":
        query = query.order_by(Tour.number_of_days.asc(), Tour.id.desc())
    else:
        query = query.order_by(Tour.id.desc())
    tours = query.offset((page - 1) * limit).limit(limit).all()
    tour_ids = [tour.id for tour in tours]
    departure_map: dict[int, list[TourCalendar]] = {tour_id: [] for tour_id in tour_ids}
    if tour_ids:
        upcoming = db.query(TourCalendar).filter(
            TourCalendar.tour_id.in_(tour_ids),
            TourCalendar.status == "available",
            TourCalendar.available_seats > TourCalendar.booked_seats,
            TourCalendar.tour_date >= datetime.now(timezone.utc),
        ).order_by(TourCalendar.tour_date.asc()).all()
        for departure in upcoming:
            if len(departure_map[departure.tour_id]) < 3:
                departure_map[departure.tour_id].append(departure)
    review_stats = get_review_stats(db, tour_ids)
    overview_map = {o.tour_id: o for o in db.query(TourOverview).filter(TourOverview.tour_id.in_(tour_ids))} if tour_ids else {}
    discount_map = _active_discount_map(db, tours)
    return {
        "status": "success",
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": max(1, (total + limit - 1) // limit),
        "items": [_public_tour(t, departure_map.get(t.id), review_stats, overview_map.get(t.id), discount_map) for t in tours],
        "filters_applied": {
            "search": search,
            "country": country,
            "city": city,
            "category": category,
            "min_days": min_days,
            "max_days": max_days,
            "min_price": min_price,
            "max_price": max_price,
            "departure_month": departure_month,
            "available_only": available_only,
            "sort": sort,
        },
    }


@router.get("/tours/featured")
def featured_tours(db: Session = Depends(get_db), limit: int = Query(default=6, le=20)):
    # Tours an admin actually marked Featured come first; if there aren't
    # enough of those yet, fill the rest with the most recently published
    # tours so this section (and the homepage sections built from it)
    # isn't empty before any admin has used the Featured toggle.
    featured = (
        db.query(Tour)
        .filter(Tour.status == "published", Tour.featured == True)  # noqa: E712
        .order_by(Tour.id.desc())
        .limit(limit)
        .all()
    )
    tours = featured
    if len(tours) < limit:
        exclude_ids = [t.id for t in tours]
        fallback_query = db.query(Tour).filter(Tour.status == "published")
        if exclude_ids:
            fallback_query = fallback_query.filter(Tour.id.notin_(exclude_ids))
        tours = tours + fallback_query.order_by(Tour.id.desc()).limit(limit - len(tours)).all()
    tour_ids = [t.id for t in tours]
    review_stats = get_review_stats(db, tour_ids)
    overview_map = {o.tour_id: o for o in db.query(TourOverview).filter(TourOverview.tour_id.in_(tour_ids))} if tour_ids else {}
    discount_map = _active_discount_map(db, tours)
    return {"status": "success", "items": [_public_tour(t, review_stats=review_stats, overview=overview_map.get(t.id), discount_map=discount_map) for t in tours]}


@router.get("/tours/{country_slug}/{tour_slug}")
def public_tour_detail_by_slug(country_slug: str, tour_slug: str, db: Session = Depends(get_db)):
    """Resolve the canonical public tour URL and reject mismatched countries."""
    from fastapi import HTTPException

    tour = db.query(Tour).filter(Tour.slug == tour_slug, Tour.status == "published").first()
    if not tour:
        raise HTTPException(status_code=404, detail="Tour not found")
    expected_country = slugify(tour.country.country_name if tour.country else "worldwide")
    if country_slug != expected_country:
        raise HTTPException(
            status_code=404,
            detail={"message": "Tour not found for this country", "canonical_path": f"/tours/{expected_country}/{tour.slug}"},
        )
    return public_tour_detail(tour.slug, db)


@router.get("/tours/{tour_id}")
def public_tour_detail(tour_id: str, db: Session = Depends(get_db)):
    from fastapi import HTTPException
    lookup = Tour.id == int(tour_id) if tour_id.isdigit() else Tour.slug == tour_id
    tour = db.query(Tour).filter(lookup, Tour.status == "published").first()
    if not tour:
        raise HTTPException(status_code=404, detail="Tour not found")

    tour_id = tour.id

    overview = db.query(TourOverview).filter(TourOverview.tour_id == tour_id).first()
    itineraries = db.query(TourItinerary).filter(TourItinerary.tour_id == tour_id).order_by(TourItinerary.day_number.asc()).all()
    highlights = db.query(TourHighlight).filter(TourHighlight.tour_id == tour_id).all()
    inclusions = db.query(TourInclusion).filter(TourInclusion.tour_id == tour_id).all()
    exclusions = db.query(TourExclusion).filter(TourExclusion.tour_id == tour_id).all()
    gallery = db.query(TourGalleryImage).filter(TourGalleryImage.tour_id == tour_id).order_by(TourGalleryImage.display_order.asc()).all()
    pricing = db.query(TourPricing).filter(TourPricing.tour_id == tour_id, TourPricing.status == "active").all()
    group_discount_tiers = (
        db.query(TourGroupDiscountTier)
        .filter(TourGroupDiscountTier.tour_id == tour_id, TourGroupDiscountTier.status == "active")
        .order_by(TourGroupDiscountTier.min_pax.asc())
        .all()
    )
    activities = db.query(TourOptionalActivity).filter(TourOptionalActivity.tour_id == tour_id).all()
    accommodations = db.query(TourAccommodationExtra).filter(TourAccommodationExtra.tour_id == tour_id).all()
    extensions = db.query(TourExtension).filter(TourExtension.tour_id == tour_id).all()
    # status == "active" alone isn't enough - an admin-created discount stays
    # "active" across its whole lifecycle, so a since-expired or not-yet-started
    # offer would otherwise still be advertised here even though
    # _resolve_discount (bookings.py) already rejects it at actual checkout.
    _discount_now = datetime.now(timezone.utc)
    discounts = (
        db.query(TourDiscount)
        .filter(
            TourDiscount.tour_id == tour_id,
            TourDiscount.status == "active",
            or_(TourDiscount.start_date.is_(None), TourDiscount.start_date <= _discount_now),
            or_(TourDiscount.end_date.is_(None), TourDiscount.end_date >= _discount_now),
        )
        .all()
    )
    calendar = (
        db.query(TourCalendar)
        .filter(TourCalendar.tour_id == tour_id, TourCalendar.tour_date >= datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0))
        .order_by(TourCalendar.tour_date.asc())
        .all()
    )
    from app.models.tours import TourAvailabilityConfig
    availability_config = db.query(TourAvailabilityConfig).filter(TourAvailabilityConfig.tour_id == tour_id).first()
    similar_links = db.query(TourSimilar).filter(TourSimilar.tour_id == tour_id).all()
    tour_refund_rules = (
        db.query(RefundRule)
        .filter(RefundRule.tour_id == tour_id)
        .order_by(RefundRule.days_before_tour_min.desc())
        .all()
    )
    refund_rules = tour_refund_rules or (
        db.query(RefundRule)
        .filter(RefundRule.tour_id.is_(None))
        .order_by(RefundRule.days_before_tour_min.desc())
        .all()
    )
    review_stats = get_review_stats(db, [tour_id])
    reviews = list_tour_reviews(db, tour_id)

    similar_tour_rows = []
    for link in similar_links:
        st = db.query(Tour).filter(Tour.id == link.similar_tour_id, Tour.status == "published").first()
        if st:
            similar_tour_rows.append(st)
    similar_discount_map = _active_discount_map(db, similar_tour_rows)
    similar_tours = [_public_tour(st, discount_map=similar_discount_map) for st in similar_tour_rows]
    own_discount_map = _active_discount_map(db, [tour])

    return {
        "status": "success",
        "data": {
            **_public_tour(tour, review_stats=review_stats, discount_map=own_discount_map),
            "long_description": tour.long_description,
            "start_location": tour.start_location,
            "finish_location": tour.finish_location,
            "map_image": tour.map_image,
            "image_alt_text": tour.image_alt_text,
            "seo_title": tour.seo_title,
            "seo_description": tour.seo_description,
            "booking_deposit": tour.booking_deposit or None,
            "balance_payment_deadline_days": tour.balance_payment_deadline_days,
            "tour_video_url": tour.tour_video_url or None,
            "overview": _ser_overview(overview) if overview else None,
            "itineraries": [
                {
                    "day": i.day_number,
                    "title": i.day_title,
                    "description": i.long_description or i.short_description or "",
                    "location": i.location_name or "",
                    "accommodation": i.accommodation or "",
                    "meals": i.meals_included or "",
                    "transport": i.transport_type or "",
                    "start_time": i.start_time or "",
                    "end_time": i.end_time or "",
                    "travel_distance": i.travel_distance or "",
                    "travel_duration": i.travel_duration or "",
                    "important_notes": i.important_notes or "",
                    "activities": i.activities or "",
                    "optional_activities": i.optional_activities or "",
                    "image": i.image or None,
                    "images": _safe_json_list(i.images),
                }
                for i in itineraries
            ],
            "highlights": [{"text": h.title, "title": h.title, "image": h.image or None, "description": h.short_description or ""} for h in highlights],
            "inclusions": [{"text": i.title} for i in inclusions],
            "exclusions": [{"text": e.title} for e in exclusions],
            "gallery": [{"image_url": g.image_path, "alt_text": g.image_alt_text, "is_banner": g.image_type == "banner"} for g in gallery],
            # price_per_person must match what _price_booking (bookings.py)
            # actually charges at checkout, not the raw just-entered
            # adult_price - those diverge whenever a supplier's edit to a
            # live tour is frozen pending admin approval (see
            # services.tours._apply_pricing_computation's freeze guard).
            # See _public_pricing_rows for how the base price + group
            # discount tiers are expanded into these traveller-count rows.
            "pricing": _public_pricing_rows(pricing, group_discount_tiers),
            "optional_activities": [{"id": a.id, "name": a.activity_name, "description": a.description or "", "price": float(a.price_per_person) if a.price_per_person else None, "currency": tour.currency or "USD", "category": a.category or "other", "image": a.image or None} for a in activities],
            "accommodations": [{"id": a.id, "name": a.accommodation_name, "description": a.description or "", "price": float(a.extra_price) if a.extra_price else None, "category": a.category or "room_upgrade", "image": a.image or None} for a in accommodations],
            "extensions": [{"id": e.id, "title": e.extension_title, "description": e.extension_note or "", "duration_days": None, "price": float(e.extra_price) if e.extra_price else None, "category": e.category or "other", "image": (e.extension_tour.banner_image or None) if e.extension_tour else None} for e in extensions],
            "discounts": [{"label": d.discount_name, "discount_type": d.discount_type, "value": float(d.discount_value), "valid_from": str(d.start_date) if d.start_date else None, "valid_to": str(d.end_date) if d.end_date else None} for d in discounts],
            "calendar": [{"id": c.id, "date": str(c.tour_date.date() if c.tour_date else ""), "slots": max(0, c.available_seats - c.booked_seats), "status": c.status} for c in calendar],
            "min_advance_booking_days": availability_config.min_advance_booking_days if availability_config else 0,
            "availability_end_date": str(availability_config.availability_end_date.date()) if availability_config and availability_config.availability_end_date else None,
            "similar_tours": similar_tours,
            "cancellation_policy": [
                {
                    "days_before_min": r.days_before_tour_min,
                    "days_before_max": r.days_before_tour_max,
                    "refund_percentage": float(r.refund_percentage),
                    "description": r.description or "",
                }
                for r in refund_rules
            ],
            "reviews": reviews,
        },
    }


@router.get("/categories")
def public_categories(db: Session = Depends(get_db)):
    cats = db.query(TourCategory).filter(TourCategory.status == "active").order_by(TourCategory.category_name.asc()).all()
    counts = dict(
        db.query(Tour.category_id, func.count(Tour.id))
        .filter(Tour.status == "published")
        .group_by(Tour.category_id)
        .all()
    )
    items = [{**_category(c), "tour_count": counts.get(c.id, 0)} for c in cats]
    items.sort(key=lambda item: (-item["tour_count"], item["category_name"]))
    return {"status": "success", "items": items}


@router.get("/subcategories")
def public_subcategories(db: Session = Depends(get_db), category: str = Query(default="")):
    q = db.query(TourSubcategory).filter(TourSubcategory.status == "active")
    if category:
        cat = db.query(TourCategory).filter(
            or_(TourCategory.slug == category, TourCategory.id == (int(category) if category.isdigit() else -1))
        ).first()
        if cat:
            q = q.filter(TourSubcategory.category_id == cat.id)
    subs = q.order_by(TourSubcategory.subcategory_name.asc()).all()
    return {"status": "success", "items": [_subcategory(s) for s in subs]}


@router.get("/countries")
def public_countries(db: Session = Depends(get_db)):
    countries = db.query(Country).filter(Country.status == "active").order_by(Country.country_name.asc()).all()
    counts = dict(
        db.query(Tour.country_id, func.count(Tour.id))
        .filter(Tour.status == "published")
        .group_by(Tour.country_id)
        .all()
    )
    items = [{**_country(c), "tour_count": counts.get(c.id, 0)} for c in countries]
    items.sort(key=lambda item: (-item["tour_count"], item["country_name"]))
    return {"status": "success", "items": items}


@router.get("/cities")
def public_cities(db: Session = Depends(get_db), country: str = Query(default="")):
    q = db.query(City).filter(City.status == "active")
    if country:
        c = db.query(Country).filter(Country.country_name.ilike(country)).first()
        if c:
            q = q.filter(City.country_id == c.id)
    cities = q.order_by(City.city_name.asc()).all()
    counts = dict(
        db.query(Tour.city_id, func.count(Tour.id))
        .filter(Tour.status == "published")
        .group_by(Tour.city_id)
        .all()
    )
    items = [{**_city(c), "tour_count": counts.get(c.id, 0)} for c in cities]
    items.sort(key=lambda item: (-item["tour_count"], item["city_name"]))
    return {"status": "success", "items": items}
