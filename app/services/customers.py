from datetime import datetime, timedelta

from app.utils.money import utcnow
from math import ceil

from fastapi import HTTPException, Request
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.services.audit import AuditLog, log_audit
from app.services.auth import build_password_reset_url
from app.config import settings
from app.utils.email_templates import base_email, esc, password_reset_email
from app.models.cms import City, Country
from app.models.customers import Customer, CustomerCommunication
from app.models.sessions import LoginHistory
from app.models.bookings import Booking
from app.models.payments import Payment
from app.schemas.customers import (
    CustomerBlockRequest,
    CustomerCreate,
    CustomerStatusUpdate,
    CustomerUpdate,
    SendCustomerMessageRequest,
)
from app.models.users import User
from app.auth.security import create_password_reset_token


def _split_name(full_name: str):
    parts = full_name.strip().split(None, 1)
    first_name = parts[0] if parts else ""
    last_name = parts[1] if len(parts) > 1 else ""
    return first_name, last_name


def _customer_code(customer_id: int):
    return str(customer_id)



def serialize_customer(customer: Customer, db: Session | None = None):
    summary = {
        "total_bookings": customer.total_bookings or 0,
        "completed_tours": customer.completed_bookings or 0,
        "cancelled_tours": customer.cancelled_bookings or 0,
        "upcoming_tours": customer.upcoming_bookings or 0,
        "amount_paid": float(customer.total_amount_paid or 0),
        "amount_pending": float(customer.total_amount_pending or 0),
    }
    country_name = customer.country_ref.country_name if customer.country_ref else customer.country
    city_name = customer.city_ref.city_name if customer.city_ref else customer.city
    state_name = customer.city_ref.state.state_name if customer.city_ref and customer.city_ref.state else customer.state
    return {
        "id": customer.id,
        "user_id": customer.user_id,
        "customer_code": customer.customer_code or _customer_code(customer.id),
        "customer_type": customer.customer_type,
        "agent_id": customer.agent_id,
        "first_name": customer.first_name,
        "last_name": customer.last_name,
        "full_name": customer.full_name,
        "email": customer.email,
        "phone": customer.phone,
        "phone_country_code": customer.phone_country_code,
        "date_of_birth": customer.date_of_birth,
        "gender": customer.gender,
        "nationality": customer.nationality,
        "passport_number": customer.passport_number,
        "passport_expiry": customer.passport_expiry,
        "frequent_flyer": customer.frequent_flyer,
        "preferred_airline": customer.preferred_airline,
        "emergency_name": customer.emergency_name,
        "emergency_relation": customer.emergency_relation,
        "emergency_phone": customer.emergency_phone,
        "emergency_email": customer.emergency_email,
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
        "country_name": country_name,
        "state_name": state_name,
        "city_name": city_name,
        "pincode": customer.pincode,
        "status": customer.status,
        "email_verified": customer.email_verified,
        "phone_verified": customer.phone_verified,
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
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": max(1, ceil(total / limit)) if total else 1,
    }


_UPCOMING_BOOKING_STATUSES = {"confirmed", "pending_supplier_acceptance", "payment_authorized"}
_CANCELLED_BOOKING_STATUSES = {"cancelled", "declined"}
# A cancellation in review is deliberately not payable: the customer must not
# be prompted to pay while Operations decides the request.  Once a request is
# rejected the booking returns to its previous payable lifecycle state.
_NON_PAYABLE_BOOKING_STATUSES = _CANCELLED_BOOKING_STATUSES | {"refunded", "cancellation_requested"}


