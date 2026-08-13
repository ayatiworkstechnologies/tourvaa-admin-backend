"""Admin management of affiliate links across all affiliates - CRUD plus
activate/disable/duplicate. Self-service link creation for an affiliate's own
links stays on POST /affiliates/{affiliate_id}/links in affiliate_tracking.py.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth.permissions import require_any_permission
from app.database import get_db
from app.schemas.affiliate_tracking import AffiliateLinkAdminCreate, AffiliateLinkUpdate
from app.services import affiliate_tracking as service
from app.utils.pagination import pagination_params

router = APIRouter(prefix="/affiliate-links", tags=["Affiliate Links (Admin)"])


@router.get("")
@router.get("/")
def list_links(
    pagination=Depends(pagination_params),
    affiliate_id: int = Query(default=0),
    tour_id: int = Query(default=0),
    status: str = Query(default=""),
    db: Session = Depends(get_db),
    _=Depends(require_any_permission("affiliate_links.view")),
):
    return {
        "status": "success",
        **service.list_links_admin(
            db, affiliate_id=affiliate_id or None, tour_id=tour_id or None, status=status,
            search=pagination["search"], page=pagination["page"], limit=pagination["limit"],
        ),
    }


@router.post("")
@router.post("/")
def create_link(data: AffiliateLinkAdminCreate, db: Session = Depends(get_db), current_user=Depends(require_any_permission("affiliate_links.create"))):
    result = service.create_link(db, affiliate_id=data.affiliate_id, data=data, actor=current_user)
    return {"status": "success", "message": "Affiliate link created", "data": result}


@router.get("/{link_id}")
def link_detail(link_id: int, db: Session = Depends(get_db), _=Depends(require_any_permission("affiliate_links.view"))):
    return {"status": "success", "data": service._s_link(service.get_link(db, link_id))}


@router.put("/{link_id}")
def update_link(link_id: int, data: AffiliateLinkUpdate, db: Session = Depends(get_db), current_user=Depends(require_any_permission("affiliate_links.update"))):
    result = service.update_link(db, link_id, data, current_user, is_admin=True)
    return {"status": "success", "message": "Affiliate link updated", "data": result}


@router.delete("/{link_id}")
def delete_link(link_id: int, db: Session = Depends(get_db), current_user=Depends(require_any_permission("affiliate_links.delete"))):
    return {"status": "success", "data": service.delete_link(db, link_id, current_user)}


@router.post("/{link_id}/activate")
def activate_link(link_id: int, db: Session = Depends(get_db), current_user=Depends(require_any_permission("affiliate_links.activate"))):
    result = service.activate_link(db, link_id, current_user)
    return {"status": "success", "message": "Affiliate link activated", "data": result}


@router.post("/{link_id}/disable")
def disable_link(link_id: int, db: Session = Depends(get_db), current_user=Depends(require_any_permission("affiliate_links.disable"))):
    result = service.disable_link(db, link_id, current_user)
    return {"status": "success", "message": "Affiliate link disabled", "data": result}


@router.post("/{link_id}/duplicate")
def duplicate_link(link_id: int, campaign_name: str = Query(default=None), db: Session = Depends(get_db), current_user=Depends(require_any_permission("affiliate_links.duplicate"))):
    result = service.duplicate_link(db, link_id, current_user, campaign_name=campaign_name)
    return {"status": "success", "message": "Affiliate link duplicated", "data": result}
