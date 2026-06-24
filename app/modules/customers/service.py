from datetime import datetime, timedelta
from math import ceil

from fastapi import HTTPException, Request
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.modules.audit.service import log_audit
from app.modules.auth.service import build_password_reset_url
from app.modules.common.email_templates import password_reset_email
from app.modules.common.mailer import send_email
from app.modules.customers.models import Customer, CustomerCommunication
from app.modules.bookings.models import Booking
from app.modules.payments.models import Payment
from app.modules.customers.schemas import (
    CustomerBlockRequest,
    CustomerCreate,
    CustomerStatusUpdate,
    CustomerUpdate,
    SendCustomerMessageRequest,
)
from app.modules.users.models import User
from app.security import create_password_reset_token


def _split_name(full_name: str):
    parts = full_name.strip().split(None, 1)
    first_name = parts[0] if parts else ""
    last_name = parts[1] if len(parts) > 1 else ""
    return first_name, last_name


def _customer_code(customer_id: int):
    return f"TVA-CUS-{customer_id:05d}"



def serialize_customer(customer: Customer, db: Session | None = None):
    summary = {
        "total_bookings": customer.total_bookings or 0,
        "completed_tours": customer.completed_bookings or 0,
        "cancelled_tours": customer.cancelled_bookings or 0,
        "upcoming_tours": customer.upcoming_bookings or 0,
        "amount_paid": float(customer.total_amount_paid or 0),
        "amount_pending": float(customer.total_amount_pending or 0),
    }
    return {
        "id": customer.id,
        "user_id": customer.user_id,
        "customer_code": customer.customer_code or _customer_code(customer.id),
        "first_name": customer.first_name,
        "last_name": customer.last_name,
        "full_name": customer.full_name,
        "email": customer.email,
        "phone": customer.phone,
        "country_id": customer.country_id,
        "city_id": customer.city_id,
        "address_line_1": customer.address_line_1,
        "address_line_2": customer.address_line_2,
        "postal_code": customer.postal_code,
        "address": customer.address,
        "profile_image": customer.profile_image,
        "country": customer.country,
        "state": customer.state,
        "city": customer.city,
        "pincode": customer.pincode,
        "status": customer.status,
        "is_blocked": customer.is_blocked,
        "blocked_reason": customer.blocked_reason,
        "blocked_at": customer.blocked_at,
        "blocked_by": customer.blocked_by,
        "created_at": customer.created_at,
        "updated_at": customer.updated_at,
        "total_bookings_count": customer.total_bookings,
        "completed_bookings": customer.completed_bookings,
        "cancelled_bookings": customer.cancelled_bookings,
        "upcoming_bookings": customer.upcoming_bookings,
        "total_amount_paid": float(customer.total_amount_paid or 0),
        "total_amount_pending": float(customer.total_amount_pending or 0),
        **summary,
    }


def _paginate(items: list, page: int = 1, limit: int = 20) -> dict:
    page = max(1, int(page or 1))
    limit = max(1, int(limit or 20))
    total = len(items)
    start = (page - 1) * limit
    end = start + limit
    return {
        "items": items[start:end],
        "data": items[start:end],
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": max(1, ceil(total / limit)) if total else 1,
    }

def serialize_communication(item: CustomerCommunication):
    return {
        "id": item.id,
        "customer_id": item.customer_id,
        "booking_id": item.booking_id,
        "subject": item.subject,
        "message": item.message,
        "sent_by_user_id": item.sent_by_user_id,
        "sent_to_email": item.sent_to_email,
        "message_type": item.message_type,
        "email_status": item.email_status,
        "created_at": item.created_at,
    }


