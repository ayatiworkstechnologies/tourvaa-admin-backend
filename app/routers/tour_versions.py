from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth.permissions import require_any_permission
from app.utils.pagination import pagination_params
from app.services import tour_versions as service
from app.schemas.tour_versions import ReviewCommentCreate, TourVersionReject
from app.services.supplier_scope import ensure_supplier_tour_access, reject_supplier_review_action

router = APIRouter(tags=["Tour Versions"])


@router.post("/tours/{tour_id}/submit-for-approval")
def submit_for_approval(tour_id: int, request: Request, db: Session = Depends(get_db), current_user=Depends(require_any_permission("tours.edit", "update-tours"))):
    ensure_supplier_tour_access(db, tour_id, current_user)
    result = service.submit_for_approval(db, tour_id=tour_id, actor=current_user, request=request)
    return {"status": "success", "message": "Tour submitted for approval", "data": result}


@router.post("/tours/{tour_id}/withdraw")
def withdraw_submission(tour_id: int, request: Request, db: Session = Depends(get_db), current_user=Depends(require_any_permission("tours.edit", "update-tours"))):
    ensure_supplier_tour_access(db, tour_id, current_user)
    result = service.withdraw_submission(db, tour_id=tour_id, actor=current_user, request=request)
    return {"status": "success", "message": "Submission withdrawn", "data": result}


@router.get("/tours/{tour_id}/review-comments")
def list_review_comments(tour_id: int, status: str = "", db: Session = Depends(get_db), current_user=Depends(require_any_permission("tours.view", "view-tours"))):
    ensure_supplier_tour_access(db, tour_id, current_user)
    return {"status": "success", "data": service.list_review_comments(db, tour_id=tour_id, status=status or None)}


@router.post("/tours/{tour_id}/review-comments")
def create_review_comment(tour_id: int, body: ReviewCommentCreate, request: Request, db: Session = Depends(get_db), current_user=Depends(require_any_permission("tours.publish", "update-tours"))):
    reject_supplier_review_action(current_user)
    result = service.create_review_comment(db, tour_id=tour_id, data=body, actor=current_user, request=request)
    return {"status": "success", "data": result}


@router.patch("/tours/{tour_id}/review-comments/{comment_id}/resolve")
def resolve_review_comment(tour_id: int, comment_id: int, request: Request, db: Session = Depends(get_db), current_user=Depends(require_any_permission("tours.edit", "update-tours"))):
    ensure_supplier_tour_access(db, tour_id, current_user)
    result = service.resolve_review_comment(db, comment_id=comment_id, actor=current_user, request=request)
    return {"status": "success", "data": result}


@router.get("/tours/pending-approval")
def list_pending(db: Session = Depends(get_db), pagination=Depends(pagination_params), current_user=Depends(require_any_permission("tours.view", "view-tours"))):
    reject_supplier_review_action(current_user)
    return {"status": "success", **service.list_pending(db, page=pagination["page"], limit=pagination["limit"])}


@router.get("/tours/{tour_id}/versions")
def list_versions(tour_id: int, db: Session = Depends(get_db), pagination=Depends(pagination_params), current_user=Depends(require_any_permission("tours.view", "view-tours"))):
    ensure_supplier_tour_access(db, tour_id, current_user)
    return {"status": "success", **service.list_versions(db, tour_id=tour_id, page=pagination["page"], limit=pagination["limit"])}


@router.patch("/tours/{tour_id}/versions/{version_id}/approve")
def approve_version(tour_id: int, version_id: int, request: Request, db: Session = Depends(get_db), current_user=Depends(require_any_permission("tours.publish", "update-tours"))):
    reject_supplier_review_action(current_user)
    result = service.approve_version(db, tour_id=tour_id, version_id=version_id, actor=current_user, request=request)
    return {"status": "success", "message": "Tour version approved", "data": result}


@router.patch("/tours/{tour_id}/versions/{version_id}/reject")
def reject_version(
    tour_id: int,
    version_id: int,
    body: TourVersionReject,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(require_any_permission("tours.publish", "update-tours")),
):
    reject_supplier_review_action(current_user)
    result = service.reject_version(db, tour_id=tour_id, version_id=version_id, data=body, actor=current_user, request=request)
    return {"status": "success", "message": "Tour version rejected", "data": result}
