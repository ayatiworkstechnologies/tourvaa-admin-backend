from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.services.cms import list_tours, get_tour, _tour
from app.services.tours import (
    get_overview,
    list_itineraries,
    list_inclusions,
    list_exclusions,
    list_highlights,
    list_similar_tours,
    list_gallery,
    list_activities,
    list_calendar,
    list_pricing,
)

router = APIRouter(prefix="/client", tags=["Client"])


@router.get("/config")
def client_config():
    return {
        "status": "success",
        "message": "Client configuration loaded",
        "data": {
            "api_base_url": settings.API_BASE_URL,
            "api_prefix": "/api",
            "auth": {
                "type": "bearer",
                "header": "Authorization",
                "format": "Bearer <access_token>",
            },
            "clients": {
                "web": {
                    "reset_password_url": f"{settings.FRONTEND_URL}/reset-password",
                },
                "mobile": {
                    "reset_password_url": settings.MOBILE_DEEP_LINK_URL,
                },
            },
            "uploads": {
                "profile_image": {
                    "max_size_mb": 2,
                    "mime_types": ["image/png", "image/jpeg", "image/webp"],
                }
            },
            "headers": {
                "client_type": "X-Client-Type",
                "client_version": "X-Client-Version",
                "device_id": "X-Device-Id",
            },
        },
    }

@router.get("/tours")
def public_tours(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=10, ge=1, le=100),
    search: str = Query(default=""),
    country_id: str = Query(default=""),
    city_id: str = Query(default=""),
    category_id: str = Query(default=""),
    db: Session = Depends(get_db)
):
    return {
        "status": "success",
        **list_tours(db, page, limit, search, country_id, city_id, category_id, status="published")
    }

@router.get("/tours/{tour_id}")
def public_tour_detail(tour_id: int, db: Session = Depends(get_db)):
    tour = get_tour(db, tour_id)
    if tour.status != "published":
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Tour not found")
    return {"status": "success", "data": _tour(tour)}

@router.get("/tours/{tour_id}/overview")
def public_tour_overview(tour_id: int, db: Session = Depends(get_db)):
    return {"status": "success", "data": get_overview(db, tour_id)}

@router.get("/tours/{tour_id}/itineraries")
def public_tour_itineraries(tour_id: int, db: Session = Depends(get_db)):
    return {"status": "success", "data": list_itineraries(db, tour_id)}

@router.get("/tours/{tour_id}/inclusions")
def public_tour_inclusions(tour_id: int, db: Session = Depends(get_db)):
    return {"status": "success", "data": list_inclusions(db, tour_id)}

@router.get("/tours/{tour_id}/exclusions")
def public_tour_exclusions(tour_id: int, db: Session = Depends(get_db)):
    return {"status": "success", "data": list_exclusions(db, tour_id)}

@router.get("/tours/{tour_id}/highlights")
def public_tour_highlights(tour_id: int, db: Session = Depends(get_db)):
    return {"status": "success", "data": list_highlights(db, tour_id)}

@router.get("/tours/{tour_id}/similar-tours")
def public_tour_similar_tours(tour_id: int, db: Session = Depends(get_db)):
    return {"status": "success", "data": list_similar_tours(db, tour_id)}

@router.get("/tours/{tour_id}/gallery")
def public_tour_gallery(tour_id: int, db: Session = Depends(get_db)):
    return {"status": "success", "data": list_gallery(db, tour_id)}

@router.get("/tours/{tour_id}/optional-activities")
def public_tour_activities(tour_id: int, db: Session = Depends(get_db)):
    return {"status": "success", "data": list_activities(db, tour_id)}

@router.get("/tours/{tour_id}/calendar")
def public_tour_calendar(tour_id: int, db: Session = Depends(get_db)):
    return {"status": "success", "data": list_calendar(db, tour_id)}

@router.get("/tours/{tour_id}/pricing")
def public_tour_pricing(tour_id: int, db: Session = Depends(get_db)):
    # Strip internal cost/margin fields (supplier_price, markup_type, markup_value)
    # before returning pricing slabs to unauthenticated public clients.
    rows = list_pricing(db, tour_id)
    public_fields = (
        "id", "tour_id", "passenger_from", "passenger_to",
        "adult_price", "child_price", "final_price", "currency", "status",
        "created_at", "updated_at",
    )
    safe_rows = [{k: row.get(k) for k in public_fields} for row in rows]
    return {"status": "success", "data": safe_rows}