def _live_customer_summaries(db: Session, customer_ids: list[int]) -> dict[int, dict]:
    """Build authoritative, lifetime booking totals for the customer list.

    The stored Customer fields are write-side caches. They cannot reliably
    include every booking channel or express balances in multiple currencies,
    so the admin list derives its financial display from booking snapshots.
    """
    if not customer_ids:
        return {}

    summaries: dict[int, dict] = {}
    rows = db.query(Booking).filter(Booking.customer_id.in_(customer_ids)).all()
    for booking in rows:
        if booking.customer_id is None:
            continue
        summary = summaries.setdefault(booking.customer_id, {
            "total_bookings": 0,
            "completed_tours": 0,
            "cancelled_tours": 0,
            "upcoming_tours": 0,
            "amounts_by_currency": {},
        })
        status = (booking.booking_status or "").lower()
        summary["total_bookings"] += 1
        if status == "completed":
            summary["completed_tours"] += 1
        elif status in _CANCELLED_BOOKING_STATUSES:
            summary["cancelled_tours"] += 1
        elif status in _UPCOMING_BOOKING_STATUSES:
            summary["upcoming_tours"] += 1

        currency = (booking.currency or "USD").upper()
        amounts = summary["amounts_by_currency"].setdefault(currency, {"currency": currency, "paid": 0.0, "pending": 0.0})
        amounts["paid"] += float(booking.amount_paid or 0)
        if status not in _NON_PAYABLE_BOOKING_STATUSES:
            amounts["pending"] += float(booking.amount_pending or 0)

    for summary in summaries.values():
        totals = sorted(summary.pop("amounts_by_currency").values(), key=lambda item: item["currency"])
        summary["amounts_by_currency"] = totals
        summary["has_mixed_currencies"] = len(totals) > 1
        if len(totals) == 1:
            summary["currency"] = totals[0]["currency"]
            summary["amount_paid"] = totals[0]["paid"]
            summary["amount_pending"] = totals[0]["pending"]
        else:
            summary["currency"] = None
            summary["amount_paid"] = 0.0
            summary["amount_pending"] = 0.0
    return summaries

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
    agent_id: int | None = None,
    agent_user_id: int | None = None,
):
    query = db.query(Customer).options(
        joinedload(Customer.country_ref),
        joinedload(Customer.city_ref).joinedload(City.state),
    )

    if agent_id:
        if agent_user_id:
            from app.models.agents import Agent
            from app.services.agent_scope import agent_customer_filter
            agent = db.query(Agent).filter(Agent.id == agent_id).first()
            query = query.filter(agent_customer_filter(db, agent, agent_user_id)) if agent else query.filter(Customer.id == -1)
        else:
            query = query.filter(
                Customer.id.in_(
                    db.query(Booking.customer_id).filter(Booking.agent_id == agent_id).distinct()
                )
            )

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
        country_value = country.strip()
        if country_value.isdigit():
            query = query.filter(Customer.country_id == int(country_value))
        else:
            query = query.filter(Customer.country.ilike(f"%{country_value}%"))

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

    # The UI calls this a booking date range, so never apply it to the
    # unrelated date on which the customer account was created.
    if start_date or end_date:
        booking_date_query = db.query(Booking.customer_id).filter(Booking.customer_id.isnot(None))
        if start_date:
            booking_date_query = booking_date_query.filter(Booking.created_at >= start_date)
        if end_date:
            booking_date_query = booking_date_query.filter(Booking.created_at <= f"{end_date} 23:59:59")
        query = query.filter(Customer.id.in_(booking_date_query.distinct()))

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
    live_summaries = _live_customer_summaries(db, [customer.id for customer in customers])
    items = []
    for customer in customers:
        item = serialize_customer(customer)
        summary = live_summaries.get(customer.id)
        if summary is not None:
            item.update(summary)
            item["total_bookings_count"] = summary["total_bookings"]
            item["completed_bookings"] = summary["completed_tours"]
            item["cancelled_bookings"] = summary["cancelled_tours"]
            item["upcoming_bookings"] = summary["upcoming_tours"]
            item["total_amount_paid"] = summary["amount_paid"]
            item["total_amount_pending"] = summary["amount_pending"]
        else:
            item.update({
                "total_bookings": 0,
                "completed_tours": 0,
                "cancelled_tours": 0,
                "upcoming_tours": 0,
                "amount_paid": 0.0,
                "amount_pending": 0.0,
                "currency": None,
                "amounts_by_currency": [],
                "has_mixed_currencies": False,
            })
        items.append(item)

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
        from app.models.bookings import Booking as BookingModel
        from app.models.payments import Payment as PaymentModel
        from app.services.bookings import serialize_booking
        from app.services.payments import serialize_payment

        live_summary = _live_customer_summaries(db, [customer_id]).get(customer_id)
        if live_summary:
            data.update(live_summary)
            data["total_amount_paid"] = data["amount_paid"]
            data["total_amount_pending"] = data["amount_pending"]

        recent_bookings = (
            db.query(BookingModel)
            .filter(BookingModel.customer_id == customer_id)
            .order_by(BookingModel.id.desc())
            .limit(10)
            .all()
        )
        recent_payments = (
            db.query(PaymentModel)
            .filter(PaymentModel.customer_id == customer_id)
            .order_by(PaymentModel.id.desc())
            .limit(10)
            .all()
        )
        serialized_bookings = [serialize_booking(db, b) for b in recent_bookings]
        serialized_payments = [serialize_payment(p) for p in recent_payments]
    except Exception:
        serialized_bookings = []
        serialized_payments = []

    latest_login = None
    if customer.user_id:
        latest_login = (
            db.query(LoginHistory)
            .filter(LoginHistory.user_id == customer.user_id)
            .filter(LoginHistory.status == "success")
            .order_by(LoginHistory.created_at.desc(), LoginHistory.id.desc())
            .first()
        )
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
            "last_login_at": latest_login.created_at if latest_login else None,
            "last_login_ip": latest_login.ip_address if latest_login else None,
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
    from app.services.agent_scope import get_actor_agent, is_agent_user
    added_by_agent = get_actor_agent(db, actor) if is_agent_user(actor) else None
    customer = Customer(
        customer_type="agent" if added_by_agent else "registered",
        agent_id=added_by_agent.id if added_by_agent else None,
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

    if data.emergency_email is not None:
        customer.emergency_email = str(data.emergency_email).strip().lower()

    if data.date_of_birth is not None:
        try:
            customer.date_of_birth = datetime.fromisoformat(data.date_of_birth.replace("Z", "+00:00")) if data.date_of_birth else None
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid date of birth") from exc

    if data.full_name is not None and (data.first_name is None or data.last_name is None):
        first_name, last_name = _split_name(data.full_name)
        if data.first_name is None:
            customer.first_name = first_name
        if data.last_name is None:
            customer.last_name = last_name

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
        "nationality",
        "passport_number",
        "passport_expiry",
        "frequent_flyer",
        "preferred_airline",
        "emergency_name",
        "emergency_relation",
        "emergency_phone",
        "gender",
    ]:
        value = getattr(data, field)
        if value is not None:
            setattr(customer, field, value.strip())

    for field in ["country_id", "city_id"]:
        value = getattr(data, field)
        if value is not None:
            setattr(customer, field, value)

    # The customer portal saves a human-readable Country. Keep the normalized
    # foreign key in sync so a stale legacy country_id cannot override the
    # just-saved value on the next profile load.
    if data.country is not None and data.country_id is None:
        country_name = data.country.strip()
        matched_country = (
            db.query(Country).filter(Country.country_name.ilike(country_name)).first()
            if country_name
            else None
        )
        customer.country_id = matched_country.id if matched_country else None

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
    customer.blocked_at = utcnow()
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
    user.reset_password_expires_at = utcnow() + timedelta(minutes=30)
    user.token_version += 1

    reset_url = build_password_reset_url(token)
    from app.services.notification_delivery import dispatch_lifecycle_email
    queued = dispatch_lifecycle_email(
        db, event="password_reset", entity_type="user", entity_id=user.id,
        recipient_type="customer", recipient_email=user.email, template_key="password_reset",
        values={"name": user.name, "email": user.email, "reset_url": reset_url, "button_text": "Reset Password", "button_url": reset_url},
        fallback_subject="Reset your Tourvaa password",
        fallback_html=password_reset_email(user.name, reset_url),
        event_version=token_hash,
    )
    email_status = "queued" if queued else "duplicate"

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
    from app.services.bookings import get_customer_bookings
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
    actor: User | None = None,
):
    from app.services.payments import get_customer_payments
    return get_customer_payments(
        db,
        customer_id=customer_id,
        page=page,
        limit=limit,
        payment_status=payment_status,
        payment_method=payment_method,
        actor=actor,
        hide_identifiers=False,
    )


