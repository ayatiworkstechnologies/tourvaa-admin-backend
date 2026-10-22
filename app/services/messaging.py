import logging
from urllib.parse import urlencode
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session, object_session

from app.config import settings
from app.auth.security import create_token
from app.models.affiliates import Affiliate
from app.models.agents import Agent
from app.models.bookings import Booking, BookingCommunication, EmailLog
from app.models.customers import Customer
from app.models.messaging import BookingConversation, BookingMessage, Conversation, Message
from app.models.suppliers import Supplier
from app.models.users import User
from app.services.notifications import enqueue_notification, notify_admins
from app.services.messaging_ws import ws_manager
from app.utils.email_templates import base_email, esc
from app.utils.notification_triggers import email_admins, send_templated_email
from app.utils.money import utcnow

logger = logging.getLogger(__name__)

PARTICIPANT_TYPES = ("agent", "supplier", "customer", "affiliate")
PREVIEW_LENGTH = 160


def _notification_preview(body: str) -> str:
    """Keep notification and browser-push bodies short and readable."""
    clean = " ".join((body or "").split())
    return clean if len(clean) <= PREVIEW_LENGTH else f"{clean[:PREVIEW_LENGTH - 1].rstrip()}…"


def _booking_message_url(*, booking_id: int, recipient_role: str) -> str:
    role = (recipient_role or "").strip().lower()
    portal = {
        "customer": "customer",
        "agent": "agent",
        "supplier": "supplier",
    }.get(role, "admin")
    suffix = "?tab=communications#booking-messages" if portal == "admin" else "#booking-messages"
    return f"{settings.FRONTEND_URL.rstrip('/')}/{portal}/bookings/{booking_id}{suffix}"


def _mail_reply_url(*, kind: str, user_id: int, conversation_id: int, booking_id: int | None = None) -> str:
    token = create_token(
        {"user_id": user_id, "conversation_id": conversation_id, "kind": kind, "booking_id": booking_id},
        token_type="mail_reply",
        expires_minutes=7 * 24 * 60,
    )
    return f"{settings.FRONTEND_URL.rstrip('/')}/message-reply?{urlencode({'token': token})}"


def _booking_message_email(*, sender_label: str, message_url: str) -> str:
    """Content-free booking-chat alert.

    The portal is the source of truth for both the message and replies.  This
    prevents sensitive booking text being copied into mailboxes and avoids the
    separate signed-reply experience falling out of sync with the chat.
    """
    return base_email(
        "New booking message",
        f"You have a new message from {esc(sender_label)}.",
        (
            "<p style=\"margin:0;\">Open the secure booking chat to read the message and reply. "
            "For privacy, booking details are not included in email notifications.</p>"
        ),
        "Open booking chat",
        message_url,
    )


def _support_message_url(*, recipient_role: str, participant_type: str, conversation_id: int | None = None) -> str:
    """Return the authenticated inbox for a support-message recipient."""
    role = (recipient_role or "").strip().lower()
    participant = (participant_type or "").strip().lower()
    if role == "admin":
        base_url = f"{settings.FRONTEND_URL.rstrip('/')}/admin/messages?type={participant}"
        return f"{base_url}&conversation={conversation_id}" if conversation_id else base_url
    portal_path = {
        "customer": "/customer/support",
        "agent": "/agent/messages",
        "supplier": "/supplier/messages",
        "affiliate": "/affiliate/messages",
    }.get(participant, "/")
    return f"{settings.FRONTEND_URL.rstrip('/')}{portal_path}"


def _support_message_email(*, sender_label: str, message_url: str, body: str | None = None) -> str:
    """Build a scoped alert with an expiring, signed reply action."""
    message_html = f'<blockquote style="margin:16px 0;padding:12px 16px;border-left:3px solid #2563eb;background:#f8fafc;white-space:pre-wrap;">{esc(body)}</blockquote>' if body else ""
    intro = "You can read the update below and reply securely without signing in." if body else "The message is available in your secure Tourvaa portal. Open the conversation to read it and send your reply."
    expiry = "For security, the reply link expires after 7 days. " if body else ""
    return base_email(
        "New support message",
        f"You have a new message from {esc(sender_label)}.",
        (
            f"<p style=\"margin:0;\">{intro}</p>"
            f"{message_html}"
            f"<p style=\"margin:16px 0 0;\">{expiry}"
            "Replies sent directly to this email are not added to the conversation.</p>"
        ),
        "View message & reply",
        message_url,
    )