def get_customers(
    db: Session,
    page: int,
    limit: int,
    search: str = "",
    country: str = "",
    status: str = "",
    payment_status: str = "",
    booking_status: str = "",
    start_date: str = "",
    end_date: str = "",
    sort_by: str = "newest",
    sort_order: str = "desc",
):
    query = db.query(Customer)

    if search:
        pattern = f"%{search.strip().lower()}%"
        query = query.filter(
            or_(
                Customer.customer_code.ilike(pattern),
                Customer.full_name.ilike(pattern),
                Customer.email.ilike(pattern),
                Customer.phone.ilike(pattern),
            )
        )

    if country:
        query = query.filter(Customer.country.ilike(f"%{country.strip()}%"))

    if status:
        query = query.filter(Customer.status == status.strip().lower())

    if booking_status:
        query = query.filter(
            Customer.id.in_(
                db.query(Booking.customer_id).filter(Booking.booking_status == booking_status.strip().lower())
            )
        )

    if payment_status:
        query = query.filter(
            Customer.id.in_(
                db.query(Payment.customer_id).filter(Payment.payment_status == payment_status.strip().lower())
            )
        )

    if start_date:
        query = query.filter(Customer.created_at >= start_date)

    if end_date:
        query = query.filter(Customer.created_at <= f"{end_date} 23:59:59")

    sort_key = sort_by.strip().lower()
    direction_desc = sort_order.strip().lower() != "asc"

    if sort_key in {"oldest"}:
        query = query.order_by(Customer.id.asc())
    elif sort_key in {"name", "name_az"}:
        query = query.order_by(Customer.full_name.desc() if direction_desc else Customer.full_name.asc())
    else:
        query = query.order_by(Customer.id.desc())

    total = query.count()
    customers = query.offset((page - 1) * limit).limit(limit).all()
    items = [serialize_customer(customer) for customer in customers]

    if sort_key == "highest_amount_paid":
        items.sort(key=lambda item: item["amount_paid"], reverse=direction_desc)
    elif sort_key == "highest_pending_amount":
        items.sort(key=lambda item: item["amount_pending"], reverse=direction_desc)

    return {
        "items": items,
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": max(1, (total + limit - 1) // limit),
    }


def get_customer_by_id(db: Session, customer_id: int):
    customer = db.query(Customer).filter(Customer.id == customer_id).first()

    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    return customer


def get_customer_detail(db: Session, customer_id: int, actor: User | None = None, request: Request | None = None):
    customer = get_customer_by_id(db, customer_id)
    data = serialize_customer(customer)

    # Try to enrich with live booking/payment data if tables exist
    try:
        from app.modules.bookings.models import Booking as BookingModel
        from app.modules.payments.models import Payment as PaymentModel
        from app.modules.bookings.service import serialize_booking
        from app.modules.payments.service import serialize_payment
        from sqlalchemy import func as sqlfunc

        recent_bookings = (
            db.query(BookingModel)
            .filter(BookingModel.customer_id == customer_id)
            .order_by(BookingModel.id.desc())
            .limit(3)
            .all()
        )
        recent_payments = (
            db.query(PaymentModel)
            .filter(PaymentModel.customer_id == customer_id)
            .order_by(PaymentModel.id.desc())
            .limit(3)
            .all()
        )
        live = _history_summary_from_db(db, customer_id)
        data.update(live)
        serialized_bookings = [serialize_booking(b) for b in recent_bookings]
        serialized_payments = [serialize_payment(p) for p in recent_payments]
    except Exception:
        serialized_bookings = []
        serialized_payments = []

    data.update(
        {
            "booking_summary": {
                "total": data["total_bookings"],
                "completed": data["completed_tours"],
                "cancelled": data["cancelled_tours"],
                "upcoming": data["upcoming_tours"],
            },
            "payment_summary": {
                "paid": data["amount_paid"],
                "pending": data["amount_pending"],
            },
            "recent_bookings": serialized_bookings,
            "recent_payments": serialized_payments,
            "last_login_at": None,
        }
    )
    log_audit(
        db,
        actor=actor,
        action="view_customer",
        entity_type="customer",
        entity_id=customer.id,
        request=request,
    )
    db.commit()
    return data


