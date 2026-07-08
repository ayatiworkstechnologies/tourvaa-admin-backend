from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.bookings import Booking, BookingStatusHistory
from app.schemas.bookings import BookingCreate
from app.services.bookings import calculate_booking_price, create_booking, get_booking_detail, get_bookings, serialize_booking
from app.auth.permissions import get_current_user
from app.utils.money import money
from app.utils.pagination import pagination_params
from app.models.customers import Customer, CustomerCancellationRequest, CustomerCommunication, CustomerSavedTraveller
from app.schemas.customers import (
    CustomerCancellationCreate,
    CustomerManualPaymentRequest,
    CustomerMessageCreate,
    CustomerProfileUpdate,
    SavedTravellerRequest,
)
from app.services.customers import serialize_customer, serialize_communication
from app.services.invoices import list_invoices
from app.schemas.payments import PaymentCreate
from app.services.payments import create_payment, get_customer_payments
from app.models.users import User
from app.auth.security import hash_password, verify_password
from app.schemas.profile import PasswordUpdate

router = APIRouter(prefix="/customer", tags=["Customer Portal"])


def _current_customer(db: Session, current_user: User) -> Customer:
    customer = db.query(Customer).filter(Customer.user_id == current_user.id).first()
    if not customer:
        customer = db.query(Customer).filter(Customer.email == current_user.email).first()
        if customer:
            customer.user_id = current_user.id
            db.commit()
            db.refresh(customer)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer profile not found")
    if customer.is_blocked or customer.status in {"blocked", "suspended", "deleted"}:
        raise HTTPException(status_code=403, detail="Customer account is not active")
    return customer


def _parse_optional_dt(value: str | None):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format")


