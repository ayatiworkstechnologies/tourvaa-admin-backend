"""
Public API - no authentication required.
Serves tour listing and detail for the public website.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.cms import City, Country, Tour, TourCategory, TourSubcategory
from app.services.cms import _category, _city, _country, _subcategory, _tour
from app.schemas.cms import slugify
from app.models.tours import (
    TourAccommodationExtra,
    TourCalendar,
    TourDiscount,
    TourExtension,
    TourExclusion,
    TourGalleryImage,
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


def _ser_overview(o: TourOverview):
    return {
        "duration_text": o.duration_text,
        "start_location": o.start_location,
        "end_location": o.end_location,
        "group_size": o.group_size,
        "tour_type": o.tour_type,
        "physical_rating": o.physical_rating,
    }


def _public_tour(item: Tour, departures: list[TourCalendar] | None = None):
    country_name = item.country.country_name if item.country else ""
    country_slug = slugify(country_name or "worldwide")
    return {
        "id": item.id,
        "tour_code": item.tour_code,
        "title": item.title,
        "slug": item.slug,
        "subtitle": item.subtitle,
        "price_start_per_person": item.price_start_per_person,
        "currency": item.currency,
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
        query = query.filter(or_(Tour.title.ilike(pat), Tour.short_description.ilike(pat)))
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
    return {
        "status": "success",
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": max(1, (total + limit - 1) // limit),
        "items": [_public_tour(t, departure_map.get(t.id)) for t in tours],
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
    tours = db.query(Tour).filter(Tour.status == "published").order_by(Tour.id.desc()).limit(limit).all()
    return {"status": "success", "items": [_public_tour(t) for t in tours]}


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
    pricing = db.query(TourPricing).filter(TourPricing.tour_id == tour_id).all()
    activities = db.query(TourOptionalActivity).filter(TourOptionalActivity.tour_id == tour_id).all()
    accommodations = db.query(TourAccommodationExtra).filter(TourAccommodationExtra.tour_id == tour_id).all()
    extensions = db.query(TourExtension).filter(TourExtension.tour_id == tour_id).all()
    discounts = db.query(TourDiscount).filter(TourDiscount.tour_id == tour_id, TourDiscount.status == "active").all()
    calendar = db.query(TourCalendar).filter(TourCalendar.tour_id == tour_id).order_by(TourCalendar.tour_date.asc()).all()
    similar_links = db.query(TourSimilar).filter(TourSimilar.tour_id == tour_id).all()

    similar_tours = []
    for link in similar_links:
        st = db.query(Tour).filter(Tour.id == link.similar_tour_id, Tour.status == "published").first()
        if st:
            similar_tours.append(_public_tour(st))

    return {
        "status": "success",
        "data": {
            **_public_tour(tour),
            "long_description": tour.long_description,
            "start_location": tour.start_location,
            "finish_location": tour.finish_location,
            "map_image": tour.map_image,
            "image_alt_text": tour.image_alt_text,
            "seo_title": tour.seo_title,
            "seo_description": tour.seo_description,
            "overview": _ser_overview(overview) if overview else None,
            "itineraries": [{"day": i.day_number, "title": i.day_title, "description": i.long_description or i.short_description or "", "accommodation": "", "meals": ""} for i in itineraries],
            "highlights": [{"text": h.title} for h in highlights],
            "inclusions": [{"text": i.title} for i in inclusions],
            "exclusions": [{"text": e.title} for e in exclusions],
            "gallery": [{"image_url": g.image_path, "alt_text": g.image_alt_text, "is_banner": g.image_type == "banner"} for g in gallery],
            "pricing": [{"persons_from": p.passenger_from, "persons_to": p.passenger_to, "price_per_person": float(p.final_price), "currency": p.currency} for p in pricing],
            "optional_activities": [{"id": a.id, "name": a.activity_name, "description": a.description or "", "price": float(a.price_per_person) if a.price_per_person else None, "currency": tour.currency or "USD"} for a in activities],
            "accommodations": [{"id": a.id, "name": a.accommodation_name, "description": a.description or "", "price": float(a.extra_price) if a.extra_price else None} for a in accommodations],
            "extensions": [{"id": e.id, "title": e.extension_title, "description": e.extension_note or "", "duration_days": None, "price": float(e.extra_price) if e.extra_price else None} for e in extensions],
            "discounts": [{"label": d.discount_name, "discount_type": d.discount_type, "value": float(d.discount_value), "valid_from": str(d.start_date) if d.start_date else None, "valid_to": str(d.end_date) if d.end_date else None} for d in discounts],
            "calendar": [{"id": c.id, "date": str(c.tour_date.date() if c.tour_date else ""), "slots": max(0, c.available_seats - c.booked_seats), "status": c.status} for c in calendar],
            "similar_tours": similar_tours,
        },
    }


@router.get("/categories")
def public_categories(db: Session = Depends(get_db)):
    cats = db.query(TourCategory).filter(TourCategory.status == "active").order_by(TourCategory.category_name.asc()).all()
    return {"status": "success", "items": [_category(c) for c in cats]}


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
    return {"status": "success", "items": [_country(c) for c in countries]}


@router.get("/cities")
def public_cities(db: Session = Depends(get_db), country: str = Query(default="")):
    q = db.query(City).filter(City.status == "active")
    if country:
        c = db.query(Country).filter(Country.country_name.ilike(country)).first()
        if c:
            q = q.filter(City.country_id == c.id)
    cities = q.order_by(City.city_name.asc()).all()
    return {"status": "success", "items": [_city(c) for c in cities]}
