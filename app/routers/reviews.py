from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.services import reviews as service
from app.schemas.reviews import ReviewCreate, ReviewModerate
from app.auth.permissions import get_current_user, require_any_permission
from app.utils.pagination import pagination_params

router = APIRouter(tags=["Reviews"])


@router.post("/customer/reviews")
def submit_review(data: ReviewCreate, request: Request, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    result = service.create_review(db, data=data, actor=current_user, request=request)
    return {"status": "success", "message": "Thanks for your review - it'll appear once approved.", "data": result}


@router.get("/admin/reviews")
def list_reviews(pagination=Depends(pagination_params), status: str = Query(default=""), db: Session = Depends(get_db), _=Depends(require_any_permission("tours.view", "view-tours"))):
    return {"status": "success", **service.list_reviews(db, page=pagination["page"], limit=pagination["limit"], status=status)}


@router.patch("/admin/reviews/{review_id}/approve")
def approve_review(review_id: int, request: Request, db: Session = Depends(get_db), current_user=Depends(require_any_permission("tours.edit", "update-tours"))):
    result = service.moderate_review(db, review_id=review_id, data=ReviewModerate(status="approved"), actor=current_user, request=request)
    return {"status": "success", "message": "Review approved", "data": result}


@router.patch("/admin/reviews/{review_id}/reject")
def reject_review(review_id: int, request: Request, db: Session = Depends(get_db), current_user=Depends(require_any_permission("tours.edit", "update-tours"))):
    result = service.moderate_review(db, review_id=review_id, data=ReviewModerate(status="rejected"), actor=current_user, request=request)
    return {"status": "success", "message": "Review rejected", "data": result}
