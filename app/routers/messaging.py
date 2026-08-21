import logging

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.permissions import ACCESS_COOKIE_NAME, _decode_token, get_current_user, get_user_role_ids, require_any_permission
from app.database import SessionLocal, get_db
from app.models.permissions import Permission, RolePermission
from app.models.users import User
from app.services import messaging as messaging_service
from app.services.messaging_ws import ticket_store, ws_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/messages", tags=["Admin Messaging"])
ticket_router = APIRouter(prefix="/messages", tags=["Messaging"])
booking_router = APIRouter(prefix="/bookings", tags=["Booking Messaging"])
supplier_booking_router = APIRouter(prefix="/supplier/booking-messages", tags=["Supplier Booking Messaging"])
ws_router = APIRouter(tags=["Messaging WebSocket"])


@ticket_router.post("/ws-ticket")
def issue_ws_ticket(current_user: User = Depends(get_current_user)):
    return {"status": "success", "data": {"ticket": ticket_store.issue(current_user.id)}}


@ticket_router.delete("/{message_id}")
async def delete_own_message(message_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Deletes a message in an admin-support conversation (admin's own
    reply, or a supplier/agent/customer/affiliate's own message to admin).
    Own messages only, regardless of which portal the caller is in."""
    message = await messaging_service.delete_message(db, message_id, current_user)
    return {"status": "success", "message": "Message deleted", "data": message}


@ticket_router.delete("/booking/{message_id}")
async def delete_own_booking_message(message_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Deletes a message in a booking-scoped conversation (customer/agent
    <-> supplier). Own messages only."""
    message = await messaging_service.delete_booking_message(db, message_id, current_user)
    return {"status": "success", "message": "Message deleted", "data": message}


class SendReplyBody(BaseModel):
    body: str = Field(min_length=1)


@router.get("/conversations")
def conversations(
    type: str = Query(..., alias="type"),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=30, ge=1, le=100),
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_any_permission("messages.view")),
):
    return {"status": "success", **messaging_service.list_conversations_admin(db, type, page, limit)}


@router.get("/unread-summary")
def unread_summary(db: Session = Depends(get_db), _current_user: User = Depends(require_any_permission("messages.view"))):
    return {"status": "success", "data": messaging_service.admin_unread_summary(db)}


@router.get("/conversations/{conversation_id}")
def conversation_thread(conversation_id: int, db: Session = Depends(get_db), _current_user: User = Depends(require_any_permission("messages.view"))):
    return {"status": "success", "data": messaging_service.get_conversation_thread_admin(db, conversation_id)}


@router.post("/conversations/{conversation_id}/messages")
async def reply(conversation_id: int, data: SendReplyBody, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("messages.reply"))):
    message = await messaging_service.send_message_as_admin(db, conversation_id, current_user, data.body)
    return {"status": "success", "message": "Reply sent", "data": message}


@booking_router.get("/{booking_id}/conversation")
async def booking_conversation_thread(booking_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return {"status": "success", "data": messaging_service.get_booking_conversation_thread_for_initiator(db, booking_id, current_user)}


@booking_router.post("/{booking_id}/conversation/messages")
async def send_booking_conversation_message(booking_id: int, data: SendReplyBody, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    message = await messaging_service.send_booking_message_as_initiator(db, booking_id, current_user, data.body)
    return {"status": "success", "message": "Message sent", "data": message}


@supplier_booking_router.get("")
@supplier_booking_router.get("/")
async def supplier_booking_conversations(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=30, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return {"status": "success", **messaging_service.list_booking_conversations_for_supplier(db, current_user, page, limit)}


@supplier_booking_router.get("/unread-count")
async def supplier_booking_unread(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return {"status": "success", "data": {"unread": messaging_service.supplier_booking_unread_count(db, current_user)}}


@supplier_booking_router.get("/{conversation_id}")
async def supplier_booking_conversation_thread(conversation_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return {"status": "success", "data": messaging_service.get_booking_conversation_thread_for_supplier(db, conversation_id, current_user)}


@supplier_booking_router.post("/{conversation_id}/messages")
async def supplier_booking_conversation_reply(conversation_id: int, data: SendReplyBody, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    message = await messaging_service.send_booking_message_as_supplier(db, conversation_id, current_user, data.body)
    return {"status": "success", "message": "Reply sent", "data": message}


def _ws_user_by_id(user_id: int) -> User | None:
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user or user.account_status != "ACTIVE" or not user.is_active:
            return None
        db.expunge(user)
        return user
    finally:
        db.close()


def _ws_user(websocket: WebSocket) -> User | None:
    """Authenticate a websocket handshake. The browser connects directly to
    the backend's public origin (bypassing the Next.js rewrite proxy, which
    doesn't reliably support WebSocket upgrades), so it carries a one-time
    ticket minted via POST /messages/ws-ticket rather than the session
    cookie - a cross-origin request wouldn't have that cookie anyway. The
    cookie path stays as a same-origin/local-dev fallback."""
    ticket = websocket.query_params.get("ticket", "")
    if ticket:
        user_id = ticket_store.redeem(ticket)
        return _ws_user_by_id(user_id) if user_id else None

    token = websocket.cookies.get(ACCESS_COOKIE_NAME, "")
    if not token:
        return None
    try:
        payload = _decode_token(token)
    except Exception:
        return None
    if payload.get("token_type") not in {None, "access"}:
        return None

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == payload.get("user_id")).first()
        if not user or payload.get("token_version") is None or payload.get("token_version") != user.token_version:
            return None
        if user.account_status != "ACTIVE" or not user.is_active:
            return None
        db.expunge(user)
        return user
    finally:
        db.close()


def _has_messages_permission(user: User) -> bool:
    db = SessionLocal()
    try:
        role_ids = get_user_role_ids(user)
        if not role_ids:
            return False
        allowed = (
            db.query(Permission)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .filter(RolePermission.role_id.in_(role_ids))
            .filter(Permission.slug.in_(["messages.view", "messages.reply"]))
            .filter(Permission.is_active == True)
            .first()
        )
        return bool(allowed)
    finally:
        db.close()


@ws_router.websocket("/ws/messages")
async def messages_socket(websocket: WebSocket):
    user = _ws_user(websocket)
    if not user:
        await websocket.close(code=4401)
        return

    participant_type = messaging_service.participant_type_for_user(user)
    is_admin_listener = _has_messages_permission(user)

    if is_admin_listener:
        await ws_manager.connect_admin(websocket)
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            ws_manager.disconnect_admin(websocket)
        return

    if not participant_type:
        await websocket.close(code=4403)
        return

    await ws_manager.connect_participant(websocket, user.id)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        ws_manager.disconnect_participant(websocket, user.id)
