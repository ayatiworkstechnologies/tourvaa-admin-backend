"""
Public API — no authentication required.
Serves tour listing and detail for the public website.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.cms import City, Country, Tour, TourCategory, TourSubcategory
from app.services.cms import _category, _city, _country, _subcategory, _tour
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


def _public_tour(item: Tour):
    return {
        "id": item.id,
        "tour_code": item.tour_code,
        "title": item.title,
        "slug": item.slug,
        "subtitle": item.subtitle,
        "price_start_per_person": item.price_start_per_person,
        "currency": item.currency,
        "country_name": item.country.country_name if item.country else "",
        "city_name": item.city.city_name if item.city else "",
        "category_name": item.category.category_name if item.category else "",
        "number_of_days": item.number_of_days,
        "number_of_hours": item.number_of_hours,
        "short_description": item.short_description,
        "banner_image": item.banner_image,
        "status": item.status,
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
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=PAGE_SIZE, ge=1, le=50),
):
    query = db.query(Tour).filter(Tour.status == "published")
    if search:
        pat = f"%{search.strip()}%"
        query = query.filter(or_(Tour.title.ilike(pat), Tour.short_description.ilike(pat)))
    if country:
        c = db.query(Country).filter(Country.country_name.ilike(country)).first()
        if c:
            query = query.filter(Tour.country_id == c.id)
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

    total = query.count()
    tours = query.order_by(Tour.id.desc()).offset((page - 1) * limit).limit(limit).all()
    return {
        "status": "success",
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": max(1, (total + limit - 1) // limit),
        "items": [_public_tour(t) for t in tours],
    }


@router.get("/tours/featured")
def featured_tours(db: Session = Depends(get_db), limit: int = Query(default=6, le=20)):
    tours = db.query(Tour).filter(Tour.status == "published").order_by(Tour.id.desc()).limit(limit).all()
    return {"status": "success", "items": [_public_tour(t) for t in tours]}


@router.get("/tours/{tour_id}")
def public_tour_detail(tour_id: int, db: Session = Depends(get_db)):
    from fastapi import HTTPException
    tour = db.query(Tour).filter(Tour.id == tour_id, Tour.status == "published").first()
    if not tour:
        raise HTTPException(status_code=404, detail="Tour not found")

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
            "optional_activities": [{"name": a.activity_name, "description": a.description or "", "price": float(a.price_per_person) if a.price_per_person else None, "currency": tour.currency or "AED"} for a in activities],
            "accommodations": [{"name": a.accommodation_name, "description": a.description or "", "price": float(a.extra_price) if a.extra_price else None} for a in accommodations],
            "extensions": [{"title": e.extension_title, "description": e.extension_note or "", "duration_days": None, "price": float(e.extra_price) if e.extra_price else None} for e in extensions],
            "discounts": [{"label": d.discount_name, "discount_type": d.discount_type, "value": float(d.discount_value), "valid_from": str(d.start_date) if d.start_date else None, "valid_to": str(d.end_date) if d.end_date else None} for d in discounts],
            "calendar": [{"date": str(c.tour_date.date() if c.tour_date else ""), "slots": max(0, c.available_seats - c.booked_seats), "status": c.status} for c in calendar],
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