def create_customer(
    db: Session,
    data: CustomerCreate,
    actor: User | None = None,
    request: Request | None = None,
):
    email = str(data.email).strip().lower()
    existing = db.query(Customer).filter(Customer.email == email).first()

    if existing:
        raise HTTPException(status_code=400, detail="Customer email already exists")

    first_name = (data.first_name or "").strip()
    last_name = (data.last_name or "").strip()
    if not first_name:
        first_name, derived_last_name = _split_name(data.full_name)
        last_name = last_name or derived_last_name

    linked_user = db.query(User).filter(User.email == email).first()
    customer = Customer(
        user_id=linked_user.id if linked_user else None,
        first_name=first_name,
        last_name=last_name,
        full_name=data.full_name.strip(),
        email=email,
        phone=data.phone.strip(),
        country_id=data.country_id,
        city_id=data.city_id,
        address_line_1=data.address_line_1.strip(),
        address_line_2=data.address_line_2.strip(),
        postal_code=data.postal_code.strip(),
        address=data.address.strip(),
        profile_image=data.profile_image.strip(),
        country=data.country.strip(),
        state=data.state.strip(),
        city=data.city.strip(),
        pincode=data.pincode.strip(),
        status=data.status,
        is_blocked=data.status == "blocked",
    )
    db.add(customer)
    db.flush()
    customer.customer_code = _customer_code(customer.id)

    log_audit(
        db,
        actor=actor,
        action="create_customer",
        entity_type="customer",
        entity_id=customer.id,
        new_values=serialize_customer(customer),
        request=request,
    )
    db.commit()
    db.refresh(customer)
    return serialize_customer(customer)


def update_customer(
    db: Session,
    customer_id: int,
    data: CustomerUpdate,
    actor: User | None = None,
    request: Request | None = None,
):
    customer = get_customer_by_id(db, customer_id)
    old_values = serialize_customer(customer)

    if data.email is not None:
        email = str(data.email).strip().lower()
        existing = (
            db.query(Customer)
            .filter(Customer.email == email, Customer.id != customer_id)
            .first()
        )
        if existing:
            raise HTTPException(status_code=400, detail="Customer email already exists")
        customer.email = email

    for field in [
        "first_name",
        "last_name",
        "full_name",
        "phone",
        "address_line_1",
        "address_line_2",
        "postal_code",
        "address",
        "profile_image",
        "country",
        "state",
        "city",
        "pincode",
    ]:
        value = getattr(data, field)
        if value is not None:
            setattr(customer, field, value.strip())

    for field in ["country_id", "city_id"]:
        value = getattr(data, field)
        if value is not None:
            setattr(customer, field, value)

    log_audit(
        db,
        actor=actor,
        action="update_customer",
        entity_type="customer",
        entity_id=customer.id,
        old_values=old_values,
        new_values=serialize_customer(customer),
        request=request,
    )
    db.commit()
    db.refresh(customer)
    return serialize_customer(customer)


def update_customer_status(
    db: Session,
    customer_id: int,
    data: CustomerStatusUpdate,
    actor: User | None = None,
    request: Request | None = None,
):
    customer = get_customer_by_id(db, customer_id)
    old_values = serialize_customer(customer)
    customer.status = data.status
    customer.is_blocked = data.status == "blocked"

    if customer.user:
        customer.user.is_active = data.status == "active"
        customer.user.token_version += 1

    log_audit(
        db,
        actor=actor,
        action="update_customer_status",
        entity_type="customer",
        entity_id=customer.id,
        old_values=old_values,
        new_values=serialize_customer(customer),
        request=request,
    )
    db.commit()
    db.refresh(customer)
    return serialize_customer(customer)


def block_customer(
    db: Session,
    customer_id: int,
    data: CustomerBlockRequest,
    actor: User | None = None,
    request: Request | None = None,
):
    customer = get_customer_by_id(db, customer_id)
    old_values = serialize_customer(customer)
    customer.status = "blocked"
    customer.is_blocked = True
    customer.blocked_reason = data.reason
    customer.blocked_at = datetime.utcnow()
    customer.blocked_by = actor.id if actor else None

    if customer.user:
        customer.user.is_active = False
        customer.user.token_version += 1

    log_audit(
        db,
        actor=actor,
        action="block_customer",
        entity_type="customer",
        entity_id=customer.id,
        old_values=old_values,
        new_values=serialize_customer(customer),
        request=request,
    )
    db.commit()
    db.refresh(customer)
    return serialize_customer(customer)