def _email_support_message_admins(
    db: Session,
    *,
    participant_type: str,
    conversation_id: int,
) -> None:
    """Best-effort admin alert for a portal support message."""
    try:
        sender_label = f"{participant_type.capitalize()} portal"
        message_url = _support_message_url(
            conversation_id=conversation_id,
            recipient_role="admin",
            participant_type=participant_type,
        )
        email_admins(
            db,
            "support_message_received",
            {
                "sender_name": sender_label,
                "button_text": "View message & reply",
                "button_url": message_url,
            },
            f"New {participant_type} support message",
            _support_message_email(sender_label=sender_label, message_url=message_url),
            entity_type="support_conversation",
            entity_id=conversation_id,
        )
    except Exception as exc:
        logger.warning("Support-message email to admins failed: %s", exc)


def _email_support_message_recipient(
    db: Session,
    user_id: int,
    *,
    participant_type: str,
    conversation_id: int,
    body: str,
) -> None:
    """Best-effort portal-user alert for an Admin support reply."""
    try:
        recipient = db.query(User).filter(User.id == user_id).first()
        message_url = _mail_reply_url(kind="support", user_id=user_id, conversation_id=conversation_id)
        send_templated_email(
            db,
            recipient.email if recipient else None,
            "support_message_received",
            {
                "name": recipient.name if recipient else None,
                "sender_name": "Tourvaa Admin",
                "button_text": "View message & reply",
                "button_url": message_url,
            },
            "New message from Tourvaa Admin",
            _support_message_email(sender_label="Tourvaa Admin", message_url=message_url, body=body),
            entity_type="support_conversation",
            entity_id=conversation_id,
            recipient_type=participant_type,
        )
    except Exception as exc:
        logger.warning("Support-message email to user %s failed: %s", user_id, exc)


def _email_booking_message_recipient(
    db: Session,
    user_id: int,
    *,
    sender_label: str,
    booking_id: int,
    recipient_role: str,
    conversation_id: int,
    message_id: int,
) -> None:
    """Best-effort alert; mail delivery must never block a portal message."""
    try:
        recipient = db.query(User).filter(User.id == user_id).first()
        message_url = _booking_message_url(booking_id=booking_id, recipient_role=recipient_role)
        send_templated_email(
            db,
            recipient.email if recipient else None,
            "booking_message_received",
            {
                "sender_name": sender_label,
                "button_text": "Open booking chat",
                "button_url": message_url,
            },
            "New message from Tourvaa",
            _booking_message_email(sender_label=sender_label, message_url=message_url),
            entity_type="booking_message",
            entity_id=message_id,
            recipient_type=recipient_role,
        )
    except Exception as exc:
        logger.warning("Booking-message email to user %s failed: %s", user_id, exc)


def _email_booking_message_admins(db: Session, *, sender_label: str, subject: str, booking_id: int, message_id: int) -> None:
    """Best-effort operational alert; the in-app notification remains primary."""
    try:
        message_url = _booking_message_url(booking_id=booking_id, recipient_role="admin")
        email_admins(
            db,
            "booking_message_received",
            {
                "sender_name": sender_label,
                "button_text": "Open booking chat",
                "button_url": message_url,
            },
            subject,
            _booking_message_email(sender_label=sender_label, message_url=message_url),
            entity_type="booking_message",
            entity_id=message_id,
        )
    except Exception as exc:
        logger.warning("Booking-message email to admins failed: %s", exc)


def participant_type_for_user(user: User) -> Optional[str]:
    slug = ((user.role.slug if user.role else "") or "").lower()
    user_type = (user.user_type or "").upper()
    if user_type == "SUPPLIER" or "supplier" in slug:
        return "supplier"
    if user_type == "AGENT" or "agent" in slug:
        return "agent"
    if user_type == "CUSTOMER" or "customer" in slug:
        return "customer"
    if user_type == "AFFILIATE" or "affiliate" in slug:
        return "affiliate"
    return None


def _participant_profile(db: Session, participant_type: str, user: User) -> dict:
    name = user.name
    profile: dict = {}
    if participant_type == "agent":
        agent = db.query(Agent).filter(Agent.user_id == user.id).first()
        if agent:
            name = agent.agent_name or user.name
            profile["agent_id"] = agent.id
    elif participant_type == "supplier":
        supplier = db.query(Supplier).filter(Supplier.user_id == user.id).first()
        if supplier:
            name = supplier.supplier_name or user.name
            profile["supplier_id"] = supplier.id
    elif participant_type == "customer":
        customer = db.query(Customer).filter(Customer.user_id == user.id).first()
        if customer:
            name = customer.full_name or user.name
            profile["customer_id"] = customer.id
    elif participant_type == "affiliate":
        affiliate = db.query(Affiliate).filter(Affiliate.user_id == user.id).first()
        if affiliate:
            name = affiliate.name or user.name
            profile["affiliate_id"] = affiliate.id
    return {"name": name, "email": user.email, **profile}