def _serialize_saved_traveller(row: CustomerSavedTraveller) -> dict:
    return {
        "id": row.id,
        "customer_id": row.customer_id,
        "traveller_name": row.traveller_name,
        "email": row.email,
        "phone": row.phone,
        "traveller_type": row.traveller_type,
        "age": row.age,
        "gender": row.gender,
        "passport_number": row.passport_number,
        "allergies": row.allergies,
        "special_notes": row.special_notes,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _serialize_cancellation(row: CustomerCancellationRequest) -> dict:
    return {
        "id": row.id,
        "customer_id": row.customer_id,
        "booking_id": row.booking_id,
        "booking_code": row.booking.booking_code if row.booking else None,
        "tour_name": row.booking.tour_name if row.booking else None,
        "reason": row.reason,
        "status": row.status,
        "admin_notes": row.admin_notes,
        "reviewed_by": row.reviewed_by,
        "reviewed_at": row.reviewed_at,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


@router.get("/profile")
def customer_profile(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    customer = _current_customer(db, current_user)
    data = serialize_customer(customer)
    data.update({
        "email_verified": bool(customer.email_verified or current_user.email_verified_at),
        "phone_verified": bool(customer.phone_verified),
    })
    return {"status": "success", "data": data}


@router.put("/profile")
def update_customer_profile(data: CustomerProfileUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    customer = _current_customer(db, current_user)
    payload = data.model_dump(exclude_unset=True)
    if "date_of_birth" in payload:
        payload["date_of_birth"] = _parse_optional_dt(payload["date_of_birth"])
    for field, value in payload.items():
        if hasattr(customer, field):
            setattr(customer, field, value)
    if not customer.full_name:
        customer.full_name = f"{customer.first_name} {customer.last_name}".strip() or current_user.name
    current_user.name = customer.full_name
    current_user.phone = customer.phone
    current_user.profile_image = customer.profile_image
    current_user.address = customer.address or customer.address_line_1
    current_user.country = customer.country
    current_user.state = customer.state
    current_user.city = customer.city
    current_user.pincode = customer.pincode or customer.postal_code
    db.commit()
    db.refresh(customer)
    return {"status": "success", "message": "Profile updated successfully", "data": serialize_customer(customer)}


@router.post("/change-password")
def change_customer_password(data: PasswordUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _current_customer(db, current_user)
    if not verify_password(data.current_password, current_user.password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    if data.current_password == data.new_password:
        raise HTTPException(status_code=400, detail="New password must be different from current password")
    current_user.password = hash_password(data.new_password)
    current_user.token_version += 1
    db.commit()
    return {"status": "success", "message": "Password updated successfully"}


@router.get("/bookings")
def customer_bookings(params: dict = Depends(pagination_params), booking_status: str = Query(default=""), payment_status: str = Query(default=""), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    customer = _current_customer(db, current_user)
    return {"status": "success", **get_bookings(db, page=params["page"], limit=params["limit"], search=params["search"], customer_id=customer.id, booking_status=booking_status, payment_status=payment_status, actor=current_user)}


@router.post("/bookings")
def create_customer_booking(payload: dict, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    customer = _current_customer(db, current_user)
    payload = {**payload, "customer_id": customer.id, "booking_source": "customer"}
    data = BookingCreate.model_validate(payload)
    return {"status": "success", "message": "Booking created successfully", "data": create_booking(db, data, actor=current_user, request=request)}


@router.get("/bookings/{booking_id}")
def customer_booking_detail(booking_id: int, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _current_customer(db, current_user)
    return {"status": "success", "data": get_booking_detail(db, booking_id, actor=current_user, request=request)}


@router.post("/bookings/{booking_id}/cancel")
def request_booking_cancellation(booking_id: int, data: CustomerCancellationCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    customer = _current_customer(db, current_user)
    booking = db.query(Booking).filter(Booking.id == booking_id, Booking.customer_id == customer.id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    if booking.booking_status in {"cancelled", "completed", "refunded"}:
        raise HTTPException(status_code=400, detail="This booking cannot be cancelled")
    existing = db.query(CustomerCancellationRequest).filter(CustomerCancellationRequest.booking_id == booking.id, CustomerCancellationRequest.status.in_(["requested", "under_review", "refund_processing"])).first()
    if existing:
        return {"status": "success", "message": "Cancellation request already exists", "data": _serialize_cancellation(existing)}
    row = CustomerCancellationRequest(customer_id=customer.id, booking_id=booking.id, reason=data.reason, status="requested")
    booking.cancellation_reason = data.reason
    db.add(row)
    db.add(BookingStatusHistory(booking_id=booking.id, old_status=booking.booking_status, new_status="cancellation_requested", changed_by_user_id=current_user.id, change_source="customer", reason=data.reason, metadata_json={"cancellation_status": "requested"}))
    db.commit()
    db.refresh(row)
    return {"status": "success", "message": "Cancellation request submitted", "data": _serialize_cancellation(row)}


@router.post("/bookings/{booking_id}/pay")
def record_customer_manual_payment(booking_id: int, data: CustomerManualPaymentRequest, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    customer = _current_customer(db, current_user)
    booking = db.query(Booking).filter(Booking.id == booking_id, Booking.customer_id == customer.id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    if money(booking.amount_pending) <= 0:
        return {"status": "success", "message": "Booking is already paid", "data": serialize_booking(booking, detail=True)}
    payment = create_payment(db, PaymentCreate(booking_id=booking.id, customer_id=customer.id, payment_method=data.payment_method, payment_type=booking.payment_type or "full", total_amount=money(booking.final_amount), paid_amount=money(booking.amount_pending), gateway=data.gateway, transaction_id=data.transaction_id, notes="Customer checkout payment"), actor=current_user, request=request)
    db.refresh(booking)
    return {"status": "success", "message": "Payment recorded successfully", "data": {"payment": payment, "booking": serialize_booking(booking, detail=True)}}


@router.get("/payments")
def customer_payments(params: dict = Depends(pagination_params), payment_status: str = Query(default=""), payment_method: str = Query(default=""), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    customer = _current_customer(db, current_user)
    return {"status": "success", **get_customer_payments(db, customer.id, page=params["page"], limit=params["limit"], payment_status=payment_status, payment_method=payment_method)}


@router.get("/invoices")
def customer_invoices(params: dict = Depends(pagination_params), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    customer = _current_customer(db, current_user)
    return {"status": "success", **list_invoices(db, page=params["page"], limit=params["limit"], customer_id=customer.id)}


@router.get("/invoices/{invoice_id}/download")
def customer_invoice_download(invoice_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    customer = _current_customer(db, current_user)
    result = list_invoices(db, page=1, limit=1, customer_id=customer.id)
    invoice = next((item for item in result["items"] if item["id"] == invoice_id), None)
    if not invoice:
        from app.models.invoices import Invoice
        inv = db.query(Invoice).filter(Invoice.id == invoice_id, Invoice.customer_id == customer.id).first()
        if not inv:
            raise HTTPException(status_code=404, detail="Invoice not found")
        from app.services.invoices import serialize_invoice
        invoice = serialize_invoice(inv, detail=True)
    return {"status": "success", "data": invoice}


@router.get("/messages")
def customer_messages(params: dict = Depends(pagination_params), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    customer = _current_customer(db, current_user)
    query = db.query(CustomerCommunication).filter(CustomerCommunication.customer_id == customer.id).order_by(CustomerCommunication.id.desc())
    total = query.count()
    rows = query.offset((params["page"] - 1) * params["limit"]).limit(params["limit"]).all()
    items = [serialize_communication(row) for row in rows]
    return {"status": "success", "items": items, "data": items, "total": total, "page": params["page"], "limit": params["limit"], "total_pages": max(1, (total + params["limit"] - 1) // params["limit"])}


@router.post("/messages")
def send_customer_portal_message(data: CustomerMessageCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    customer = _current_customer(db, current_user)
    if data.booking_id:
        booking = db.query(Booking).filter(Booking.id == data.booking_id, Booking.customer_id == customer.id).first()
        if not booking:
            raise HTTPException(status_code=404, detail="Booking not found")
    row = CustomerCommunication(customer_id=customer.id, booking_id=data.booking_id, subject=data.subject, message=data.message, sent_by_user_id=current_user.id, sent_to_email="admin", message_type="customer_reply", email_status="pending")
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"status": "success", "message": "Message sent successfully", "data": serialize_communication(row)}


@router.get("/travellers")
def customer_saved_travellers(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    customer = _current_customer(db, current_user)
    rows = db.query(CustomerSavedTraveller).filter(CustomerSavedTraveller.customer_id == customer.id).order_by(CustomerSavedTraveller.id.desc()).all()
    items = [_serialize_saved_traveller(row) for row in rows]
    return {"status": "success", "items": items, "data": items, "total": len(items)}


@router.post("/travellers")
def add_saved_traveller(data: SavedTravellerRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    customer = _current_customer(db, current_user)
    row = CustomerSavedTraveller(customer_id=customer.id, **data.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"status": "success", "message": "Traveller saved", "data": _serialize_saved_traveller(row)}


@router.put("/travellers/{traveller_id}")
def update_saved_traveller(traveller_id: int, data: SavedTravellerRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    customer = _current_customer(db, current_user)
    row = db.query(CustomerSavedTraveller).filter(CustomerSavedTraveller.id == traveller_id, CustomerSavedTraveller.customer_id == customer.id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Traveller not found")
    for field, value in data.model_dump().items():
        setattr(row, field, value)
    db.commit()
    db.refresh(row)
    return {"status": "success", "message": "Traveller updated", "data": _serialize_saved_traveller(row)}


@router.delete("/travellers/{traveller_id}")
def delete_saved_traveller(traveller_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    customer = _current_customer(db, current_user)
    row = db.query(CustomerSavedTraveller).filter(CustomerSavedTraveller.id == traveller_id, CustomerSavedTraveller.customer_id == customer.id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Traveller not found")
    db.delete(row)
    db.commit()
    return {"status": "success", "message": "Traveller deleted"}


@router.get("/cancellations")
def customer_cancellations(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    customer = _current_customer(db, current_user)
    rows = db.query(CustomerCancellationRequest).filter(CustomerCancellationRequest.customer_id == customer.id).order_by(CustomerCancellationRequest.id.desc()).all()
    items = [_serialize_cancellation(row) for row in rows]
    return {"status": "success", "items": items, "data": items, "total": len(items)}


@router.post("/bookings/calculate-price")
def customer_calculate_price(payload: dict, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    customer = _current_customer(db, current_user)
    payload = {**payload, "customer_id": customer.id, "booking_source": "customer"}
    return {"status": "success", "data": calculate_booking_price(db, BookingCreate.model_validate(payload))}
