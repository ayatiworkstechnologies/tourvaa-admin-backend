from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.services import reviews as service
from app.schemas.reviews import ReviewCreate, ReviewModerate, ReviewUpdate
from app.auth.permissions import get_current_user, require_any_permission
from app.utils.pagination import pagination_params

router = APIRouter(tags=["Reviews"])


@router.post("/customer/reviews")
def submit_review(data: ReviewCreate, request: Request, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    result = service.create_review(db, data=data, actor=current_user, request=request)
    return {"status": "success", "message": "Thanks for your review - it'll appear once approved.", "data": result}


@router.get("/customer/reviews/eligibility/{booking_id}")
def get_review_eligibility(booking_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    return {"status": "success", "data": service.review_eligibility(db, booking_id, current_user)}


@router.patch("/customer/reviews/{review_id}")
def update_review(review_id: int, data: ReviewUpdate, request: Request, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    return {"status": "success", "message": "Review resubmitted for moderation.", "data": service.update_customer_review(db, review_id, data, current_user, request)}


@router.get("/public/tours/{tour_id}/reviews")
def public_tour_reviews(tour_id: int, pagination=Depends(pagination_params), db: Session = Depends(get_db)):
    return {"status": "success", **service.list_public_tour_reviews(db, tour_id, page=pagination["page"], limit=pagination["limit"])}


@router.get("/public/tours/{tour_id}/review-summary")
def public_tour_review_summary(tour_id: int, db: Session = Depends(get_db)):
    return {"status": "success", "data": service.get_tour_review_summary(db, tour_id)}


@router.get("/portal/reviews")
def portal_reviews(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    return {"status": "success", "data": service.list_portal_reviews(db, current_user)}


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