def _serialize_message(msg: Message) -> dict:
    return {
        "id": msg.id,
        "conversation_id": msg.conversation_id,
        "sender_role": msg.sender_role,
        "sender_user_id": msg.sender_user_id,
        "sender_name": msg.sender.name if msg.sender else None,
        "body": None if msg.is_deleted else msg.body,
        "is_deleted": msg.is_deleted,
        "delivered_at": getattr(msg, "delivered_at", None),
        "read_at": getattr(msg, "read_at", None),
        "created_at": msg.created_at,
    }


def _serialize_conversation(db: Session, conv: Conversation, *, with_messages: bool = False) -> dict:
    profile = _participant_profile(db, conv.participant_type, conv.participant_user) if conv.participant_user else {"name": None, "email": None}
    data = {
        "id": conv.id,
        "participant_type": conv.participant_type,
        "participant_user_id": conv.participant_user_id,
        "participant_name": profile.get("name"),
        "participant_email": profile.get("email"),
        "participant_online": ws_manager.is_user_online(conv.participant_user_id),
        "admin_online": ws_manager.is_admin_online(),
        "agent_id": profile.get("agent_id"),
        "supplier_id": profile.get("supplier_id"),
        "customer_id": profile.get("customer_id"),
        "affiliate_id": profile.get("affiliate_id"),
        "status": conv.status,
        "last_message_at": conv.last_message_at,
        "last_message_preview": conv.last_message_preview,
        "admin_unread_count": conv.admin_unread_count,
        "participant_unread_count": conv.participant_unread_count,
        "created_at": conv.created_at,
    }
    if with_messages:
        data["messages"] = [_serialize_message(m) for m in conv.messages]
    return data


def get_or_create_conversation(db: Session, user: User) -> Conversation:
    participant_type = participant_type_for_user(user)
    if not participant_type:
        raise HTTPException(status_code=403, detail="This account type cannot use messaging")

    conv = db.query(Conversation).filter(Conversation.participant_user_id == user.id).first()
    if conv:
        return conv

    conv = Conversation(participant_type=participant_type, participant_user_id=user.id)
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return conv


def list_conversations_admin(db: Session, participant_type: str, page: int, limit: int) -> dict:
    if participant_type not in PARTICIPANT_TYPES:
        raise HTTPException(status_code=400, detail="Invalid participant type")

    query = db.query(Conversation).filter(Conversation.participant_type == participant_type)
    total = query.count()
    rows = (
        query.order_by(func.coalesce(Conversation.last_message_at, Conversation.created_at).desc(), Conversation.id.desc())
        .offset((page - 1) * limit)
        .limit(limit)
        .all()
    )
    items = [_serialize_conversation(db, row) for row in rows]
    return {"items": items, "total": total, "page": page, "limit": limit}


def get_conversation_thread_admin(db: Session, conversation_id: int) -> dict:
    conv = db.query(Conversation).filter(Conversation.id == conversation_id).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    conv.admin_unread_count = 0
    _mark_messages_read(message for message in conv.messages if message.sender_role != "admin")
    db.commit()
    db.refresh(conv)
    return _serialize_conversation(db, conv, with_messages=True)


def get_own_conversation_thread(db: Session, user: User) -> dict:
    conv = get_or_create_conversation(db, user)
    conv.participant_unread_count = 0
    _mark_messages_read(message for message in conv.messages if message.sender_role == "admin")
    db.commit()
    db.refresh(conv)
    return _serialize_conversation(db, conv, with_messages=True)


async def send_message_as_participant(db: Session, user: User, body: str) -> dict:
    body = (body or "").strip()
    if not body:
        raise HTTPException(status_code=400, detail="Message body is required")

    conv = get_or_create_conversation(db, user)
    msg = Message(conversation_id=conv.id, sender_user_id=user.id, sender_role=conv.participant_type, body=body, delivered_at=utcnow())
    db.add(msg)
    conv.last_message_at = utcnow()
    conv.last_message_preview = body[:PREVIEW_LENGTH]
    conv.admin_unread_count = (conv.admin_unread_count or 0) + 1
    sender_name = _participant_profile(db, conv.participant_type, user).get("name") or "A portal user"
    notify_admins(
        db,
        notification_type="support_message_received",
        title=f"New {conv.participant_type} support message",
        message=f"{sender_name}: {_notification_preview(body)}",
        entity_type="conversation",
        entity_id=conv.id,
    )
    db.commit()
    db.refresh(msg)
    db.refresh(conv)
    _email_support_message_admins(
        db,
        participant_type=conv.participant_type,
        conversation_id=conv.id,
    )

    serialized = _serialize_message(msg)
    await ws_manager.notify_new_message(
        {"type": "new_message", "conversation": _serialize_conversation(db, conv), "message": serialized},
        participant_user_id=conv.participant_user_id,
    )
    return serialized


