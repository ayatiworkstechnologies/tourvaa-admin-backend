"""
Centralized helper for all domain event notifications.
Import and call these functions from service layers — keeps notification
logic out of the business logic files.
"""

from sqlalchemy.orm import Session

from app.modules.notifications.service import enqueue_notification, notify_admins


# ---------------------------------------------------------------------------
# Supplier events
# ---------------------------------------------------------------------------


def notify_supplier_registered(db: Session, *, supplier_id: int, supplier_name: str, user_id: int | None = None):
    notify_admins(db, notification_type="supplier_registered", title="New Supplier Registered", message=f"Supplier '{supplier_name}' has registered and is awaiting approval.", entity_type="supplier", entity_id=supplier_id)
    db.flush()


def notify_supplier_submitted_verification(db: Session, *, supplier_id: int, supplier_name: str, user_id: int | None = None):
    notify_admins(db, notification_type="supplier_submitted_verification", title="Supplier Submitted for Review", message=f"Supplier '{supplier_name}' has submitted their profile for admin review.", entity_type="supplier", entity_id=supplier_id)
    db.flush()


def notify_supplier_approved(db: Session, *, supplier_id: int, supplier_name: str, user_id: int | None = None):
    notify_admins(db, notification_type="supplier_approved", title="Supplier Approved", message=f"Supplier '{supplier_name}' has been approved.", entity_type="supplier", entity_id=supplier_id)
    if user_id:
        enqueue_notification(db, user_id=user_id, notification_type="supplier_approved", title="Your supplier profile is approved!", message=f"Congratulations! Your supplier profile '{supplier_name}' has been approved. You can now start receiving bookings.", entity_type="supplier", entity_id=supplier_id)
    db.flush()


def notify_supplier_rejected(db: Session, *, supplier_id: int, supplier_name: str, rejection_reason: str = "", user_id: int | None = None):
    if user_id:
        enqueue_notification(db, user_id=user_id, notification_type="supplier_rejected", title="Supplier Profile Rejected", message=f"Your supplier profile '{supplier_name}' was not approved. Reason: {rejection_reason}", entity_type="supplier", entity_id=supplier_id)
    db.flush()


def notify_supplier_reupload_requested(db: Session, *, supplier_id: int, supplier_name: str, requirements: str = "", user_id: int | None = None):
    if user_id:
        enqueue_notification(db, user_id=user_id, notification_type="supplier_reupload_requested", title="Document Reupload Required", message=f"Please reupload documents for your supplier profile '{supplier_name}'. Required: {requirements}", entity_type="supplier", entity_id=supplier_id)
    db.flush()


# ---------------------------------------------------------------------------
# Agent events
# ---------------------------------------------------------------------------


def notify_agent_registered(db: Session, *, agent_id: int, agent_name: str, user_id: int | None = None):
    notify_admins(db, notification_type="agent_registered", title="New Agent Registered", message=f"Agent/reseller '{agent_name}' has registered and is awaiting approval.", entity_type="agent", entity_id=agent_id)
    db.flush()


def notify_agent_approved(db: Session, *, agent_id: int, agent_name: str, user_id: int | None = None):
    notify_admins(db, notification_type="agent_approved", title="Agent Approved", message=f"Agent '{agent_name}' has been approved.", entity_type="agent", entity_id=agent_id)
    if user_id:
        enqueue_notification(db, user_id=user_id, notification_type="agent_approved", title="Your agent profile is approved!", message=f"Congratulations! Your agent profile '{agent_name}' has been approved.", entity_type="agent", entity_id=agent_id)
    db.flush()


def notify_agent_rejected(db: Session, *, agent_id: int, agent_name: str, rejection_reason: str = "", user_id: int | None = None):
    if user_id:
        enqueue_notification(db, user_id=user_id, notification_type="agent_rejected", title="Agent Profile Rejected", message=f"Your agent profile '{agent_name}' was not approved. Reason: {rejection_reason}", entity_type="agent", entity_id=agent_id)
    db.flush()


# ---------------------------------------------------------------------------
# Booking events
# ---------------------------------------------------------------------------


def notify_booking_status_changed(db: Session, *, booking_id: int, booking_code: str, new_status: str, customer_user_id: int | None = None, supplier_user_id: int | None = None):
    status_messages = {
        "confirmed": "Your booking has been confirmed.",
        "cancelled": "Your booking has been cancelled.",
        "completed": "Your booking has been completed. Thank you!",
        "in_progress": "Your booking is now in progress.",
    }
    msg = status_messages.get(new_status, f"Booking status updated to: {new_status}")
    if customer_user_id:
        enqueue_notification(db, user_id=customer_user_id, notification_type=f"booking_{new_status}", title=f"Booking {new_status.capitalize()}", message=f"Booking {booking_code}: {msg}", entity_type="booking", entity_id=booking_id)
    db.flush()


def notify_customer_cancellation_requested(db: Session, *, booking_id: int, booking_code: str, customer_user_id: int | None = None):
    notify_admins(db, notification_type="cancellation_requested", title="Cancellation Requested", message=f"Customer requested cancellation for booking {booking_code}.", entity_type="booking", entity_id=booking_id)
    if customer_user_id:
        enqueue_notification(db, user_id=customer_user_id, notification_type="cancellation_requested", title="Cancellation Request Received", message=f"Your cancellation request for booking {booking_code} has been received and is being reviewed.", entity_type="booking", entity_id=booking_id)
    db.flush()


def notify_refund_processed(db: Session, *, booking_id: int, booking_code: str, amount: str, currency: str = "USD", customer_user_id: int | None = None, supplier_user_id: int | None = None):
    if customer_user_id:
        enqueue_notification(db, user_id=customer_user_id, notification_type="refund_processed", title="Refund Processed", message=f"A refund of {amount} {currency} has been processed for booking {booking_code}.", entity_type="booking", entity_id=booking_id)
    notify_admins(db, notification_type="refund_processed", title="Refund Processed", message=f"Refund of {amount} {currency} processed for booking {booking_code}.", entity_type="booking", entity_id=booking_id)
    db.flush()


# ---------------------------------------------------------------------------
# Payment events
# ---------------------------------------------------------------------------


def notify_payment_failed(db: Session, *, payment_id: int, booking_code: str, reason: str = "", customer_user_id: int | None = None):
    if customer_user_id:
        enqueue_notification(db, user_id=customer_user_id, notification_type="payment_failed", title="Payment Failed", message=f"Payment for booking {booking_code} failed. {reason}", entity_type="payment", entity_id=payment_id)
    notify_admins(db, notification_type="payment_failed", title="Payment Failed", message=f"Payment for booking {booking_code} failed. {reason}", entity_type="payment", entity_id=payment_id)
    db.flush()