def unblock_customer(db: Session, customer_id: int, actor: User | None = None, request: Request | None = None):
    customer = get_customer_by_id(db, customer_id)
    old_values = serialize_customer(customer)
    customer.status = "active"
    customer.is_blocked = False
    customer.blocked_reason = None
    customer.blocked_at = None
    customer.blocked_by = None

    if customer.user:
        customer.user.is_active = True
        customer.user.token_version += 1

    log_audit(
        db,
        actor=actor,
        action="unblock_customer",
        entity_type="customer",
        entity_id=customer.id,
        old_values=old_values,
        new_values=serialize_customer(customer),
        request=request,
    )
    db.commit()
    db.refresh(customer)
    return serialize_customer(customer)


def reset_customer_password(
    db: Session,
    customer_id: int,
    actor: User | None = None,
    request: Request | None = None,
):
    customer = get_customer_by_id(db, customer_id)
    user = customer.user or db.query(User).filter(User.email == customer.email).first()

    if not user:
        raise HTTPException(status_code=400, detail="Customer does not have a login account")

    token, token_hash = create_password_reset_token()
    user.reset_password_token = token_hash
    user.reset_password_expires_at = datetime.utcnow() + timedelta(minutes=30)
    user.token_version += 1

    reset_url = build_password_reset_url(token)
    email_status = "pending"
    try:
        send_email(
            user.email,
            "Reset your Tourvaa password",
            password_reset_email(user.name, reset_url),
        )
        email_status = "sent"
    except Exception:
        email_status = "failed"

    log_audit(
        db,
        actor=actor,
        action="reset_customer_password",
        entity_type="customer",
        entity_id=customer.id,
        new_values={"email": customer.email, "email_status": email_status},
        request=request,
    )
    db.commit()
    return serialize_customer(customer)


def get_customer_booking_history(
    db: Session,
    customer_id: int,
    page: int = 1,
    limit: int = 100,
    booking_status: str = "",
    payment_status: str = "",
):
    from app.modules.bookings.service import get_customer_bookings
    return get_customer_bookings(
        db,
        customer_id=customer_id,
        page=page,
        limit=limit,
        booking_status=booking_status,
        payment_status=payment_status,
    )


def get_customer_payment_history(
    db: Session,
    customer_id: int,
    page: int = 1,
    limit: int = 100,
    payment_status: str = "",
    payment_method: str = "",
):
    from app.modules.payments.service import get_customer_payments
    return get_customer_payments(
        db,
        customer_id=customer_id,
        page=page,
        limit=limit,
        payment_status=payment_status,
        payment_method=payment_method,
    )


def get_customer_communication_history(db: Session, customer_id: int, page: int = 1, limit: int = 100):
    items = (
        db.query(CustomerCommunication)
        .filter(CustomerCommunication.customer_id == customer_id)
        .order_by(CustomerCommunication.id.desc())
        .all()
    )
    serialized = [serialize_communication(item) for item in items]

    if not serialized:
        serialized = [
            {
                "id": 1,
                "customer_id": customer_id,
                "booking_id": 1,
                "subject": "Booking confirmation sent",
                "message": "Your booking confirmation has been sent to your registered email.",
                "sent_by_user_id": None,
                "sent_to_email": "",
                "message_type": "system_notification",
                "email_status": "sent",
                "created_at": None,
            }
        ]

    return _paginate(serialized, page, limit)


def send_customer_message(
    db: Session,
    customer_id: int,
    data: SendCustomerMessageRequest,
    actor: User | None = None,
    request: Request | None = None,
):
    customer = get_customer_by_id(db, customer_id)
    message = CustomerCommunication(
        customer_id=customer.id,
        booking_id=data.booking_id,
        subject=data.subject,
        message=data.message,
        sent_by_user_id=actor.id if actor else None,
        sent_to_email=customer.email,
        message_type=data.message_type,
        email_status="pending",
    )
    db.add(message)
    db.flush()

    try:
        send_email(customer.email, data.subject, data.message)
        message.email_status = "sent"
    except Exception:
        message.email_status = "failed"

    log_audit(
        db,
        actor=actor,
        action="send_customer_message",
        entity_type="customer",
        entity_id=customer.id,
        new_values=serialize_communication(message),
        request=request,
    )
    db.commit()
    db.refresh(message)
    return serialize_communication(message)