async def send_message_as_admin(db: Session, conversation_id: int, admin_user: User, body: str) -> dict:
    body = (body or "").strip()
    if not body:
        raise HTTPException(status_code=400, detail="Message body is required")

    conv = db.query(Conversation).filter(Conversation.id == conversation_id).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    msg = Message(conversation_id=conv.id, sender_user_id=admin_user.id, sender_role="admin", body=body, delivered_at=utcnow())
    db.add(msg)
    conv.last_message_at = utcnow()
    conv.last_message_preview = body[:PREVIEW_LENGTH]
    conv.participant_unread_count = (conv.participant_unread_count or 0) + 1
    enqueue_notification(
        db,
        user_id=conv.participant_user_id,
        notification_type="support_message_received",
        title="New message from Tourvaa Admin",
        message=_notification_preview(body),
        entity_type="conversation",
        entity_id=conv.id,
    )
    db.commit()
    db.refresh(msg)
    db.refresh(conv)
    _email_support_message_recipient(
        db,
        conv.participant_user_id,
        participant_type=conv.participant_type,
        conversation_id=conv.id,
        body=body,
    )

    serialized = _serialize_message(msg)
    await ws_manager.notify_new_message(
        {"type": "new_message", "conversation": _serialize_conversation(db, conv), "message": serialized},
        participant_user_id=conv.participant_user_id,
    )
    return serialized


async def delete_message(db: Session, message_id: int, actor: User) -> dict:
    """Soft-deletes a Message the caller themselves sent (admin-support
    conversation). Deleting someone else's message is not allowed - this is
    a "take back what I said" action, not moderation (that's a separate,
    unbuilt admin capability)."""
    msg = db.query(Message).filter(Message.id == message_id).first()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")
    if msg.sender_user_id != actor.id:
        raise HTTPException(status_code=403, detail="You can only delete your own messages")
    if not msg.is_deleted:
        msg.is_deleted = True
        msg.deleted_at = utcnow()
        db.commit()
        db.refresh(msg)

    conv = msg.conversation
    serialized = _serialize_message(msg)
    await ws_manager.notify_new_message(
        {"type": "message_deleted", "conversation_id": conv.id, "message": serialized},
        participant_user_id=conv.participant_user_id,
    )
    return serialized


async def delete_booking_message(db: Session, message_id: int, actor: User) -> dict:
    """Soft-delete the caller's own message in a booking-specific Admin channel."""
    msg = db.query(BookingMessage).filter(BookingMessage.id == message_id).first()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")
    if msg.sender_user_id != actor.id:
        raise HTTPException(status_code=403, detail="You can only delete your own messages")
    if not msg.is_deleted:
        msg.is_deleted = True
        msg.deleted_at = utcnow()
        db.commit()
        db.refresh(msg)

    conv = msg.conversation
    serialized = _serialize_booking_message(
        msg,
        email_delivery=_booking_message_email_deliveries(db, [msg]).get(msg.id),
    )
    other_party_user_id = conv.supplier_user_id if actor.id == conv.initiator_user_id else conv.initiator_user_id
    await ws_manager.notify_new_message(
        {"type": "booking_message_deleted", "conversation_id": conv.id, "message": serialized},
        participant_user_id=other_party_user_id,
    )
    return serialized


def admin_unread_summary(db: Session) -> dict:
    rows = (
        db.query(Conversation.participant_type, Conversation.admin_unread_count)
        .filter(Conversation.admin_unread_count > 0)
        .all()
    )
    summary = {t: 0 for t in PARTICIPANT_TYPES}
    for participant_type, unread in rows:
        summary[participant_type] = summary.get(participant_type, 0) + unread
    return summary


def _mark_messages_read(messages) -> None:
    """Mark unread messages as seen by the opposite side of a two-party chat."""
    now = utcnow()
    for message in messages:
        if not getattr(message, "is_deleted", False) and getattr(message, "read_at", None) is None:
            message.read_at = now


# --- Booking-scoped direct messaging: customer/agent <-> supplier ---------

