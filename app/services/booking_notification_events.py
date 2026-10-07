"""Central, idempotent booking-notification event definitions.

New booking lifecycle notifications must enter through this module instead of
embedding recipient and event naming rules in routers.
"""
from enum import StrEnum

from sqlalchemy.orm import Session

from app.models.notifications import Notification
from app.services.notifications import enqueue_notification


class BookingNotificationEvent(StrEnum):
    BOOKING_CREATED = "booking_created"
    BOOKING_CREATION_FAILED = "booking_creation_failed"
    BOOKING_CONFIRMED = "booking_confirmed"
    BOOKING_CONFIRMATION_FAILED = "booking_confirmation_failed"
    PAYMENT_DUE_REMINDER = "payment_due_reminder"
    PAYMENT_SUCCESS = "payment_success"
    PAYMENT_FAILED = "payment_failed"
    DEPOSIT_PAYMENT_RECEIVED = "deposit_payment_received"
    BALANCE_PAYMENT_RECEIVED = "balance_payment_received"
    BOOKING_MODIFICATION_REQUESTED = "booking_modification_requested"
    BOOKING_MODIFICATION_CONFIRMED = "booking_modification_confirmed"
    CANCELLATION_REQUESTED_CUSTOMER = "cancellation_requested_customer"
    CANCELLATION_REQUESTED_AGENT = "cancellation_requested_agent"
    CANCELLATION_REQUESTED_SUPPLIER = "cancellation_requested_supplier"
    CANCELLATION_APPROVED = "cancellation_approved"
    BOOKING_CANCELLED_BY_TOURVAA = "booking_cancelled_by_tourvaa"
    REFUND_INITIATED = "refund_initiated"
    REFUND_COMPLETED = "refund_completed"
    BOOKING_DECLINED = "booking_declined"
    BOOKING_EXPIRED = "booking_expired"
    BOOKING_REMINDER_7_DAYS = "booking_reminder_7_days"
    BOOKING_REMINDER_24_HOURS = "booking_reminder_24_hours"
    TOUR_COMPLETED = "tour_completed"
    REVIEW_REQUEST = "review_request"
    MODIFICATION_REJECTED = "modification_rejected"
    CANCELLATION_REJECTED = "cancellation_rejected"
    REFUND_REQUESTED = "refund_requested"
    REFUND_APPROVED = "refund_approved"
    REFUND_FAILED = "refund_failed"
    TOUR_DATE_CHANGED = "tour_date_changed"
    REVIEW_SUBMITTED = "review_submitted"
    INVOICE_GENERATED = "invoice_generated"
    INVOICE_PAID = "invoice_paid"
    AGENT_INVOICE_GENERATED = "agent_invoice_generated"
    AGENT_COMMISSION_GENERATED = "agent_commission_generated"
    AGENT_COMMISSION_PAID = "agent_commission_paid"
    SUPPLIER_SETTLEMENT_DUE = "supplier_settlement_due"
    SUPPLIER_SETTLEMENT_COMPLETED = "supplier_settlement_completed"
    SUPPLIER_ACCOUNT_APPROVED = "supplier_account_approved"
    SUPPLIER_ACCOUNT_REJECTED = "supplier_account_rejected"
    AGENT_ACCOUNT_APPROVED = "agent_account_approved"
    AGENT_ACCOUNT_REJECTED = "agent_account_rejected"
    SUPPLIER_DOCUMENTS_SUBMITTED = "supplier_documents_submitted"
    SUPPLIER_DOCUMENTS_APPROVED = "supplier_documents_approved"
    SUPPLIER_DOCUMENTS_REJECTED = "supplier_documents_rejected"
    AGENT_DOCUMENTS_SUBMITTED = "agent_documents_submitted"
    AGENT_DOCUMENTS_APPROVED = "agent_documents_approved"
    AGENT_DOCUMENTS_REJECTED = "agent_documents_rejected"


def emit_in_app_once(
    db: Session,
    *,
    event: BookingNotificationEvent,
    booking_id: int,
    user_id: int | None,
    recipient_type: str,
    title: str,
    message: str,
) -> bool:
    """Create one durable in-app event per booking/event/recipient.

    The metadata marker provides retry safety immediately while the broader
    lifecycle email dispatcher is migrated onto the same event contract.
    """
    if not user_id:
        return False
    exists = (
        db.query(Notification.id)
        .filter(
            Notification.user_id == user_id,
            Notification.notification_type == str(event),
            Notification.entity_type == "booking",
            Notification.entity_id == booking_id,
        )
        .first()
    )
    if exists:
        return False
    enqueue_notification(
        db,
        user_id=user_id,
        notification_type=str(event),
        title=title,
        message=message,
        entity_type="booking",
        entity_id=booking_id,
        metadata={"event_type": str(event), "recipient_type": recipient_type},
    )
    return True


def reserve_email_delivery(db: Session, *, event: BookingNotificationEvent, entity_type: str, entity_id: int, recipient_type: str, recipient_email: str, template_key: str, event_version: str = "1"):
    """Reserve a delivery before scheduling SMTP; duplicates return None.

    Callers may commit their business transaction normally; SMTP delivery is
    intentionally performed afterwards by the existing asynchronous mailer.
    """
    from sqlalchemy.exc import IntegrityError
    from app.models.notifications import NotificationDelivery

    key = f"{event}:{entity_type}:{entity_id}:{recipient_type}:{recipient_email.lower()}:{event_version}"
    row = NotificationDelivery(
        event_type=str(event), entity_type=entity_type, entity_id=entity_id,
        recipient_type=recipient_type, recipient_email=recipient_email,
        template_key=template_key, idempotency_key=key,
    )
    try:
        with db.begin_nested():
            db.add(row)
            db.flush()
        return row
    except IntegrityError:
        return None
