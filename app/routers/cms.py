from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.cms import City, Country, State, Tour, TourCategory, TourSubcategory
from app.schemas.cms import CategoryPayload, CityPayload, CountryPayload, StatePayload, StatusUpdate, SubcategoryPayload, TourPayload
from app.services.cms import _category, _city, _country, _state, _subcategory, _tour, get_tour, list_categories, list_cities, list_countries, list_states, list_subcategories, list_tours, save_category, save_city, save_country, save_state, save_subcategory, save_tour, update_status
from app.auth.permissions import get_current_user, require_any_permission
from app.utils.pagination import pagination_params
from app.models.users import User


def _get_actor_supplier_id(db: Session, user: User) -> int | None:
    """Returns the Supplier.id for the given user, or None if user is not a supplier."""
    role_slug = (user.role.slug if user.role else "") or ""
    if "supplier" not in role_slug.lower():
        return None
    from app.models.suppliers import Supplier
    supplier = db.query(Supplier).filter(Supplier.user_id == user.id).first()
    return supplier.id if supplier else None

router = APIRouter(tags=["CMS"])


@router.get("/countries")
def countries(params: dict = Depends(pagination_params), db: Session = Depends(get_db)):
    return {"status": "success", **list_countries(db, params["page"], params["limit"], params["search"])}


@router.post("/countries")
def add_country(data: CountryPayload, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("countries.create"))):
    return {"status": "success", "data": save_country(db, data, current_user, request)}


@router.get("/countries/{country_id}")
def country_detail(country_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    from app.utils.operations import get_or_404
    return {"status": "success", "data": _country(get_or_404(db, Country, country_id, "Country"))}


@router.put("/countries/{country_id}")
def edit_country(country_id: int, data: CountryPayload, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("countries.edit"))):
    return {"status": "success", "data": save_country(db, data, current_user, request, country_id)}


@router.patch("/countries/{country_id}/status")
def country_status(country_id: int, data: StatusUpdate, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("countries.disable", "countries.edit"))):
    return {"status": "success", "data": update_status(db, Country, _country, country_id, data, current_user, "country", request)}


@router.get("/states")
def states(params: dict = Depends(pagination_params), country_id: str = Query(default=""), db: Session = Depends(get_db)):
    return {"status": "success", **list_states(db, params["page"], params["limit"], params["search"], country_id)}


@router.post("/states")
def add_state(data: StatePayload, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("countries.create"))):
    return {"status": "success", "data": save_state(db, data, current_user, request)}


@router.get("/states/{state_id}")
def state_detail(state_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    from app.utils.operations import get_or_404
    return {"status": "success", "data": _state(get_or_404(db, State, state_id, "State"))}


@router.put("/states/{state_id}")
def edit_state(state_id: int, data: StatePayload, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("countries.edit"))):
    return {"status": "success", "data": save_state(db, data, current_user, request, state_id)}


@router.patch("/states/{state_id}/status")
def state_status(state_id: int, data: StatusUpdate, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("countries.edit"))):
    return {"status": "success", "data": update_status(db, State, _state, state_id, data, current_user, "state", request)}


@router.get("/cities")
def cities(params: dict = Depends(pagination_params), country_id: str = Query(default=""), state_id: str = Query(default=""), db: Session = Depends(get_db)):
    return {"status": "success", **list_cities(db, params["page"], params["limit"], params["search"], country_id, state_id)}


@router.post("/cities")
def add_city(data: CityPayload, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("cities.create"))):
    return {"status": "success", "data": save_city(db, data, current_user, request)}


@router.get("/cities/{city_id}")
def city_detail(city_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    from app.utils.operations import get_or_404
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
    from app.utils.operations import get_or_404
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
    from app.utils.operations import get_or_404
    return {"status": "success", "data": _subcategory(get_or_404(db, TourSubcategory, subcategory_id, "Subcategory"))}


@router.put("/tour-subcategories/{subcategory_id}")
def edit_subcategory(subcategory_id: int, data: SubcategoryPayload, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("subcategories.edit"))):
    return {"status": "success", "data": save_subcategory(db, data, current_user, request, subcategory_id)}


@router.patch("/tour-subcategories/{subcategory_id}/status")
def subcategory_status(subcategory_id: int, data: StatusUpdate, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("subcategories.disable", "subcategories.edit"))):
    return {"status": "success", "data": update_status(db, TourSubcategory, _subcategory, subcategory_id, data, current_user, "subcategory", request)}


@router.get("/tours")
def tours(params: dict = Depends(pagination_params), country_id: str = Query(default=""), city_id: str = Query(default=""), category_id: str = Query(default=""), status: str = Query(default=""), supplier_id: str = Query(default=""), db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("tours.view", "view-tours"))):
    # Suppliers only see their own tours; admins can filter by any supplier_id or see all
    actor_supplier_id = _get_actor_supplier_id(db, current_user)
    effective_supplier_id = str(actor_supplier_id) if actor_supplier_id else supplier_id
    return {"status": "success", **list_tours(db, params["page"], params["limit"], params["search"], country_id, city_id, category_id, status, effective_supplier_id)}


@router.post("/tours")
def add_tour(
    data: TourPayload,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_permission("tours.create", "create-tours")),
):
    actor_supplier_id = _get_actor_supplier_id(db, current_user)
    if actor_supplier_id:
        # Supplier-created tours must always remain attached to the caller's profile.
        data = data.model_copy(update={"supplier_id": actor_supplier_id})
    return {"status": "success", "data": save_tour(db, data, current_user, request)}


@router.get("/tours/categories", operation_id="cms_list_tour_categories")
def tour_categories(
    search: str = Query(default=""),
    page: int = Query(default=1),
    limit: int = Query(default=200),
    db: Session = Depends(get_db),
):
    return {"status": "success", **list_categories(db, page, limit, search)}


@router.get("/tours/{tour_id}")
def tour_detail(tour_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("tours.view", "view-tours"))):
    tour = get_tour(db, tour_id)
    actor_supplier_id = _get_actor_supplier_id(db, current_user)
    if actor_supplier_id and tour.supplier_id != actor_supplier_id:
        raise HTTPException(status_code=403, detail="Access denied: this tour belongs to another supplier")
    return {"status": "success", "data": _tour(tour)}


@router.put("/tours/{tour_id}")
def edit_tour(tour_id: int, data: TourPayload, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("tours.edit", "update-tours"))):
    tour = get_tour(db, tour_id)
    actor_supplier_id = _get_actor_supplier_id(db, current_user)
    if actor_supplier_id and tour.supplier_id != actor_supplier_id:
        raise HTTPException(status_code=403, detail="Access denied: this tour belongs to another supplier")
    # Prevent a supplier from reassigning a tour to a different supplier
    if actor_supplier_id:
        data = data.model_copy(update={"supplier_id": actor_supplier_id})
    return {"status": "success", "data": save_tour(db, data, current_user, request, tour_id)}


@router.patch("/tours/{tour_id}/status")
def tour_status(tour_id: int, data: StatusUpdate, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("tours.publish", "tours.disable", "tours.edit", "update-tours"))):
    tour = get_tour(db, tour_id)
    actor_supplier_id = _get_actor_supplier_id(db, current_user)
    if actor_supplier_id and tour.supplier_id != actor_supplier_id:
        raise HTTPException(status_code=403, detail="Access denied: this tour belongs to another supplier")
    return {"status": "success", "data": update_status(db, Tour, _tour, tour_id, data, current_user, "tour", request)}