def _serialize_booking_message(
    msg: BookingMessage,
    *,
    hide_supplier_identity: bool = False,
    email_delivery: dict | None = None,
) -> dict:
    is_supplier_message = msg.sender_role == "supplier"
    return {
        "id": msg.id,
        "conversation_id": msg.conversation_id,
        "sender_role": msg.sender_role,
        "sender_user_id": msg.sender_user_id,
        # Customer/agent viewers never learn the supplier's real name, even
        # for their own messages in the thread (see hide_supplier_identity
        # on _serialize_booking_conversation - same policy, this is the
        # per-message counterpart of it).
        "sender_name": None if (hide_supplier_identity and is_supplier_message) else (msg.sender.name if msg.sender else None),
        # Admin replies are routed to one side of the split booking thread.
        # The frontend needs this value both for the immediate POST response
        # and when it reloads the conversation history.
        "recipient_role": msg.recipient_role,
        "body": None if msg.is_deleted else msg.body,
        "is_deleted": msg.is_deleted,
        "delivered_at": getattr(msg, "delivered_at", None),
        "read_at": getattr(msg, "read_at", None),
        "created_at": msg.created_at,
        # Metadata only: no recipient address, subject, or message content is
        # exposed in the conversation.
        "email_delivery": email_delivery,
    }


def _booking_message_email_deliveries(db: Session | None, messages: list[BookingMessage]) -> dict[int, dict]:
    """Return a compact, privacy-safe mail status for each chat message."""
    message_ids = [message.id for message in messages if message.id is not None]
    if not message_ids or db is None:
        return {}
    try:
        rows = (
            db.query(EmailLog.entity_id, EmailLog.status)
            .filter(EmailLog.entity_type == "booking_message", EmailLog.entity_id.in_(message_ids))
            .all()
        )
    except Exception:
        # Delivery status is supplementary; never prevent a chat message from
        # being returned if the log table is temporarily unavailable.
        return {}
    grouped: dict[int, list[str]] = {}
    for message_id, status in rows:
        grouped.setdefault(message_id, []).append(status)
    return {
        message_id: {
            "status": "failed" if any(status == "failed" for status in statuses) else "sent" if any(status == "sent" for status in statuses) else "sending",
            "recipient_count": len(statuses),
        }
        for message_id, statuses in grouped.items()
    }


def _flush_message(db: Session) -> None:
    """Allocate a message ID before its delivery log is created.

    The callable check keeps the small, database-free serializer tests simple;
    all real SQLAlchemy sessions provide ``flush``.
    """
    flush = getattr(db, "flush", None)
    if callable(flush):
        flush()


def _serialize_booking_conversation(
    conv: BookingConversation,
    *,
    with_messages: bool = False,
    hide_supplier_identity: bool = False,
    viewer_role: str | None = None,
) -> dict:
    data = {
        "id": conv.id,
        "booking_id": conv.booking_id,
        "booking_code": conv.booking.booking_code if conv.booking else None,
        "tour_name": conv.booking.tour_name if conv.booking else None,
        "initiator_role": conv.initiator_role,
        "initiator_user_id": conv.initiator_user_id,
        "initiator_name": conv.initiator_user.name if conv.initiator_user else None,
        "initiator_online": ws_manager.is_user_online(conv.initiator_user_id),
        "supplier_user_id": conv.supplier_user_id,
        "supplier_online": ws_manager.is_user_online(conv.supplier_user_id),
        "admin_online": ws_manager.is_admin_online(),
        # Presented to the customer/agent as a generic Tourvaa support
        # channel, never the actual supplier's identity - see
        # get_booking_conversation_thread_for_initiator and
        # send_booking_message_as_supplier's broadcast (always sent TO the
        # initiator), both of which pass hide_supplier_identity=True.
        # get_booking_conversation_thread_for_supplier/
        # list_booking_conversations_for_supplier (the supplier's own view)
        # never set this flag.
        "supplier_name": None if hide_supplier_identity else (conv.supplier_user.name if conv.supplier_user else None),
        "status": conv.status,
        "last_message_at": conv.last_message_at,
        "last_message_preview": conv.last_message_preview,
        "initiator_unread_count": conv.initiator_unread_count,
        "supplier_unread_count": conv.supplier_unread_count,
        "created_at": conv.created_at,
    }
    if with_messages:
        # A BookingConversation is the persistence container for the booking,
        # not permission to read messages addressed to the other portal. An
        # Agent/Customer must never receive an Admin-to-Supplier reply, and a
        # Supplier must never receive an Admin-to-Agent/Customer reply.
        messages = list(conv.messages)
        if viewer_role:
            messages = [
                message
                for message in messages
                if message.sender_role == viewer_role
                or (message.sender_role == "admin" and message.recipient_role == viewer_role)
            ]
        try:
            session = object_session(messages[0]) if messages else None
        except Exception:
            session = None
        deliveries = _booking_message_email_deliveries(session, messages)
        data["messages"] = [
            _serialize_booking_message(
                message,
                hide_supplier_identity=hide_supplier_identity,
                email_delivery=deliveries.get(message.id),
            )
            for message in messages
        ]
    return data