def get_customer_communication_history(db: Session, customer_id: int, page: int = 1, limit: int = 100):
    items = (
        db.query(CustomerCommunication)
        .filter(CustomerCommunication.customer_id == customer_id)
        .order_by(CustomerCommunication.id.desc())
        .all()
    )
    serialized = [serialize_communication(item) for item in items]

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

    from app.services.notification_delivery import dispatch_lifecycle_email
    portal_url = f"{settings.FRONTEND_URL.rstrip('/')}/customer/support"
    queued = dispatch_lifecycle_email(
        db, event="customer_communication", entity_type="customer_communication", entity_id=message.id,
        recipient_type="customer", recipient_email=customer.email, template_key="customer_communication",
        values={
            "name": customer.full_name or customer.first_name or "Customer",
            "sender_name": actor.name if actor else "Tourvaa Admin",
            "login_url": portal_url,
            "button_text": "View message",
            "button_url": portal_url,
        },
        fallback_subject=data.subject,
        fallback_html=base_email(
            data.subject,
            f"Hi {esc(customer.full_name or customer.first_name or 'Customer')},",
            f"<p>You have a new message from {esc(actor.name if actor else 'Tourvaa Admin')}.</p><p>Open the secure portal to read and reply to it.</p>",
            "View message",
            portal_url,
        ),
    )
    message.email_status = "queued" if queued else "duplicate"

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
