from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.bookings import Booking
from app.schemas.bookings import BookingCreate
from app.services.bookings import calculate_booking_price, create_booking, get_booking_detail, get_bookings, serialize_booking
from app.auth.permissions import get_current_user
from app.utils.money import money
from app.utils.pagination import pagination_params
from app.models.cms import Tour
from app.models.customers import Customer, CustomerSavedTraveller, CustomerWishlistItem
from app.schemas.customers import (
    CustomerCancellationCreate,
    CustomerManualPaymentRequest,
    CustomerProfileUpdate,
    SavedTravellerRequest,
)
from app.models.cancellations import CancellationRequest
from app.schemas.cancellations import CancellationRequestCreate
from app.services import cancellations as cancellations_service
from app.services.customers import serialize_customer
from app.services import messaging as messaging_service
from app.services.invoices import list_invoices
from app.services.itinerary import download_itinerary_pdf
from app.schemas.payments import PaymentCreate
from app.services.payments import create_payment, get_customer_payments
from app.models.users import User
from app.auth.security import hash_password, verify_password
from app.schemas.profile import PasswordUpdate
from app.schemas.cms import slugify

router = APIRouter(prefix="/customer", tags=["Customer Portal"])
wishlist_router = APIRouter(prefix="/wishlist", tags=["Wishlist"])


class CustomerSendMessageBody(BaseModel):
    message: str = Field(min_length=1, max_length=5000)


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


def _serialize_wishlist_item(row: CustomerWishlistItem) -> dict:
    tour = row.tour
    country_name = tour.country.country_name if tour.country else ""
    country_slug = slugify(country_name or "worldwide")
    return {
        "id": tour.id,
        "wishlist_id": row.id,
        "user_id": row.user_id,
        "title": tour.title,
        "place": country_name or tour.start_location,
        "image": tour.banner_image,
        "price": tour.price_start_per_person,
        "currency": tour.currency,
        "duration": f"{tour.number_of_days} day{'s' if tour.number_of_days != 1 else ''}",
        "href": f"/tours/{country_slug}/{tour.slug}",
        "created_at": row.created_at,
    }


def _user_wishlist(db: Session, current_user: User) -> dict:
    rows = (
        db.query(CustomerWishlistItem)
        .join(Tour, Tour.id == CustomerWishlistItem.tour_id)
        .filter(CustomerWishlistItem.user_id == current_user.id, Tour.status == "published")
        .order_by(CustomerWishlistItem.id.desc())
        .all()
    )
    items = [_serialize_wishlist_item(row) for row in rows]
    return {"status": "success", "items": items, "total": len(items)}


def _add_user_wishlist_item(tour_id: int, db: Session, current_user: User) -> dict:
    tour = db.query(Tour).filter(Tour.id == tour_id, Tour.status == "published").first()
    if not tour:
        raise HTTPException(status_code=404, detail="Tour not found")

    row = db.query(CustomerWishlistItem).filter(
        CustomerWishlistItem.user_id == current_user.id,
        CustomerWishlistItem.tour_id == tour_id,
    ).first()
    if not row:
        row = CustomerWishlistItem(user_id=current_user.id, tour_id=tour_id)
        db.add(row)
        db.commit()
        db.refresh(row)

    return {"status": "success", "message": "Tour saved to wishlist", "data": _serialize_wishlist_item(row)}


def _delete_user_wishlist_item(tour_id: int, db: Session, current_user: User) -> dict:
    row = db.query(CustomerWishlistItem).filter(
        CustomerWishlistItem.user_id == current_user.id,
        CustomerWishlistItem.tour_id == tour_id,
    ).first()
    if row:
        db.delete(row)
        db.commit()
    return {"status": "success", "message": "Tour removed from wishlist"}


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


@router.get("/wishlist")
def customer_wishlist(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _current_customer(db, current_user)
    return _user_wishlist(db, current_user)


@router.post("/wishlist/{tour_id}")
def add_customer_wishlist_item(tour_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _current_customer(db, current_user)
    return _add_user_wishlist_item(tour_id, db, current_user)


@router.delete("/wishlist/{tour_id}")
def delete_customer_wishlist_item(tour_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _current_customer(db, current_user)
    return _delete_user_wishlist_item(tour_id, db, current_user)


@wishlist_router.get("")
def user_wishlist(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return _user_wishlist(db, current_user)


@wishlist_router.post("/{tour_id}")
def add_user_wishlist_item(tour_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return _add_user_wishlist_item(tour_id, db, current_user)


@wishlist_router.delete("/{tour_id}")
def delete_user_wishlist_item(tour_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return _delete_user_wishlist_item(tour_id, db, current_user)


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


@router.get("/bookings/{booking_id}/itinerary")
def customer_booking_itinerary(booking_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    fs_path, filename = download_itinerary_pdf(db, booking_id, current_user)
    return FileResponse(path=fs_path, filename=filename, media_type="application/pdf")


@router.post("/bookings/{booking_id}/cancel")
def request_booking_cancellation(booking_id: int, data: CustomerCancellationCreate, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    customer = _current_customer(db, current_user)
    booking = db.query(Booking).filter(Booking.id == booking_id, Booking.customer_id == customer.id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    existing = (
        db.query(CancellationRequest)
        .filter(CancellationRequest.booking_id == booking.id, CancellationRequest.status == "pending")
        .first()
    )
    if existing:
        return {"status": "success", "message": "Cancellation request already exists", "data": cancellations_service._serialize_request(existing)}

    result = cancellations_service.create_request(
        db,
        data=CancellationRequestCreate(booking_id=booking_id, reason=data.reason),
        actor=current_user,
        request=request,
    )
    return {"status": "success", "message": "Cancellation request submitted", "data": result}


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
    # Serve the actual PDF (not the invoice's JSON representation) - reuses
    # the same helper and access check as the admin/agent/supplier download
    # route in routers/invoices.py, so ownership is still enforced (a
    # customer can only download their own invoice).
    from app.services.invoices import download_invoice_pdf
    fs_path, filename = download_invoice_pdf(db, invoice_id, current_user)
    return FileResponse(path=fs_path, filename=filename, media_type="application/pdf")


@router.get("/messages")
async def customer_messages(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return {"status": "success", "data": messaging_service.get_own_conversation_thread(db, current_user)}


@router.post("/messages")
async def send_customer_portal_message(data: CustomerSendMessageBody, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    message = await messaging_service.send_message_as_participant(db, current_user, data.message)
    return {"status": "success", "message": "Message sent successfully", "data": message}


@router.get("/travellers")
def customer_saved_travellers(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    customer = _current_customer(db, current_user)
    rows = db.query(CustomerSavedTraveller).filter(CustomerSavedTraveller.customer_id == customer.id).order_by(CustomerSavedTraveller.id.desc()).all()
    items = [_serialize_saved_traveller(row) for row in rows]
    return {"status": "success", "items": items, "total": len(items)}


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
def customer_cancellations(params: dict = Depends(pagination_params), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    customer = _current_customer(db, current_user)
    return {"status": "success", **cancellations_service.list_requests(db, page=params["page"], limit=params["limit"], customer_id=customer.id)}


@router.post("/bookings/calculate-price")
def customer_calculate_price(payload: dict, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    customer = _current_customer(db, current_user)
    payload = {**payload, "customer_id": customer.id, "booking_source": "customer"}
    return {"status": "success", "data": calculate_booking_price(db, BookingCreate.model_validate(payload))}