def get_or_create_booking_conversation(db: Session, booking_id: int, actor: User) -> BookingConversation:
    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    role = participant_type_for_user(actor)
    if role == "customer":
        if not booking.customer or booking.customer.user_id != actor.id:
            raise HTTPException(status_code=403, detail="This booking does not belong to you")
    elif role == "agent":
        if not booking.agent or booking.agent.user_id != actor.id:
            raise HTTPException(status_code=403, detail="This booking is not yours")
    else:
        raise HTTPException(status_code=403, detail="Only the customer or agent on a booking can message its supplier")

    if not booking.supplier or not booking.supplier.user_id:
        raise HTTPException(status_code=400, detail="This booking has no supplier assigned yet")

    conv = (
        db.query(BookingConversation)
        .filter(
            BookingConversation.booking_id == booking_id,
            BookingConversation.initiator_user_id == actor.id,
            BookingConversation.supplier_user_id == booking.supplier.user_id,
        )
        .first()
    )
    if conv:
        return conv

    conv = BookingConversation(
        booking_id=booking_id,
        initiator_role=role,
        initiator_user_id=actor.id,
        supplier_user_id=booking.supplier.user_id,
    )
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return conv


def get_booking_conversation_thread_for_initiator(db: Session, booking_id: int, actor: User) -> dict:
    conv = get_or_create_booking_conversation(db, booking_id, actor)
    conv.initiator_unread_count = 0
    _mark_messages_read(
        message for message in conv.messages
        if message.sender_role == "admin" and message.recipient_role == conv.initiator_role
    )
    db.commit()
    db.refresh(conv)
    return _serialize_booking_conversation(
        conv,
        with_messages=True,
        hide_supplier_identity=True,
        viewer_role=conv.initiator_role,
    )


def list_booking_conversation_threads_for_admin(db: Session, booking_id: int) -> list[dict]:
    """Return every portal conversation attached to a booking for Admin.

    Customer/agent portal messages are stored separately from the legacy
    internal ``BookingCommunication`` log. Admin needs a read-only view of
    the actual booking conversation(s) without creating a new thread or
    changing either participant's unread state.
    """
    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    conversations = (
        db.query(BookingConversation)
        .filter(BookingConversation.booking_id == booking_id)
        .order_by(BookingConversation.created_at.asc(), BookingConversation.id.asc())
        .all()
    )
    for conversation in conversations:
        _mark_messages_read(message for message in conversation.messages if message.sender_role != "admin")
    db.commit()
    return [_serialize_booking_conversation(conversation, with_messages=True) for conversation in conversations]


async def send_booking_message_as_admin(db: Session, conversation_id: int, admin_user: User, body: str, recipient_role: str) -> dict:
    """Reply from Admin to one party in a booking-scoped conversation."""
    body = (body or "").strip()
    if not body:
        raise HTTPException(status_code=400, detail="Message body is required")
    conv = db.query(BookingConversation).filter(BookingConversation.id == conversation_id).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    recipient_role = (recipient_role or "").strip().lower()
    if recipient_role not in {"supplier", conv.initiator_role}:
        raise HTTPException(status_code=422, detail="Reply target must be the supplier or booking initiator")
    recipient_user_id = conv.supplier_user_id if recipient_role == "supplier" else conv.initiator_user_id
    msg = BookingMessage(
        conversation_id=conv.id,
        sender_user_id=admin_user.id,
        sender_role="admin",
        recipient_role=recipient_role,
        body=body,
        delivered_at=utcnow(),
    )
    db.add(msg)
    _flush_message(db)
    conv.last_message_at = utcnow()
    conv.last_message_preview = body[:PREVIEW_LENGTH]
    if recipient_role == "supplier":
        conv.supplier_unread_count = (conv.supplier_unread_count or 0) + 1
    else:
        conv.initiator_unread_count = (conv.initiator_unread_count or 0) + 1
    enqueue_notification(db, user_id=recipient_user_id, notification_type="booking_message_received", title="New message from Tourvaa", message=_notification_preview(body), entity_type="booking_conversation", entity_id=conv.id)
    _email_booking_message_recipient(
        db,
        recipient_user_id,
        sender_label="Tourvaa Admin",
        booking_id=conv.booking_id,
        recipient_role=recipient_role,
        conversation_id=conv.id,
        message_id=msg.id,
    )
    db.commit(); db.refresh(msg); db.refresh(conv)
    serialized = _serialize_booking_message(
        msg,
        email_delivery=_booking_message_email_deliveries(db, [msg]).get(msg.id),
    )
    await ws_manager.notify_new_message({"type": "new_booking_message", "conversation": _serialize_booking_conversation(conv, hide_supplier_identity=recipient_role != "supplier"), "message": serialized}, participant_user_id=recipient_user_id)
    return serialized


