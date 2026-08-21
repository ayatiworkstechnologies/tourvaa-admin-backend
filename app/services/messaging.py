import logging
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.affiliates import Affiliate
from app.models.agents import Agent
from app.models.bookings import Booking
from app.models.customers import Customer
from app.models.messaging import BookingConversation, BookingMessage, Conversation, Message
from app.models.suppliers import Supplier
from app.models.users import User
from app.services.messaging_ws import ws_manager
from app.utils.money import utcnow

logger = logging.getLogger(__name__)

PARTICIPANT_TYPES = ("agent", "supplier", "customer", "affiliate")
PREVIEW_LENGTH = 160


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
    db.commit()
    db.refresh(conv)
    return _serialize_conversation(db, conv, with_messages=True)


def get_own_conversation_thread(db: Session, user: User) -> dict:
    conv = get_or_create_conversation(db, user)
    conv.participant_unread_count = 0
    db.commit()
    db.refresh(conv)
    return _serialize_conversation(db, conv, with_messages=True)


async def send_message_as_participant(db: Session, user: User, body: str) -> dict:
    body = (body or "").strip()
    if not body:
        raise HTTPException(status_code=400, detail="Message body is required")

    conv = get_or_create_conversation(db, user)
    msg = Message(conversation_id=conv.id, sender_user_id=user.id, sender_role=conv.participant_type, body=body)
    db.add(msg)
    conv.last_message_at = utcnow()
    conv.last_message_preview = body[:PREVIEW_LENGTH]
    conv.admin_unread_count = (conv.admin_unread_count or 0) + 1
    db.commit()
    db.refresh(msg)
    db.refresh(conv)

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

    msg = Message(conversation_id=conv.id, sender_user_id=admin_user.id, sender_role="admin", body=body)
    db.add(msg)
    conv.last_message_at = utcnow()
    conv.last_message_preview = body[:PREVIEW_LENGTH]
    conv.participant_unread_count = (conv.participant_unread_count or 0) + 1
    db.commit()
    db.refresh(msg)
    db.refresh(conv)

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
    """Soft-deletes a BookingMessage the caller themselves sent (booking-
    scoped customer/agent <-> supplier thread). Own messages only."""
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
    serialized = _serialize_booking_message(msg)
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


# --- Booking-scoped direct messaging: customer/agent <-> supplier ---------

def _serialize_booking_message(msg: BookingMessage) -> dict:
    return {
        "id": msg.id,
        "conversation_id": msg.conversation_id,
        "sender_role": msg.sender_role,
        "sender_user_id": msg.sender_user_id,
        "sender_name": msg.sender.name if msg.sender else None,
        "body": None if msg.is_deleted else msg.body,
        "is_deleted": msg.is_deleted,
        "created_at": msg.created_at,
    }


def _serialize_booking_conversation(conv: BookingConversation, *, with_messages: bool = False) -> dict:
    data = {
        "id": conv.id,
        "booking_id": conv.booking_id,
        "booking_code": conv.booking.booking_code if conv.booking else None,
        "tour_name": conv.booking.tour_name if conv.booking else None,
        "initiator_role": conv.initiator_role,
        "initiator_user_id": conv.initiator_user_id,
        "initiator_name": conv.initiator_user.name if conv.initiator_user else None,
        "supplier_user_id": conv.supplier_user_id,
        "supplier_name": conv.supplier_user.name if conv.supplier_user else None,
        "status": conv.status,
        "last_message_at": conv.last_message_at,
        "last_message_preview": conv.last_message_preview,
        "initiator_unread_count": conv.initiator_unread_count,
        "supplier_unread_count": conv.supplier_unread_count,
        "created_at": conv.created_at,
    }
    if with_messages:
        data["messages"] = [_serialize_booking_message(m) for m in conv.messages]
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
    db.commit()
    db.refresh(conv)
    return _serialize_booking_conversation(conv, with_messages=True)


def _get_booking_conversation_for_supplier(db: Session, conversation_id: int, supplier_user: User) -> BookingConversation:
    conv = db.query(BookingConversation).filter(BookingConversation.id == conversation_id).first()
    if not conv or conv.supplier_user_id != supplier_user.id:
        raise HTTPException(status_code=404, detail="Conversation not found")
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
    db.commit()
    db.refresh(conv)
    return _serialize_booking_conversation(conv, with_messages=True)


async def send_booking_message_as_initiator(db: Session, booking_id: int, actor: User, body: str) -> dict:
    body = (body or "").strip()
    if not body:
        raise HTTPException(status_code=400, detail="Message body is required")

    conv = get_or_create_booking_conversation(db, booking_id, actor)
    msg = BookingMessage(conversation_id=conv.id, sender_user_id=actor.id, sender_role=conv.initiator_role, body=body)
    db.add(msg)
    conv.last_message_at = utcnow()
    conv.last_message_preview = body[:PREVIEW_LENGTH]
    conv.supplier_unread_count = (conv.supplier_unread_count or 0) + 1
    db.commit()
    db.refresh(msg)
    db.refresh(conv)

    serialized = _serialize_booking_message(msg)
    await ws_manager.notify_new_message(
        {"type": "new_booking_message", "conversation": _serialize_booking_conversation(conv), "message": serialized},
        participant_user_id=conv.supplier_user_id,
    )
    return serialized


async def send_booking_message_as_supplier(db: Session, conversation_id: int, supplier_user: User, body: str) -> dict:
    body = (body or "").strip()
    if not body:
        raise HTTPException(status_code=400, detail="Message body is required")

    conv = _get_booking_conversation_for_supplier(db, conversation_id, supplier_user)
    msg = BookingMessage(conversation_id=conv.id, sender_user_id=supplier_user.id, sender_role="supplier", body=body)
    db.add(msg)
    conv.last_message_at = utcnow()
    conv.last_message_preview = body[:PREVIEW_LENGTH]
    conv.initiator_unread_count = (conv.initiator_unread_count or 0) + 1
    db.commit()
    db.refresh(msg)
    db.refresh(conv)

    serialized = _serialize_booking_message(msg)
    await ws_manager.notify_new_message(
        {"type": "new_booking_message", "conversation": _serialize_booking_conversation(conv), "message": serialized},
        participant_user_id=conv.initiator_user_id,
    )
    return serialized


def supplier_booking_unread_count(db: Session, supplier_user: User) -> int:
    total = (
        db.query(func.coalesce(func.sum(BookingConversation.supplier_unread_count), 0))
        .filter(BookingConversation.supplier_user_id == supplier_user.id)
        .scalar()
    )
    return int(total or 0)
