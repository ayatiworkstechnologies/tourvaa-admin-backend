from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.modules.bookings.schemas import (
    AssignSupplierRequest,
    BookingCancelRequest,
    BookingCommunicationCreate,
    MessageReplyCreate,
    BookingCreate,
    BookingStatusUpdate,
    BookingUpdate,
    SupplierDecisionRequest,
    SupplierPostponeRequest,
    SupplierNotifyRequest,
)
from app.modules.bookings.service import (
    add_communication,
    add_communication_reply,
    calculate_booking_price,
    export_bookings,
    get_payment_link,
    assign_supplier,
    cancel_booking,
    create_booking,
    get_booking_detail,
    get_bookings,
    get_status_history,
    get_upcoming_bookings,
    supplier_accept_booking,
    supplier_cancel_booking,
    supplier_complete_booking,
    supplier_decline_booking,
    supplier_notify_parties,
    supplier_postpone_booking,
    update_booking,
    update_booking_status,
)
from app.modules.common.auth import require_any_permission, get_current_user
from app.modules.common.pagination import pagination_params
from app.modules.customers.models import CustomerCommunication
from app.modules.users.models import User

router = APIRouter(prefix="/bookings", tags=["Bookings"])
supplier_router = APIRouter(prefix="/supplier/bookings", tags=["Supplier Bookings"])
supplier_portal_router = APIRouter(prefix="/supplier", tags=["Supplier Portal"])
agent_portal_router = APIRouter(prefix="/agent", tags=["Agent Portal"])


@router.get("")
@router.get("/")
def list_bookings(
    params: dict = Depends(pagination_params),
    customer_id: int = Query(default=0),
    booking_status: str = Query(default=""),
    payment_status: str = Query(default=""),
    supplier_acceptance_status: str = Query(default=""),
    country_id: int = Query(default=0),
    supplier_id: int = Query(default=0),
    agent_id: int = Query(default=0),
    tour_id: int = Query(default=0),
    start_date: str = Query(default=""),
    end_date: str = Query(default=""),
    sort_by: str = Query(default="newest"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_permission("bookings.view", "view-bookings")),
):
    result = get_bookings(db, page=params["page"], limit=params["limit"], search=params["search"], customer_id=customer_id or None, booking_status=booking_status, payment_status=payment_status, supplier_acceptance_status=supplier_acceptance_status, country_id=country_id or None, supplier_id=supplier_id or None, agent_id=agent_id or None, tour_id=tour_id or None, start_date=start_date, end_date=end_date, sort_by=sort_by, actor=current_user)
    return {"status": "success", **result}




@router.get("/export")
def export_bookings_endpoint(db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("bookings.export", "bookings.view"))):
    return {"status": "success", "data": export_bookings(db, current_user)}

@router.get("/upcoming")
def upcoming_bookings(db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("bookings.view", "view-bookings"))):
    return {"status": "success", **get_upcoming_bookings(db, current_user)}


@router.post("/calculate-price")
def calculate_price(data: BookingCreate, db: Session = Depends(get_db)):
    return {"status": "success", "data": calculate_booking_price(db, data)}


@router.post("")
@router.post("/")
def add_booking(data: BookingCreate, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("bookings.create", "create-bookings"))):
    return {"status": "success", "message": "Booking created successfully", "data": create_booking(db, data, actor=current_user, request=request)}


@router.get("/{booking_id}")
def booking_detail(booking_id: int, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("bookings.view", "view-bookings"))):
    return {"status": "success", "data": get_booking_detail(db, booking_id, actor=current_user, request=request)}


@router.put("/{booking_id}")
def edit_booking(booking_id: int, data: BookingUpdate, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("bookings.edit", "update-bookings"))):
    return {"status": "success", "message": "Booking updated successfully", "data": update_booking(db, booking_id, data, actor=current_user, request=request)}


@router.patch("/{booking_id}/status")
def change_booking_status(booking_id: int, data: BookingStatusUpdate, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("bookings.update_status", "bookings.edit", "update-bookings"))):
    return {"status": "success", "message": "Booking status updated successfully", "data": update_booking_status(db, booking_id, data, actor=current_user, request=request)}




@router.get("/{booking_id}/payment-link")
def booking_payment_link(booking_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("bookings.view_payments", "bookings.view", "payments.view"))):
    return {"status": "success", "data": get_payment_link(db, booking_id, current_user)}

@router.get("/{booking_id}/status-history")
def booking_status_history(booking_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("bookings.view_history", "bookings.view", "view-bookings"))):
    return {"status": "success", "data": get_status_history(db, booking_id, current_user)}


@router.post("/{booking_id}/assign-supplier")
def assign_supplier_endpoint(booking_id: int, data: AssignSupplierRequest, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("bookings.assign_supplier", "bookings.edit", "update-bookings"))):
    return {"status": "success", "message": "Supplier assigned", "data": assign_supplier(db, booking_id, data, current_user, request)}


@router.patch("/{booking_id}/cancel")
def cancel_booking_endpoint(booking_id: int, request: Request, data: BookingCancelRequest | None = None, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("bookings.cancel", "update-bookings"))):
    cancel_data = data or BookingCancelRequest(reason="Cancelled by admin")
    return {"status": "success", "message": "Booking cancelled successfully", "data": cancel_booking(db, booking_id, cancel_data, actor=current_user, request=request)}


@router.post("/{booking_id}/communications")
def create_booking_communication(booking_id: int, data: BookingCommunicationCreate,
    request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("bookings.edit", "bookings.view"))):
    return {"status": "success", "data": add_communication(db, booking_id, data, current_user, request)}