async def send_mail_reply(db: Session, claims: dict, body: str) -> dict:
    """Send a reply authorized by a short-lived link delivered to one user.

    The signed claims are still checked against current conversation ownership,
    so forwarding a stale or mismatched URL cannot expose another thread.
    """
    user_id = claims.get("user_id")
    conversation_id = claims.get("conversation_id")
    user = db.query(User).filter(User.id == user_id, User.is_active == True, User.account_status == "ACTIVE").first()
    if not user:
        raise HTTPException(status_code=401, detail="This reply link is no longer valid")

    if claims.get("kind") == "support":
        conversation = db.query(Conversation).filter(
            Conversation.id == conversation_id,
            Conversation.participant_user_id == user.id,
        ).first()
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return await send_message_as_participant(db, user, body)

    if claims.get("kind") == "booking":
        conversation = db.query(BookingConversation).filter(BookingConversation.id == conversation_id).first()
        if not conversation or conversation.booking_id != claims.get("booking_id"):
            raise HTTPException(status_code=404, detail="Conversation not found")
        if conversation.supplier_user_id == user.id:
            return await send_booking_message_as_supplier(db, conversation.id, user, body)
        if conversation.initiator_user_id == user.id:
            return await send_booking_message_as_initiator(db, conversation.booking_id, user, body)
        raise HTTPException(status_code=404, detail="Conversation not found")

    raise HTTPException(status_code=400, detail="Invalid reply link")


def _get_booking_conversation_for_supplier(db: Session, conversation_id: int, supplier_user: User) -> BookingConversation:
    conv = db.query(BookingConversation).filter(BookingConversation.id == conversation_id).first()
    if not conv or conv.supplier_user_id != supplier_user.id:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conv


def get_or_create_booking_conversation_for_supplier(db: Session, booking_id: int, supplier_user: User) -> BookingConversation:
    """Return the booking's shared portal-message container for its supplier.

    Supplier booking messages are addressed to Tourvaa Admin, but the existing
    booking conversation row is also used to keep the Admin audit view grouped
    by booking and portal party.  Creating the row here lets a supplier start
    the Admin conversation rather than requiring an agent/customer to write
    first.
    """
    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    if not booking.supplier or booking.supplier.user_id != supplier_user.id:
        raise HTTPException(status_code=403, detail="This booking is not assigned to you")

    existing = (
        db.query(BookingConversation)
        .filter(
            BookingConversation.booking_id == booking_id,
            BookingConversation.supplier_user_id == supplier_user.id,
        )
        .first()
    )
    if existing:
        return existing

    if booking.agent and booking.agent.user_id:
        initiator_role, initiator_user_id = "agent", booking.agent.user_id
    elif booking.customer and booking.customer.user_id:
        initiator_role, initiator_user_id = "customer", booking.customer.user_id
    else:
        raise HTTPException(status_code=400, detail="This booking has no portal contact for messaging")

    conv = BookingConversation(
        booking_id=booking_id,
        initiator_role=initiator_role,
        initiator_user_id=initiator_user_id,
        supplier_user_id=supplier_user.id,
    )
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return conv


def list_booking_conversations_for_supplier(db: Session, supplier_user: User, page: int, limit: int) -> dict:
    query = db.query(BookingConversation).filter(BookingConversation.supplier_user_id == supplier_user.id)
    total = query.count()
    rows = (
        query.order_by(func.coalesce(BookingConversation.last_message_at, BookingConversation.created_at).desc(), BookingConversation.id.desc())
        .offset((page - 1) * limit)
        .limit(limit)
        .all()
    )
    return {"items": [_serialize_booking_conversation(row) for row in rows], "total": total, "page": page, "limit": limit}


