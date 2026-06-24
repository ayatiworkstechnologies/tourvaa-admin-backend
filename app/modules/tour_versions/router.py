from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.modules.common.auth import require_any_permission
from app.modules.common.pagination import pagination_params
from app.modules.tour_versions import service
from app.modules.tour_versions.schemas import TourVersionReject

router = APIRouter(tags=["Tour Versions"])


@router.post("/tours/{tour_id}/submit-for-approval")
def submit_for_approval(tour_id: int, request: Request, db: Session = Depends(get_db), current_user=Depends(require_any_permission("tours.edit", "update-tours"))):
    result = service.submit_for_approval(db, tour_id=tour_id, actor=current_user, request=request)
    return {"status": "success", "message": "Tour submitted for approval", "data": result}


@router.get("/tours/pending-approval")
def list_pending(db: Session = Depends(get_db), pagination=Depends(pagination_params), current_user=Depends(require_any_permission("tours.view", "view-tours"))):
    return {"status": "success", **service.list_pending(db, page=pagination["page"], limit=pagination["limit"])}


@router.get("/tours/{tour_id}/versions")
def list_versions(tour_id: int, db: Session = Depends(get_db), pagination=Depends(pagination_params), current_user=Depends(require_any_permission("tours.view", "view-tours"))):
    return {"status": "success", **service.list_versions(db, tour_id=tour_id, page=pagination["page"], limit=pagination["limit"])}


@router.patch("/tours/{tour_id}/versions/{version_id}/approve")
def approve_version(tour_id: int, version_id: int, request: Request, db: Session = Depends(get_db), current_user=Depends(require_any_permission("tours.publish", "update-tours"))):
    result = service.approve_version(db, tour_id=tour_id, version_id=version_id, actor=current_user, request=request)
    return {"status": "success", "message": "Tour version approved", "data": result}


@router.patch("/tours/{tour_id}/versions/{version_id}/reject")
def reject_version(tour_id: int, version_id: int, body: TourVersionReject, request: Request, db: Session = Depends(get_db), current_user=Depends(require_any_permission("tours.publish", "update-tours"))):
    result = service.reject_version(db, tour_id=tour_id, version_id=version_id, data=body, actor=current_user, request=request)
    return {"status": "success", "message": "Tour version rejected", "data": result}
