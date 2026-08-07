import logging
from datetime import timezone
from decimal import Decimal
from math import ceil
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.services.audit import log_audit
from app.models.bookings import Booking
from app.models.cancellations import CancellationRequest, RefundRule
from app.schemas.cancellations import (
    CancellationApprove, CancellationReject, CancellationRequestCreate,
    ProcessRefundBody, RefundRuleCreate, RefundRuleUpdate,
)
from app.utils.money import money, utcnow
from app.models.customers import Customer
from app.services.notifications import enqueue_notification, notify_admins
from app.models.users import User

logger = logging.getLogger(__name__)


def _serialize_request(r: CancellationRequest) -> dict:
    return {
        "id": r.id,
        "booking_id": r.booking_id,
        "booking_code": r.booking.booking_code if r.booking else None,
        "tour_name": r.booking.tour_name if r.booking else None,
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


def _user_role(user: User | None) -> str:
    if not user or not user.role:
        return "admin"
    slug = user.role.slug or ""
    if "supplier" in slug:
        return "supplier"
    if "agent" in slug:
        return "agent"
    if "customer" in slug:
        return "customer"
    return "admin"


def _ensure_booking_owner(booking: Booking, actor: User | None) -> None:
    role = _user_role(actor)
    if role == "admin" or actor is None:
        return
    if role == "customer" and booking.customer and booking.customer.user_id == actor.id:
        return
    if role == "supplier" and booking.supplier and booking.supplier.user_id == actor.id:
        return
    if role == "agent" and booking.agent and booking.agent.user_id == actor.id:
        return
    raise HTTPException(status_code=403, detail="Booking access denied")


def _prior_status_before_cancellation_request(db: Session, booking_id: int) -> str:
    """Look up what booking_status was before this booking most recently moved
    to cancellation_requested, so a rejected request can restore it. The
    BOOKING_STATUS_TRANSITIONS graph is not symmetric (not every status that
    can move *into* cancellation_requested is a valid target coming back out
    of it), so this restores directly rather than re-validating the reverse
    transition.
    """
    from app.models.bookings import BookingStatusHistory
    row = (
        db.query(BookingStatusHistory)
        .filter(BookingStatusHistory.booking_id == booking_id, BookingStatusHistory.new_status == "cancellation_requested")
        .order_by(BookingStatusHistory.id.desc())
        .first()
    )
    return row.old_status if row and row.old_status else "confirmed"


def create_request(db: Session, data: CancellationRequestCreate, actor: User, request=None) -> dict:
    booking = db.query(Booking).filter(Booking.id == data.booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    _ensure_booking_owner(booking, actor)
    if booking.booking_status in {"cancelled", "completed", "refunded", "cancellation_requested"}:
        raise HTTPException(status_code=400, detail=f"This booking cannot be cancelled (current status: '{booking.booking_status}')")

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

    from app.models.bookings import BookingStatusHistory
    from app.services.bookings import _validate_booking_status_transition
    old_status = booking.booking_status
    _validate_booking_status_transition(old_status, "cancellation_requested")
    booking.booking_status = "cancellation_requested"
    db.add(BookingStatusHistory(
        booking_id=booking.id,
        old_status=old_status,
        new_status="cancellation_requested",
        changed_by_user_id=actor.id,
        change_source=_user_role(actor),
        reason=data.reason,
    ))

    db.commit()
    db.refresh(req)

    # Notify admin and customer
    notify_admins(db, notification_type="cancellation_requested", title="Cancellation Requested", message=f"Customer requested cancellation for booking {booking.booking_code}. Estimated refund: {refund_amount} {req.currency}", entity_type="cancellation_request", entity_id=req.id)
    if booking.customer and booking.customer.user_id:
        enqueue_notification(db, user_id=booking.customer.user_id, notification_type="cancellation_requested", title="Cancellation Request Received", message=f"Your cancellation request for booking {booking.booking_code} has been received. Estimated refund: {refund_amount} {req.currency}.", entity_type="cancellation_request", entity_id=req.id)
    db.commit()

    if booking.customer and booking.customer.email:
        from app.utils.email_templates import cancellation_requested_email
        from app.utils.notification_triggers import send_templated_email
        login_url = f"{settings.FRONTEND_URL}/customer/bookings/{booking.id}"
        send_templated_email(
            db, booking.customer.email, "cancellation_requested",
            {"name": booking.customer.full_name, "booking_code": booking.booking_code, "tour_name": booking.tour_name,
             "refund_amount": refund_amount, "currency": req.currency, "login_url": login_url,
             "button_text": "View booking", "button_url": login_url},
            f"Cancellation request received - {booking.booking_code}",
            cancellation_requested_email(booking.customer.full_name, booking.booking_code, booking.tour_name, refund_amount, req.currency, login_url),
        )

    from app.utils.email_templates import admin_booking_event_email
    from app.utils.notification_triggers import email_admins
    admin_url = f"{settings.FRONTEND_URL}/admin/bookings/{booking.id}"
    admin_detail = f"Customer requested cancellation for booking {booking.booking_code}. Estimated refund: {refund_amount} {req.currency}."
    email_admins(
        db, "admin_booking_event",
        {"event_title": "Cancellation requested", "detail": admin_detail, "booking_code": booking.booking_code,
         "tour_name": booking.tour_name, "admin_url": admin_url, "button_text": "View booking", "button_url": admin_url},
        f"Cancellation requested - {booking.booking_code}",
        admin_booking_event_email("Cancellation requested", admin_detail, booking.booking_code, booking.tour_name, admin_url),
    )

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
    return {"items": items, "total": total, "page": page, "limit": limit, "total_pages": max(1, ceil(total / limit))}


def approve_request(db: Session, request_id: int, data: CancellationApprove, actor: User, request=None) -> dict:
    req = db.query(CancellationRequest).filter(CancellationRequest.id == request_id).with_for_update().first()
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
    old_status = booking.booking_status
    booking.booking_status = "cancelled"
    booking.cancellation_reason = req.reason
    booking.cancelled_at = utcnow()
    booking.cancelled_by = actor.id
    if booking.calendar:
        booking.calendar.booked_seats = max(0, (booking.calendar.booked_seats or 0) - (booking.total_travellers or 0))

    from app.models.bookings import BookingStatusHistory
    db.add(BookingStatusHistory(
        booking_id=booking.id,
        old_status=old_status,
        new_status="cancelled",
        changed_by_user_id=actor.id,
        change_source="cancellation_request",
        reason=req.reason,
    ))

    try:
        from app.services.affiliate_tracking import reverse_conversion
        reverse_conversion(db, booking.id)
    except Exception:
        logger.exception("Failed to reverse affiliate conversion for booking_id=%s", booking.id)
    try:
        from app.services.supplier_ledger import reverse_ledger_entry
        reverse_ledger_entry(db, booking.id)
    except Exception:
        logger.exception("Failed to reverse supplier ledger entry for booking_id=%s", booking.id)

    db.commit()
    db.refresh(req)

    if booking.customer and booking.customer.user_id:
        enqueue_notification(db, user_id=booking.customer.user_id, notification_type="cancellation_approved", title="Cancellation Approved", message=f"Your cancellation request for booking {booking.booking_code} has been approved. Refund: {req.refund_amount} {req.currency}", entity_type="cancellation_request", entity_id=req.id)
        db.commit()

    if booking.customer and booking.customer.email:
        from app.utils.email_templates import cancellation_approved_email
        from app.utils.notification_triggers import send_templated_email
        login_url = f"{settings.FRONTEND_URL}/customer/bookings/{booking.id}"
        send_templated_email(
            db, booking.customer.email, "cancellation_approved",
            {"name": booking.customer.full_name, "booking_code": booking.booking_code, "tour_name": booking.tour_name,
             "refund_amount": req.refund_amount, "currency": req.currency, "login_url": login_url,
             "button_text": "View booking", "button_url": login_url},
            f"Cancellation approved - {booking.booking_code}",
            cancellation_approved_email(booking.customer.full_name, booking.booking_code, booking.tour_name, req.refund_amount, req.currency, login_url),
        )

    log_audit(db, actor=actor, action="approve_cancellation", entity_type="cancellation_request", entity_id=request_id, old_values={"status": "pending"}, new_values={"status": "approved", "refund_amount": str(req.refund_amount)}, request=request)
    return _serialize_request(req)


def reject_request(db: Session, request_id: int, data: CancellationReject, actor: User, request=None) -> dict:
    req = db.query(CancellationRequest).filter(CancellationRequest.id == request_id).with_for_update().first()
    if not req:
        raise HTTPException(status_code=404, detail="Cancellation request not found")
    if req.status != "pending":
        raise HTTPException(status_code=400, detail=f"Request is already '{req.status}'")

    req.status = "rejected"
    req.admin_notes = data.admin_notes
    req.reviewed_by = actor.id
    req.reviewed_at = utcnow()

    booking = req.booking
    if booking.booking_status == "cancellation_requested":
        from app.models.bookings import BookingStatusHistory
        restored = _prior_status_before_cancellation_request(db, booking.id)
        booking.booking_status = restored
        db.add(BookingStatusHistory(
            booking_id=booking.id,
            old_status="cancellation_requested",
            new_status=restored,
            changed_by_user_id=actor.id,
            change_source="cancellation_request",
            reason="Cancellation request rejected",
        ))

    db.commit()
    db.refresh(req)

    if booking.customer and booking.customer.user_id:
        enqueue_notification(db, user_id=booking.customer.user_id, notification_type="cancellation_rejected", title="Cancellation Rejected", message=f"Your cancellation request for booking {booking.booking_code} was rejected. Reason: {data.admin_notes}", entity_type="cancellation_request", entity_id=req.id)
        db.commit()

    if booking.customer and booking.customer.email:
        from app.utils.email_templates import cancellation_rejected_email
        from app.utils.notification_triggers import send_templated_email
        login_url = f"{settings.FRONTEND_URL}/customer/bookings/{booking.id}"
        send_templated_email(
            db, booking.customer.email, "cancellation_rejected",
            {"name": booking.customer.full_name, "booking_code": booking.booking_code, "tour_name": booking.tour_name,
             "reason": data.admin_notes or "", "login_url": login_url,
             "button_text": "View booking", "button_url": login_url},
            f"Cancellation request rejected - {booking.booking_code}",
            cancellation_rejected_email(booking.customer.full_name, booking.booking_code, booking.tour_name, data.admin_notes or "", login_url),
        )

    log_audit(db, actor=actor, action="reject_cancellation", entity_type="cancellation_request", entity_id=request_id, old_values={"status": "pending"}, new_values={"status": "rejected"}, request=request)
    return _serialize_request(req)


def process_refund(db: Session, request_id: int, data: ProcessRefundBody, actor: User, request=None) -> dict:
    req = db.query(CancellationRequest).filter(CancellationRequest.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Cancellation request not found")
    if req.status != "approved":
        raise HTTPException(status_code=400, detail="Request must be approved before processing refund")

    booking = req.booking

    # refund the actual Payment rows up to refund_amount (used to just flip status flags)
    from app.models.payments import Payment
    from app.schemas.payments import RefundRequest as PaymentRefundRequest
    from app.services.payments import process_refund as process_payment_refund

    remaining = money(req.refund_amount)
    gateway_refund_ids: list[str] = []
    if remaining > 0:
        payments = (
            db.query(Payment)
            .filter(Payment.booking_id == booking.id)
            .filter(Payment.payment_status.in_(["paid", "partially_paid", "partially_refunded"]))
            .order_by(Payment.id.asc())
            .all()
        )
        for payment in payments:
            if remaining <= 0:
                break
            refundable = money(payment.captured_amount or payment.paid_amount) - money(payment.refunded_amount)
            if refundable <= 0:
                continue
            amount = min(refundable, remaining)
            refund_result = process_payment_refund(
                db, payment.id,
                PaymentRefundRequest(amount=amount, reason=f"Cancellation request #{req.id}: {req.reason or 'Customer cancellation'}"),
                actor=actor, request=request,
            )
            if refund_result.get("gateway_refund_id"):
                gateway_refund_ids.append(refund_result["gateway_refund_id"])
            remaining -= amount

    req.status = "refund_processed"
    # Real gateway refund id(s) from the actual Stripe/PayPal call, not an
    # admin-typed guess - falls back to whatever the caller passed in for
    # bookings with no live-gateway payment (manual/test payments).
    req.gateway_refund_id = ", ".join(gateway_refund_ids) if gateway_refund_ids else data.gateway_refund_id
    req.refund_processed_at = utcnow()

    db.commit()
    db.refresh(req)
    db.refresh(booking)

    if booking.customer and booking.customer.user_id:
        enqueue_notification(db, user_id=booking.customer.user_id, notification_type="refund_processed", title="Refund Processed", message=f"Refund of {req.refund_amount} {req.currency} has been processed for booking {booking.booking_code}.", entity_type="cancellation_request", entity_id=req.id)
        db.commit()

    notify_admins(db, notification_type="refund_processed", title="Refund Processed", message=f"Refund of {req.refund_amount} {req.currency} processed for booking {booking.booking_code}.", entity_type="cancellation_request", entity_id=req.id)
    db.commit()

    log_audit(db, actor=actor, action="process_refund", entity_type="cancellation_request", entity_id=request_id, old_values={"status": "approved"}, new_values={"status": "refund_processed"}, request=request)
    return _serialize_request(req)


def list_rules(db: Session, tour_id: Optional[int] = None) -> list:
    q = db.query(RefundRule)
    if tour_id:
        q = q.filter(RefundRule.tour_id == tour_id)
    return [_serialize_rule(r) for r in q.order_by(RefundRule.days_before_tour_min.desc()).all()]


def create_rule(db: Session, data: RefundRuleCreate, actor: User, request=None) -> dict:
    rule = RefundRule(**data.model_dump())
    db.add(rule)
    db.flush()
    log_audit(db, actor=actor, action="create_refund_rule", entity_type="refund_rule", entity_id=rule.id, new_values=data.model_dump(), request=request)
    if rule.tour_id:
        from app.services.tour_versions import maybe_resubmit_for_review
        maybe_resubmit_for_review(db, rule.tour_id, actor)
    db.commit()
    db.refresh(rule)
    return _serialize_rule(rule)


def update_rule(db: Session, rule_id: int, data: RefundRuleUpdate, actor: User, request=None) -> dict:
    rule = db.query(RefundRule).filter(RefundRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Refund rule not found")
    old_values = _serialize_rule(rule)
    for key, value in data.model_dump().items():
        setattr(rule, key, value)
    log_audit(db, actor=actor, action="update_refund_rule", entity_type="refund_rule", entity_id=rule_id, old_values=old_values, new_values=data.model_dump(), request=request)
    if rule.tour_id:
        from app.services.tour_versions import maybe_resubmit_for_review
        maybe_resubmit_for_review(db, rule.tour_id, actor)
    db.commit()
    db.refresh(rule)
    return _serialize_rule(rule)


def delete_rule(db: Session, rule_id: int, actor: User, request=None):
    rule = db.query(RefundRule).filter(RefundRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Refund rule not found")
    tour_id = rule.tour_id
    db.delete(rule)
    log_audit(db, actor=actor, action="delete_refund_rule", entity_type="refund_rule", entity_id=rule_id, request=request)
    if tour_id:
        from app.services.tour_versions import maybe_resubmit_for_review
        maybe_resubmit_for_review(db, tour_id, actor)
    db.commit()
