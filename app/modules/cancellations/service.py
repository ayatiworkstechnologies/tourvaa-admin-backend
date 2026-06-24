from datetime import timezone
from decimal import Decimal
from math import ceil
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.modules.audit.service import log_audit
from app.modules.bookings.models import Booking
from app.modules.cancellations.models import CancellationRequest, RefundRule
from app.modules.cancellations.schemas import (
    CancellationApprove, CancellationReject, CancellationRequestCreate,
    ProcessRefundBody, RefundRuleCreate,
)
from app.modules.common.money import money, utcnow
from app.modules.customers.models import Customer
from app.modules.notifications.service import enqueue_notification, notify_admins
from app.modules.users.models import User


def _serialize_request(r: CancellationRequest) -> dict:
    return {
        "id": r.id,
        "booking_id": r.booking_id,
        "booking_code": r.booking.booking_code if r.booking else None,
        "customer_id": r.customer_id,
        "reason": r.reason,
        "status": r.status,
        "refund_percentage": str(r.refund_percentage),
        "refund_amount": str(r.refund_amount),
        "currency": r.currency,
        "admin_notes": r.admin_notes,
        "reviewed_by": r.reviewed_by,
        "reviewer_name": r.reviewer.name if r.reviewer else None,
        "reviewed_at": r.reviewed_at,
        "gateway_refund_id": r.gateway_refund_id,
        "refund_processed_at": r.refund_processed_at,
        "created_at": r.created_at,
        "updated_at": r.updated_at,
    }


def _serialize_rule(r: RefundRule) -> dict:
    return {
        "id": r.id,
        "tour_id": r.tour_id,
        "days_before_tour_min": r.days_before_tour_min,
        "days_before_tour_max": r.days_before_tour_max,
        "refund_percentage": str(r.refund_percentage),
        "description": r.description,
        "created_at": r.created_at,
    }


def _calculate_refund_percentage(db: Session, booking: Booking) -> Decimal:
    """Apply the most specific refund rules for a booking based on days-until-tour."""
    if not booking.tour_start_date:
        return Decimal("0")
    now = utcnow()
    tour_start = booking.tour_start_date
    if hasattr(tour_start, "tzinfo") and tour_start.tzinfo is None:
        from datetime import timezone as tz
        tour_start = tour_start.replace(tzinfo=tz.utc)
    days_until = max(0, (tour_start - now).days)

    # Tour-specific rules first, then global
    for tour_id in [booking.tour_id, None]:
        rules = (db.query(RefundRule)
                 .filter(RefundRule.tour_id == tour_id)
                 .filter(RefundRule.days_before_tour_min <= days_until)
                 .order_by(RefundRule.days_before_tour_min.desc())
                 .all())
        for rule in rules:
            max_ok = rule.days_before_tour_max is None or days_until <= rule.days_before_tour_max
            if max_ok:
                return money(rule.refund_percentage)

    return Decimal("0")