def get_booking_conversation_thread_for_supplier(db: Session, conversation_id: int, supplier_user: User) -> dict:
    conv = _get_booking_conversation_for_supplier(db, conversation_id, supplier_user)
    conv.supplier_unread_count = 0
    _mark_messages_read(
        message for message in conv.messages
        if message.sender_role == "admin" and message.recipient_role == "supplier"
    )
    db.commit()
    db.refresh(conv)
    return _serialize_booking_conversation(conv, with_messages=True, viewer_role="supplier")


def get_booking_conversation_thread_for_supplier_booking(db: Session, booking_id: int, supplier_user: User) -> dict:
    conv = get_or_create_booking_conversation_for_supplier(db, booking_id, supplier_user)
    conv.supplier_unread_count = 0
    _mark_messages_read(
        message for message in conv.messages
        if message.sender_role == "admin" and message.recipient_role == "supplier"
    )
    db.commit()
    db.refresh(conv)
    return _serialize_booking_conversation(conv, with_messages=True, viewer_role="supplier")


async def send_booking_message_as_initiator(db: Session, booking_id: int, actor: User, body: str) -> dict:
    body = (body or "").strip()
    if not body:
        raise HTTPException(status_code=400, detail="Message body is required")

    conv = get_or_create_booking_conversation(db, booking_id, actor)
    msg = BookingMessage(conversation_id=conv.id, sender_user_id=actor.id, sender_role=conv.initiator_role, body=body, delivered_at=utcnow())
    db.add(msg)
    _flush_message(db)
    # Portal messages belong only to BookingConversation / BookingMessage.
    # Do not mirror them into BookingCommunication: that legacy log is now
    # reserved for Internal Communications in the Admin booking workspace.
    conv.last_message_at = utcnow()
    conv.last_message_preview = body[:PREVIEW_LENGTH]
    notify_admins(
        db,
        notification_type="booking_message_received",
        title=f"New {conv.initiator_role} booking message",
        message=_notification_preview(body),
        entity_type="booking_conversation",
        entity_id=conv.id,
    )
    _email_booking_message_admins(
        db,
        sender_label=conv.initiator_role.capitalize(),
        subject=f"New {conv.initiator_role} booking message",
        booking_id=conv.booking_id,
        message_id=msg.id,
    )
    db.commit()
    db.refresh(msg)
    db.refresh(conv)

    serialized = _serialize_booking_message(
        msg,
        email_delivery=_booking_message_email_deliveries(db, [msg]).get(msg.id),
    )
    await ws_manager.notify_new_message(
        {"type": "new_booking_message", "conversation": _serialize_booking_conversation(conv), "message": serialized},
        participant_user_id=actor.id,
    )
    return serialized


async def send_booking_message_as_supplier(db: Session, conversation_id: int, supplier_user: User, body: str) -> dict:
    body = (body or "").strip()
    if not body:
        raise HTTPException(status_code=400, detail="Message body is required")

    conv = _get_booking_conversation_for_supplier(db, conversation_id, supplier_user)
    msg = BookingMessage(conversation_id=conv.id, sender_user_id=supplier_user.id, sender_role="supplier", body=body, delivered_at=utcnow())
    db.add(msg)
    _flush_message(db)
    conv.last_message_at = utcnow()
    conv.last_message_preview = body[:PREVIEW_LENGTH]
    # Supplier booking messages are private Supplier <-> Tourvaa Admin
    # messages.  Do not route them to the booking's agent/customer merely
    # because that user anchors the shared booking conversation row.
    notify_admins(
        db,
        notification_type="booking_message_received",
        title="New supplier booking message",
        message=_notification_preview(body),
        entity_type="booking_conversation",
        entity_id=conv.id,
    )
    _email_booking_message_admins(
        db,
        sender_label="Supplier",
        subject="New supplier booking message",
        booking_id=conv.booking_id,
        message_id=msg.id,
    )
    db.commit()
    db.refresh(msg)
    db.refresh(conv)

    serialized = _serialize_booking_message(
        msg,
        email_delivery=_booking_message_email_deliveries(db, [msg]).get(msg.id),
    )
    await ws_manager.notify_new_message(
        {
            "type": "new_booking_message",
            "conversation": _serialize_booking_conversation(conv),
            "message": serialized,
        },
        participant_user_id=supplier_user.id,
    )
    return serialized


def supplier_booking_unread_count(db: Session, supplier_user: User) -> int:
    total = (
        db.query(func.coalesce(func.sum(BookingConversation.supplier_unread_count), 0))
        .filter(BookingConversation.supplier_user_id == supplier_user.id)
        .scalar()
    )
    return int(total or 0)
