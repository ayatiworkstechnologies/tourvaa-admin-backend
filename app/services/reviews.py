from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.services.audit import log_audit
from app.services.notifications import notify_admins
from app.models.bookings import Booking
from app.models.reviews import TourReview
from app.models.users import User
from app.schemas.reviews import ReviewCreate, ReviewModerate
from app.utils.operations import simple_paginate


def _serialize(review: TourReview) -> dict:
    customer_name = review.customer.full_name if review.customer else ""
    return {
        "id": review.id,
        "booking_id": review.booking_id,
        "customer_id": review.customer_id,
        "customer_name": customer_name,
        "tour_id": review.tour_id,
        "tour_title": review.tour.title if review.tour else "",
        "rating": review.rating,
        "review_text": review.review_text,
        "status": review.status,
        "created_at": review.created_at,
        "updated_at": review.updated_at,
    }


def create_review(db: Session, data: ReviewCreate, actor: User, request=None) -> dict:
    booking = db.query(Booking).filter(Booking.id == data.booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    if not booking.customer or booking.customer.user_id != actor.id:
        raise HTTPException(status_code=403, detail="Booking access denied")
    if booking.booking_status != "completed":
        raise HTTPException(status_code=400, detail="You can only review completed bookings")
    if not booking.tour_id:
        raise HTTPException(status_code=400, detail="This booking has no associated tour to review")

    existing = db.query(TourReview).filter(TourReview.booking_id == data.booking_id).first()
    if existing:
        raise HTTPException(status_code=400, detail="You have already reviewed this booking")

    review = TourReview(
        booking_id=data.booking_id,
        customer_id=booking.customer_id,
        tour_id=booking.tour_id,
        rating=data.rating,
        review_text=data.review_text,
        status="pending",
    )
    db.add(review)
    db.flush()
    log_audit(db, actor=actor, action="create_review", entity_type="tour_review", entity_id=review.id, request=request)
    notify_admins(db, notification_type="review_submitted", title="New review awaiting approval", message=f"A review for booking {booking.booking_code} is awaiting moderation", entity_type="tour_review", entity_id=review.id)
    db.commit()
    db.refresh(review)
    return _serialize(review)


def list_tour_reviews(db: Session, tour_id: int, limit: int = 20) -> list[dict]:
    reviews = (
        db.query(TourReview)
        .filter(TourReview.tour_id == tour_id, TourReview.status == "approved")
        .order_by(TourReview.created_at.desc())
        .limit(limit)
        .all()
    )
    return [_serialize(r) for r in reviews]


def get_review_stats(db: Session, tour_ids: list[int]) -> dict[int, dict]:
    if not tour_ids:
        return {}
    rows = (
        db.query(TourReview.tour_id, func.avg(TourReview.rating), func.count(TourReview.id))
        .filter(TourReview.tour_id.in_(tour_ids), TourReview.status == "approved")
        .group_by(TourReview.tour_id)
        .all()
    )
    return {tour_id: {"average": round(float(avg), 1), "count": count} for tour_id, avg, count in rows}


def list_reviews(db: Session, page: int, limit: int, status: str = ""):
    query = db.query(TourReview)
    if status:
        query = query.filter(TourReview.status == status)
    return simple_paginate(query.order_by(TourReview.created_at.desc()), page, limit, _serialize)


def moderate_review(db: Session, review_id: int, data: ReviewModerate, actor: User, request=None) -> dict:
    review = db.query(TourReview).filter(TourReview.id == review_id).first()
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    old_status = review.status
    review.status = data.status
    log_audit(db, actor=actor, action="moderate_review", entity_type="tour_review", entity_id=review.id, old_values={"status": old_status}, new_values={"status": review.status}, request=request)
    db.commit()
    db.refresh(review)
    return _serialize(review)
