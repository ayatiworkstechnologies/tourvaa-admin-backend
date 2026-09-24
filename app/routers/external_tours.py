"""External tours (Day Tours & Experiences) API.

public_router -> /api/public/external-tours/*  (no auth; click tracking
                 attributes the user/agent when a session is present)
admin_router  -> /api/integrations/external-tours/*  (settings permissions)

Provider defaults to VIATOR; the paths stay provider-agnostic so another
provider can be added without new public URLs.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.auth.permissions import get_current_user_optional, require_any_permission
from app.database import get_db
from app.integrations.viator import service as viator
from app.integrations.viator.exceptions import (
    ViatorBadRequest,
    ViatorError,
    ViatorNotConfigured,
    ViatorNotFound,
)
from app.integrations.viator.schemas import (
    DestinationMappingUpdate,
    ExternalClickRequest,
    ExternalRedirectRequest,
    ExternalTourSearchRequest,
    ProviderSettingsUpdate,
)
from app.models.agents import Agent
from app.models.users import User
from app.utils.ratelimit import check_rate_limit

logger = logging.getLogger(__name__)

public_router = APIRouter(prefix="/external-tours", tags=["External Tours"])
admin_router = APIRouter(prefix="/integrations/external-tours", tags=["External Tours (Admin)"])

VIEW = ("settings.view", "view-settings")
UPDATE = ("settings.update", "update-settings")


def _http_error(exc: ViatorError) -> HTTPException:
    """Customer-safe error: a fixed message and code, never Viator's raw
    response or anything credential-related."""
    if isinstance(exc, ViatorNotConfigured):
        status = 503
    elif isinstance(exc, ViatorNotFound):
        status = 404
    elif isinstance(exc, ViatorBadRequest):
        status = 400
    else:
        status = 503
    return HTTPException(status_code=status, detail={"status": "error", "code": exc.code, "message": exc.public_message})


def _agent_id(db: Session, user: User | None) -> int | None:
    if not user:
        return None
    role_slug = (user.role.slug if user.role else "") or ""
    if user.user_type != "AGENT" and "agent" not in role_slug.lower():
        return None
    agent = db.query(Agent.id).filter(Agent.user_id == user.id).first()
    return agent[0] if agent else None


# --- public -----------------------------------------------------------------

@public_router.get("/config")
def external_tours_config(db: Session = Depends(get_db)):
    return {"status": "success", "data": viator.public_config(db)}


@public_router.get("/destinations")
def external_destinations(
    search: str = Query(default="", max_length=100),
    limit: int = Query(default=20, ge=1, le=50),
    db: Session = Depends(get_db),
):
    return {"status": "success", "items": viator.list_public_destinations(db, search, limit)}


@public_router.get("/destinations/{slug}")
def external_destination(slug: str, db: Session = Depends(get_db)):
    try:
        return {"status": "success", "data": viator.public_destination(db, slug[:191])}
    except ViatorError as exc:
        raise _http_error(exc) from exc


@public_router.get("/categories")
def external_categories():
    return {"status": "success", "items": viator.categories()}


@public_router.post("/search")
def external_search(
    data: ExternalTourSearchRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    check_rate_limit(request, "external-tours-search", max_calls=60, window_seconds=60)
    try:
        result = viator.search(db, data, is_agent=_agent_id(db, user) is not None)
    except ViatorError as exc:
        raise _http_error(exc) from exc
    return {"status": "success", **result}


@public_router.post("/click")
def external_click(
    data: ExternalClickRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    """Outbound affiliate click analytics. The browser opens the Viator link
    itself, so a failure here never blocks the customer."""
    check_rate_limit(request, "external-tours-click", max_calls=120, window_seconds=60)
    try:
        click = viator.record_click(db, data, user_id=user.id if user else None, agent_id=_agent_id(db, user))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "success", "data": {"id": click.id}}


@public_router.post("/redirect")
def external_redirect(
    data: ExternalRedirectRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    """Homepage "Viator Day Tours & Experiences": returns Viator's affiliate
    URL for the destination (and records the outbound click). The browser
    then navigates there - no Tourvaa page in between."""
    check_rate_limit(request, "external-tours-redirect", max_calls=60, window_seconds=60)
    try:
        result = viator.destination_redirect(
            db,
            destination=data.destination,
            country=data.country,
            source=data.source,
            user_id=user.id if user else None,
            agent_id=_agent_id(db, user),
            session_id=data.session_id,
            page_path=data.page_path,
        )
    except ViatorError as exc:
        raise _http_error(exc) from exc
    return {"status": "success", "data": result}


# --- admin ------------------------------------------------------------------

@admin_router.get("/viator/status")
def viator_status(db: Session = Depends(get_db), _=Depends(require_any_permission(*VIEW))):
    return {"status": "success", "data": viator.admin_status(db)}


@admin_router.post("/viator/test-connection")
def viator_test_connection(db: Session = Depends(get_db), _=Depends(require_any_permission(*UPDATE))):
    return {"status": "success", "data": viator.test_connection(db)}


@admin_router.post("/viator/sync-destinations")
def viator_sync_destinations(db: Session = Depends(get_db), _=Depends(require_any_permission(*UPDATE))):
    try:
        result = viator.sync_destinations(db)
    except ViatorNotConfigured as exc:
        raise HTTPException(status_code=400, detail="Enable Viator and set an API key before syncing.") from exc
    except ViatorError as exc:
        raise HTTPException(status_code=502, detail=f"Viator destination sync failed ({exc.code}).") from exc
    viator.clear_search_cache()
    return {"status": "success", "data": result}


@admin_router.put("/viator/settings")
def viator_update_settings(data: ProviderSettingsUpdate, db: Session = Depends(get_db), _=Depends(require_any_permission(*UPDATE))):
    return {"status": "success", "data": viator.update_provider_settings(db, data.model_dump(exclude_unset=True))}


@admin_router.get("/viator/mappings")
def viator_mappings(
    search: str = Query(default="", max_length=100),
    status: str = Query(default="", pattern="^(|linked|unlinked|manual|inactive)$"),
    type: str = Query(default="", max_length=30),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=25, ge=1, le=100),
    db: Session = Depends(get_db),
    _=Depends(require_any_permission(*VIEW)),
):
    return {"status": "success", **viator.list_mappings(db, search=search, status=status, dest_type=type, page=page, limit=limit)}


@admin_router.put("/viator/mappings/{mapping_id}")
def viator_update_mapping(mapping_id: int, data: DestinationMappingUpdate, db: Session = Depends(get_db), _=Depends(require_any_permission(*UPDATE))):
    try:
        row = viator.update_mapping(db, mapping_id, data.model_dump(exclude_unset=True))
    except ViatorNotFound as exc:
        raise HTTPException(status_code=404, detail="Mapping not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    viator.clear_search_cache()
    return {"status": "success", "data": row}


@admin_router.get("/viator/clicks/summary")
def viator_click_summary(days: int = Query(default=30, ge=1, le=365), db: Session = Depends(get_db), _=Depends(require_any_permission(*VIEW))):
    return {"status": "success", "data": viator.click_summary(db, days)}
