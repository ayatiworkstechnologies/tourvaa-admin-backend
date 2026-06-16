from fastapi import HTTPException, Request
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.modules.audit.service import log_audit
from app.modules.cms.models import City, Country, Tour, TourCategory, TourSubcategory, TourSubcategoryMap
from app.modules.cms.schemas import CategoryPayload, CityPayload, CountryPayload, StatusUpdate, SubcategoryPayload, TourPayload, slugify
from app.modules.operations import code_for, get_or_404, simple_paginate
from app.modules.users.models import User


def _country(item: Country):
    return {"id": item.id, "country_name": item.country_name, "country_code": item.country_code, "phone_code": item.phone_code, "currency_code": item.currency_code, "status": item.status, "created_at": item.created_at, "updated_at": item.updated_at}


def _city(item: City):
    return {"id": item.id, "country_id": item.country_id, "country_name": item.country.country_name if item.country else "", "city_name": item.city_name, "status": item.status, "created_at": item.created_at, "updated_at": item.updated_at}


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
        "short_description": item.short_description,
        "long_description": item.long_description,
        "seo_title": item.seo_title,
        "seo_description": item.seo_description,
        "seo_keywords": item.seo_keywords,
        "image_alt_text": item.image_alt_text,
        "banner_image": item.banner_image,
        "map_image": item.map_image,
        "status": item.status,
        "created_by": item.created_by,
        "updated_by": item.updated_by,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }


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


def list_cities(db: Session, page: int, limit: int, search: str = "", country_id: str = ""):
    query = db.query(City)
    if search:
        query = query.filter(City.city_name.ilike(f"%{search.strip()}%"))
    if country_id:
        query = query.filter(City.country_id == int(country_id))
    return simple_paginate(query.order_by(City.city_name.asc()), page, limit, _city)


def save_city(db: Session, data: CityPayload, actor: User, request: Request | None = None, city_id: int | None = None):
    get_or_404(db, Country, data.country_id, "Country")
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


def list_tours(db: Session, page: int, limit: int, search: str = "", country_id: str = "", city_id: str = "", category_id: str = "", status: str = ""):
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
    return simple_paginate(query.order_by(Tour.id.desc()), page, limit, _tour)


def get_tour(db: Session, tour_id: int):
    return get_or_404(db, Tour, tour_id, "Tour")


def save_tour(db: Session, data: TourPayload, actor: User, request: Request | None = None, tour_id: int | None = None):
    item = get_tour(db, tour_id) if tour_id else Tour(created_by=actor.id)
    old = _tour(item) if tour_id else None
    payload = data.model_dump()
    subcategory_ids = payload.pop("subcategory_ids", [])
    payload["slug"] = _unique_slug(db, Tour, payload["slug"] or payload["title"], tour_id)
    for key, value in payload.items():
        setattr(item, key, value)
    item.updated_by = actor.id
    db.add(item)
    db.flush()
    if not item.tour_code:
        item.tour_code = code_for("TVA-TOUR", item.id)
    item.subcategory_links = [TourSubcategoryMap(subcategory_id=subcategory_id) for subcategory_id in subcategory_ids]
    log_audit(db, actor=actor, action="update_tour" if tour_id else "create_tour", entity_type="tour", entity_id=item.id, old_values=old, new_values=_tour(item), request=request)
    db.commit()
    db.refresh(item)
    return _tour(item)


def update_status(db: Session, model, serializer, item_id: int, data: StatusUpdate, actor: User, entity_type: str, request: Request | None = None):
    item = get_or_404(db, model, item_id, entity_type.title())
    old = serializer(item)
    item.status = data.status
    log_audit(db, actor=actor, action=f"update_{entity_type}_status", entity_type=entity_type, entity_id=item.id, old_values=old, new_values=serializer(item), request=request)
    db.commit()
    db.refresh(item)
    return serializer(item)
