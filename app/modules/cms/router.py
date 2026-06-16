from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.modules.cms.models import City, Country, Tour, TourCategory, TourSubcategory
from app.modules.cms.schemas import CategoryPayload, CityPayload, CountryPayload, StatusUpdate, SubcategoryPayload, TourPayload
from app.modules.cms.service import _category, _city, _country, _subcategory, _tour, get_tour, list_categories, list_cities, list_countries, list_subcategories, list_tours, save_category, save_city, save_country, save_subcategory, save_tour, update_status
from app.modules.common.auth import require_any_permission
from app.modules.common.pagination import pagination_params
from app.modules.users.models import User

router = APIRouter(tags=["CMS"])


@router.get("/countries")
def countries(params: dict = Depends(pagination_params), db: Session = Depends(get_db), _=Depends(require_any_permission("countries.view"))):
    return {"status": "success", **list_countries(db, params["page"], params["limit"], params["search"])}


@router.post("/countries")
def add_country(data: CountryPayload, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("countries.create"))):
    return {"status": "success", "data": save_country(db, data, current_user, request)}


@router.get("/countries/{country_id}")
def country_detail(country_id: int, db: Session = Depends(get_db), _=Depends(require_any_permission("countries.view"))):
    from app.modules.operations import get_or_404
    return {"status": "success", "data": _country(get_or_404(db, Country, country_id, "Country"))}


@router.put("/countries/{country_id}")
def edit_country(country_id: int, data: CountryPayload, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("countries.edit"))):
    return {"status": "success", "data": save_country(db, data, current_user, request, country_id)}


@router.patch("/countries/{country_id}/status")
def country_status(country_id: int, data: StatusUpdate, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("countries.disable", "countries.edit"))):
    return {"status": "success", "data": update_status(db, Country, _country, country_id, data, current_user, "country", request)}


@router.get("/cities")
def cities(params: dict = Depends(pagination_params), country_id: str = Query(default=""), db: Session = Depends(get_db), _=Depends(require_any_permission("cities.view"))):
    return {"status": "success", **list_cities(db, params["page"], params["limit"], params["search"], country_id)}


@router.post("/cities")
def add_city(data: CityPayload, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("cities.create"))):
    return {"status": "success", "data": save_city(db, data, current_user, request)}


@router.get("/cities/{city_id}")
def city_detail(city_id: int, db: Session = Depends(get_db), _=Depends(require_any_permission("cities.view"))):
    from app.modules.operations import get_or_404
    return {"status": "success", "data": _city(get_or_404(db, City, city_id, "City"))}


@router.put("/cities/{city_id}")
def edit_city(city_id: int, data: CityPayload, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("cities.edit"))):
    return {"status": "success", "data": save_city(db, data, current_user, request, city_id)}


@router.patch("/cities/{city_id}/status")
def city_status(city_id: int, data: StatusUpdate, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("cities.disable", "cities.edit"))):
    return {"status": "success", "data": update_status(db, City, _city, city_id, data, current_user, "city", request)}


@router.get("/tour-categories")
def categories(params: dict = Depends(pagination_params), db: Session = Depends(get_db), _=Depends(require_any_permission("categories.view"))):
    return {"status": "success", **list_categories(db, params["page"], params["limit"], params["search"])}


@router.post("/tour-categories")
def add_category(data: CategoryPayload, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("categories.create"))):
    return {"status": "success", "data": save_category(db, data, current_user, request)}


@router.get("/tour-categories/{category_id}")
def category_detail(category_id: int, db: Session = Depends(get_db), _=Depends(require_any_permission("categories.view"))):
    from app.modules.operations import get_or_404
    return {"status": "success", "data": _category(get_or_404(db, TourCategory, category_id, "Category"))}


@router.put("/tour-categories/{category_id}")
def edit_category(category_id: int, data: CategoryPayload, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("categories.edit"))):
    return {"status": "success", "data": save_category(db, data, current_user, request, category_id)}


@router.patch("/tour-categories/{category_id}/status")
def category_status(category_id: int, data: StatusUpdate, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("categories.disable", "categories.edit"))):
    return {"status": "success", "data": update_status(db, TourCategory, _category, category_id, data, current_user, "category", request)}


@router.get("/tour-subcategories")
def subcategories(params: dict = Depends(pagination_params), category_id: str = Query(default=""), db: Session = Depends(get_db), _=Depends(require_any_permission("subcategories.view"))):
    return {"status": "success", **list_subcategories(db, params["page"], params["limit"], params["search"], category_id)}


@router.post("/tour-subcategories")
def add_subcategory(data: SubcategoryPayload, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("subcategories.create"))):
    return {"status": "success", "data": save_subcategory(db, data, current_user, request)}


@router.get("/tour-subcategories/{subcategory_id}")
def subcategory_detail(subcategory_id: int, db: Session = Depends(get_db), _=Depends(require_any_permission("subcategories.view"))):
    from app.modules.operations import get_or_404
    return {"status": "success", "data": _subcategory(get_or_404(db, TourSubcategory, subcategory_id, "Subcategory"))}


@router.put("/tour-subcategories/{subcategory_id}")
def edit_subcategory(subcategory_id: int, data: SubcategoryPayload, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("subcategories.edit"))):
    return {"status": "success", "data": save_subcategory(db, data, current_user, request, subcategory_id)}


@router.patch("/tour-subcategories/{subcategory_id}/status")
def subcategory_status(subcategory_id: int, data: StatusUpdate, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("subcategories.disable", "subcategories.edit"))):
    return {"status": "success", "data": update_status(db, TourSubcategory, _subcategory, subcategory_id, data, current_user, "subcategory", request)}


@router.get("/tours")
def tours(params: dict = Depends(pagination_params), country_id: str = Query(default=""), city_id: str = Query(default=""), category_id: str = Query(default=""), status: str = Query(default=""), db: Session = Depends(get_db), _=Depends(require_any_permission("tours.view", "view-tours"))):
    return {"status": "success", **list_tours(db, params["page"], params["limit"], params["search"], country_id, city_id, category_id, status)}


@router.post("/tours")
def add_tour(data: TourPayload, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("tours.create", "create-tours"))):
    return {"status": "success", "data": save_tour(db, data, current_user, request)}


@router.get("/tours/{tour_id}")
def tour_detail(tour_id: int, db: Session = Depends(get_db), _=Depends(require_any_permission("tours.view", "view-tours"))):
    return {"status": "success", "data": _tour(get_tour(db, tour_id))}


@router.put("/tours/{tour_id}")
def edit_tour(tour_id: int, data: TourPayload, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("tours.edit", "update-tours"))):
    return {"status": "success", "data": save_tour(db, data, current_user, request, tour_id)}


@router.patch("/tours/{tour_id}/status")
def tour_status(tour_id: int, data: StatusUpdate, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("tours.publish", "tours.disable", "tours.edit", "update-tours"))):
    return {"status": "success", "data": update_status(db, Tour, _tour, tour_id, data, current_user, "tour", request)}