def create_request(db: Session, data: CancellationRequestCreate, actor: User, request=None) -> dict:
    booking = db.query(Booking).filter(Booking.id == data.booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    if booking.booking_status == "cancelled":
        raise HTTPException(status_code=400, detail="Booking is already cancelled")

    # Check for existing pending request
    existing = db.query(CancellationRequest).filter(CancellationRequest.booking_id == data.booking_id, CancellationRequest.status == "pending").first()
    if existing:
        raise HTTPException(status_code=400, detail="A cancellation request is already pending for this booking")

    refund_pct = _calculate_refund_percentage(db, booking)
    refund_amount = money((money(booking.amount_paid) * refund_pct) / 100)

    req = CancellationRequest(
        booking_id=data.booking_id,
        customer_id=booking.customer_id,
        reason=data.reason,
        status="pending",
        refund_percentage=refund_pct,
        refund_amount=refund_amount,
        currency=booking.currency or "USD",
    )
    db.add(req)
    db.commit()
    db.refresh(req)

    # Notify admin and customer
    notify_admins(db, notification_type="cancellation_requested", title="Cancellation Requested", message=f"Customer requested cancellation for booking {booking.booking_code}. Estimated refund: {refund_amount} {req.currency}", entity_type="cancellation_request", entity_id=req.id)
    if booking.customer and booking.customer.user_id:
        enqueue_notification(db, user_id=booking.customer.user_id, notification_type="cancellation_requested", title="Cancellation Request Received", message=f"Your cancellation request for booking {booking.booking_code} has been received. Estimated refund: {refund_amount} {req.currency}.", entity_type="cancellation_request", entity_id=req.id)
    db.commit()

    log_audit(db, actor=actor, action="create_cancellation_request", entity_type="cancellation_request", entity_id=req.id, new_values={"booking_id": data.booking_id, "refund_percentage": str(refund_pct)}, request=request)
    return _serialize_request(req)


def list_requests(db: Session, page: int = 1, limit: int = 20, status: str = "", customer_id: Optional[int] = None) -> dict:
    q = db.query(CancellationRequest)
    if status:
        q = q.filter(CancellationRequest.status == status)
    if customer_id:
        q = q.filter(CancellationRequest.customer_id == customer_id)
    q = q.order_by(CancellationRequest.id.desc())
    total = q.count()
    items = [_serialize_request(r) for r in q.offset((page - 1) * limit).limit(limit).all()]
    return {"items": items, "data": items, "total": total, "page": page, "limit": limit, "total_pages": max(1, ceil(total / limit))}


def approve_request(db: Session, request_id: int, data: CancellationApprove, actor: User, request=None) -> dict:
    req = db.query(CancellationRequest).filter(CancellationRequest.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Cancellation request not found")
    if req.status != "pending":
        raise HTTPException(status_code=400, detail=f"Request is already '{req.status}'")

    if data.refund_percentage is not None:
        req.refund_percentage = money(data.refund_percentage)
    if data.refund_amount is not None:
        req.refund_amount = money(data.refund_amount)
    elif data.refund_percentage is not None:
        booking = req.booking
        req.refund_amount = money((money(booking.amount_paid) * money(data.refund_percentage)) / 100)

    req.status = "approved"
    req.admin_notes = data.admin_notes
    req.reviewed_by = actor.id
    req.reviewed_at = utcnow()

    # Cancel the booking
    booking = req.booking
    booking.booking_status = "cancelled"
    booking.cancellation_reason = req.reason
    booking.cancelled_at = utcnow()

    db.commit()
    db.refresh(req)

    if booking.customer and booking.customer.user_id:
        enqueue_notification(db, user_id=booking.customer.user_id, notification_type="cancellation_approved", title="Cancellation Approved", message=f"Your cancellation request for booking {booking.booking_code} has been approved. Refund: {req.refund_amount} {req.currency}", entity_type="cancellation_request", entity_id=req.id)
        db.commit()

    log_audit(db, actor=actor, action="approve_cancellation", entity_type="cancellation_request", entity_id=request_id, old_values={"status": "pending"}, new_values={"status": "approved", "refund_amount": str(req.refund_amount)}, request=request)
    return _serialize_request(req)


def reject_request(db: Session, request_id: int, data: CancellationReject, actor: User, request=None) -> dict:
    req = db.query(CancellationRequest).filter(CancellationRequest.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Cancellation request not found")
    if req.status != "pending":
        raise HTTPException(status_code=400, detail=f"Request is already '{req.status}'")

    req.status = "rejected"
    req.admin_notes = data.admin_notes
    req.reviewed_by = actor.id
    req.reviewed_at = utcnow()
    db.commit()
    db.refresh(req)

    booking = req.booking
    if booking.customer and booking.customer.user_id:
        enqueue_notification(db, user_id=booking.customer.user_id, notification_type="cancellation_rejected", title="Cancellation Rejected", message=f"Your cancellation request for booking {booking.booking_code} was rejected. Reason: {data.admin_notes}", entity_type="cancellation_request", entity_id=req.id)
        db.commit()

    log_audit(db, actor=actor, action="reject_cancellation", entity_type="cancellation_request", entity_id=request_id, old_values={"status": "pending"}, new_values={"status": "rejected"}, request=request)
    return _serialize_request(req)


def process_refund(db: Session, request_id: int, data: ProcessRefundBody, actor: User, request=None) -> dict:
    req = db.query(CancellationRequest).filter(CancellationRequest.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Cancellation request not found")
    if req.status != "approved":
        raise HTTPException(status_code=400, detail="Request must be approved before processing refund")

    booking = req.booking

    if data.gateway != "manual" and data.gateway_refund_id:
        pass  # In a real integration, call gateway here

    req.status = "refund_processed"
    req.gateway_refund_id = data.gateway_refund_id
    req.refund_processed_at = utcnow()

    # Update booking payment status
    booking.payment_status = "refunded"

    db.commit()
    db.refresh(req)

    if booking.customer and booking.customer.user_id:
        enqueue_notification(db, user_id=booking.customer.user_id, notification_type="refund_processed", title="Refund Processed", message=f"Refund of {req.refund_amount} {req.currency} has been processed for booking {booking.booking_code}.", entity_type="cancellation_request", entity_id=req.id)
        db.commit()

    notify_admins(db, notification_type="refund_processed", title="Refund Processed", message=f"Refund of {req.refund_amount} {req.currency} processed for booking {booking.booking_code}.", entity_type="cancellation_request", entity_id=req.id)
    db.commit()

    log_audit(db, actor=actor, action="process_refund", entity_type="cancellation_request", entity_id=request_id, old_values={"status": "approved"}, new_values={"status": "refund_processed"}, request=request)
    return _serialize_request(req)


# ---------------------------------------------------------------------------
# Refund Rules
# ---------------------------------------------------------------------------

def list_rules(db: Session, tour_id: Optional[int] = None) -> list:
    q = db.query(RefundRule)
    if tour_id:
        q = q.filter(RefundRule.tour_id == tour_id)
    return [_serialize_rule(r) for r in q.order_by(RefundRule.days_before_tour_min.desc()).all()]


def create_rule(db: Session, data: RefundRuleCreate, actor: User, request=None) -> dict:
    rule = RefundRule(**data.model_dump())
    db.add(rule)
    db.commit()
    db.refresh(rule)
    log_audit(db, actor=actor, action="create_refund_rule", entity_type="refund_rule", entity_id=rule.id, new_values=data.model_dump(), request=request)
    return _serialize_rule(rule)


def delete_rule(db: Session, rule_id: int, actor: User, request=None):
    rule = db.query(RefundRule).filter(RefundRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Refund rule not found")
    db.delete(rule)
    db.commit()
    log_audit(db, actor=actor, action="delete_refund_rule", entity_type="refund_rule", entity_id=rule_id, request=request)