@router.post("/communications/{communication_id}/replies")
def reply_booking_communication(communication_id: int, data: MessageReplyCreate, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("bookings.edit", "bookings.view"))):
    return {"status": "success", "data": add_communication_reply(db, communication_id, data.message, current_user, request)}

@supplier_router.get("")
@supplier_router.get("/")
def supplier_bookings(params: dict = Depends(pagination_params), db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("bookings.view", "view-bookings"))):
    return {"status": "success", **get_bookings(db, page=params["page"], limit=params["limit"], search=params["search"], actor=current_user)}


@supplier_router.get("/{booking_id}")
def supplier_booking_detail(booking_id: int, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("bookings.view", "view-bookings"))):
    return {"status": "success", "data": get_booking_detail(db, booking_id, actor=current_user, request=request)}


@supplier_router.post("/{booking_id}/accept")
def supplier_accept(booking_id: int, data: SupplierDecisionRequest, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("bookings.update_status", "update-bookings"))):
    return {"status": "success", "data": supplier_accept_booking(db, booking_id, data, current_user, request)}


@supplier_router.post("/{booking_id}/decline")
def supplier_decline(booking_id: int, data: SupplierDecisionRequest, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("bookings.update_status", "update-bookings"))):
    return {"status": "success", "data": supplier_decline_booking(db, booking_id, data, current_user, request)}


@supplier_router.patch("/{booking_id}/complete")
def supplier_complete(booking_id: int, request: Request, data: SupplierDecisionRequest | None = None, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("bookings.update_status", "update-bookings"))):
    reason = (data.reason if data else None) or "Tour completed by supplier"
    return {"status": "success", "message": "Booking marked as completed", "data": supplier_complete_booking(db, booking_id, reason, current_user, request)}


@supplier_router.patch("/{booking_id}/cancel")
def supplier_cancel(booking_id: int, data: BookingCancelRequest, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("bookings.update_status", "update-bookings"))):
    return {"status": "success", "message": "Booking cancelled", "data": supplier_cancel_booking(db, booking_id, data.reason or "Cancelled by supplier", current_user, request)}


@supplier_router.patch("/{booking_id}/postpone")
def supplier_postpone(booking_id: int, data: SupplierPostponeRequest, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("bookings.update_status", "update-bookings"))):
    return {"status": "success", "message": "Booking postponed", "data": supplier_postpone_booking(db, booking_id, data.reason, data.new_tour_date, current_user, request)}


@supplier_router.post("/{booking_id}/notify")
def supplier_notify(booking_id: int, data: SupplierNotifyRequest, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("bookings.view", "view-bookings"))):
    return {"status": "success", "data": supplier_notify_parties(db, booking_id, data.message, data.notify_customer, data.notify_agent, current_user, request)}


@supplier_router.get("/{booking_id}/status-history")
def supplier_booking_history(booking_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("bookings.view", "view-bookings"))):
    return {"status": "success", "data": get_status_history(db, booking_id, current_user)}


def _serialize_portal_message(row: CustomerCommunication) -> dict:
    return {
        "id": row.id,
        "subject": row.subject,
        "message": row.message,
        "message_type": row.message_type,
        "email_status": row.email_status,
        "sender_name": row.sender.name if row.sender else None,
        "sender_role": row.message_type,
        "direction": "outbound",
        "created_at": row.created_at,
    }


@supplier_portal_router.get("/messages")
def supplier_messages(params: dict = Depends(pagination_params), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    q = db.query(CustomerCommunication).filter(
        CustomerCommunication.sent_by_user_id == current_user.id,
        CustomerCommunication.message_type == "supplier_message",
    ).order_by(CustomerCommunication.id.desc())
    total = q.count()
    rows = q.offset((params["page"] - 1) * params["limit"]).limit(params["limit"]).all()
    items = [_serialize_portal_message(r) for r in rows]
    return {"status": "success", "items": items, "data": items, "total": total, "page": params["page"], "limit": params["limit"]}


@supplier_portal_router.post("/messages")
def send_supplier_message(data: BookingCommunicationCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    row = CustomerCommunication(
        customer_id=None,
        subject=data.subject or "Supplier Support Request",
        message=data.message,
        sent_by_user_id=current_user.id,
        sent_to_email="admin",
        message_type="supplier_message",
        email_status="pending",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"status": "success", "message": "Message sent successfully", "data": _serialize_portal_message(row)}


@agent_portal_router.get("/messages")
def agent_messages(params: dict = Depends(pagination_params), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    q = db.query(CustomerCommunication).filter(
        CustomerCommunication.sent_by_user_id == current_user.id,
        CustomerCommunication.message_type == "agent_message",
    ).order_by(CustomerCommunication.id.desc())
    total = q.count()
    rows = q.offset((params["page"] - 1) * params["limit"]).limit(params["limit"]).all()
    items = [_serialize_portal_message(r) for r in rows]
    return {"status": "success", "items": items, "data": items, "total": total, "page": params["page"], "limit": params["limit"]}


@agent_portal_router.post("/messages")
def send_agent_message(data: BookingCommunicationCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    row = CustomerCommunication(
        customer_id=None,
        subject=data.subject or "Agent Support Request",
        message=data.message,
        sent_by_user_id=current_user.id,
        sent_to_email="admin",
        message_type="agent_message",
        email_status="pending",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"status": "success", "message": "Message sent successfully", "data": _serialize_portal_message(row)}


