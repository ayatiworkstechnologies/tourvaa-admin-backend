"""
Lightweight geo reference endpoints — no auth, no pagination.
Used by dropdowns and selects across the entire frontend.

GET /api/geo/countries          → all active countries
GET /api/geo/states?country_id= → active states for a country
GET /api/geo/cities?state_id=   → active cities for a state
"""

from typing import Optional

from fastapi import APIRouter, Query
from sqlalchemy.orm import Session
from fastapi import Depends

from app.database import get_db
from app.models.cms import City, Country, State

router = APIRouter(prefix="/geo", tags=["Geo Reference"])


@router.get("/countries")
def geo_countries(db: Session = Depends(get_db)):
    rows = (
        db.query(Country)
        .filter(Country.status == "active")
        .order_by(Country.country_name.asc())
        .all()
    )
    return {
        "data": [
            {
                "id": r.id,
                "name": r.country_name,
                "code": r.country_code,
                "phone_code": r.phone_code,
                "currency_code": r.currency_code,
            }
            for r in rows
        ]
    }


@router.get("/states")
def geo_states(country_id: int = Query(..., description="Filter by country ID"), db: Session = Depends(get_db)):
    rows = (
        db.query(State)
        .filter(State.country_id == country_id, State.status == "active")
        .order_by(State.state_name.asc())
        .all()
    )
    return {
        "data": [{"id": r.id, "name": r.state_name, "code": r.state_code} for r in rows]
    }


@router.get("/cities")
def geo_cities(
    state_id: Optional[int] = Query(default=None, description="Filter by state ID"),
    country_id: Optional[int] = Query(default=None, description="Filter by country ID when state is not selected"),
    db: Session = Depends(get_db),
):
    query = db.query(City).filter(City.status == "active")
    if state_id is not None:
        query = query.filter(City.state_id == state_id)
    elif country_id is not None:
        query = query.filter(City.country_id == country_id)
    else:
        return {"data": []}

    rows = query.order_by(City.city_name.asc()).all()
    return {"data": [{"id": r.id, "name": r.city_name} for r in rows]}
