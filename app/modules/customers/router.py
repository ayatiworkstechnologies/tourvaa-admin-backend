from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.modules.common.auth import get_current_user, require_any_permission
from app.modules.common.pagination import pagination_params
from app.modules.customers.schemas import (
    CustomerBlockRequest,
    CustomerCreate,
    CustomerStatusUpdate,
    CustomerUpdate,
    CustomerProfileUpdate,
    SendCustomerMessageRequest,
)
from app.modules.bookings.schemas import BookingCreate
from app.modules.bookings.service import create_booking
from app.modules.customers.models import Customer
from app.modules.customers.service import (
    block_customer,
    create_customer,
    get_customer_booking_history,
    get_customer_communication_history,
    get_customer_detail,
    get_customer_payment_history,
    get_customers,
    reset_customer_password,
    send_customer_message,
    serialize_customer,
    unblock_customer,
    update_customer,
    update_customer_status,
)
from app.modules.users.models import User

router = APIRouter(prefix="/customers", tags=["Customers"])


@router.get("")
@router.get("/")
def list_customers(
    params: dict = Depends(pagination_params),
    country: str = Query(default=""),
    country_id: str = Query(default=""),
    status: str = Query(default=""),
    payment_status: str = Query(default=""),
    booking_status: str = Query(default=""),
    start_date: str = Query(default=""),
    end_date: str = Query(default=""),
    sort_by: str = Query(default="newest"),
    sort_order: str = Query(default="desc"),
    agent_id: str = Query(default=""),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_permission("customers.view", "view-customers")),
):
    # If the caller is an agent, auto-scope to their customers only
    effective_agent_id: int | None = None
    role_slug = (current_user.role.slug if current_user.role else "") or ""
    if "agent" in role_slug.lower():
        from app.modules.agents.models import Agent
        agent = db.query(Agent).filter(Agent.user_id == current_user.id).first()
        if agent:
            effective_agent_id = agent.id
    elif agent_id:
        effective_agent_id = int(agent_id)

    paginated = get_customers(
        db,
        page=params["page"],
        limit=params["limit"],
        search=params["search"],
        country=country or country_id,
        status=status,
        payment_status=payment_status,
        booking_status=booking_status,
        start_date=start_date,
        end_date=end_date,
        sort_by=sort_by,
        sort_order=sort_order,
        agent_id=effective_agent_id,
    )
    return {"status": "success", "data": paginated["items"], **paginated}


@router.post("/")
def add_customer(
    data: CustomerCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_permission("customers.create", "create-customers")),
):
    return {
        "status": "success",
        "message": "Customer created successfully",
        "data": create_customer(db, data, actor=current_user, request=request),
    }


@router.get("/me")
def my_customer(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    customer = db.query(Customer).filter(Customer.user_id == current_user.id).first()
    if not customer:
        customer = db.query(Customer).filter(Customer.email == current_user.email).first()
        if customer:
            customer.user_id = current_user.id
            db.commit()
            db.refresh(customer)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer profile not found")
    return {"status": "success", "data": serialize_customer(customer)}


@router.put("/me")
@router.patch("/me")
def edit_my_customer(data: CustomerProfileUpdate, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    customer = db.query(Customer).filter(Customer.user_id == current_user.id).first()
    if not customer:
        customer = db.query(Customer).filter(Customer.email == current_user.email).first()
        if customer:
            customer.user_id = current_user.id
            db.commit()
            db.refresh(customer)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer profile not found")
    update_data = CustomerUpdate(**data.model_dump(exclude_unset=True))
    updated = update_customer(db, customer.id, update_data, actor=current_user, request=request)
    current_user.name = updated.get("full_name") or current_user.name
    current_user.phone = updated.get("phone") or current_user.phone
    current_user.profile_image = updated.get("profile_image") or current_user.profile_image
    current_user.address = updated.get("address") or updated.get("address_line_1") or current_user.address
    current_user.country = updated.get("country_name") or updated.get("country") or current_user.country
    current_user.state = updated.get("state_name") or updated.get("state") or current_user.state
    current_user.city = updated.get("city_name") or updated.get("city") or current_user.city
    current_user.pincode = updated.get("pincode") or updated.get("postal_code") or current_user.pincode
    db.commit()
    return {"status": "success", "message": "Customer updated successfully", "data": updated}


@router.get("/{customer_id}")
def customer_detail(
    customer_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_permission("customers.view", "view-customers")),
):
    return {
        "status": "success",
        "data": get_customer_detail(db, customer_id, actor=current_user, request=request),
    }


@router.put("/{customer_id}")
def edit_customer(
    customer_id: int,
    data: CustomerUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_permission("customers.edit", "update-customers")),
):
    return {
        "status": "success",
        "message": "Customer updated successfully",
        "data": update_customer(db, customer_id, data, actor=current_user, request=request),
    }


@router.patch("/{customer_id}/status")
def change_customer_status(
    customer_id: int,
    data: CustomerStatusUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_permission("customers.edit", "update-customers")),
):
    return {
        "status": "success",
        "message": "Customer status updated successfully",
        "data": update_customer_status(db, customer_id, data, actor=current_user, request=request),
    }


@router.patch("/{customer_id}/block")
def block_customer_account(
    customer_id: int,
    data: CustomerBlockRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_permission("customers.block", "update-customers")),
):
    return {
        "status": "success",
        "message": "Customer blocked successfully",
        "data": block_customer(db, customer_id, data, actor=current_user, request=request),
    }


@router.post("/{customer_id}/block")
def block_customer_account_compat(
    customer_id: int,
    request: Request,
    data: CustomerBlockRequest | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_permission("customers.block", "update-customers")),
):
    block_data = data or CustomerBlockRequest(reason="Blocked by admin")
    return {
        "status": "success",
        "message": "Customer blocked successfully",
        "data": block_customer(db, customer_id, block_data, actor=current_user, request=request),
    }


@router.patch("/{customer_id}/unblock")
def unblock_customer_account(customer_id: int, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("customers.unblock", "update-customers"))):
    return {"status": "success", "message": "Customer unblocked successfully", "data": unblock_customer(db, customer_id, actor=current_user, request=request)}


@router.post("/{customer_id}/unblock")
def unblock_customer_account_compat(customer_id: int, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("customers.unblock", "update-customers"))):
    return {"status": "success", "message": "Customer unblocked successfully", "data": unblock_customer(db, customer_id, actor=current_user, request=request)}


@router.post("/{customer_id}/reset-password")
def reset_customer_login_password(
    customer_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_permission("customers.reset_password", "update-customers")),
):
    return {
        "status": "success",
        "message": "Customer password reset email sent successfully",
        "data": reset_customer_password(db, customer_id, actor=current_user, request=request),
    }


@router.get("/{customer_id}/bookings")
def customer_booking_history(
    customer_id: int,
    params: dict = Depends(pagination_params),
    booking_status: str = Query(default=""),
    payment_status: str = Query(default=""),
    db: Session = Depends(get_db),
    _=Depends(require_any_permission("customers.view_bookings", "customers.view", "view-customers")),
):
    get_customer_detail(db, customer_id)
    paginated = get_customer_booking_history(
        db,
        customer_id,
        page=params["page"],
        limit=params["limit"],
        booking_status=booking_status,
        payment_status=payment_status,
    )
    return {"status": "success", **paginated}


@router.get("/{customer_id}/payments")
def customer_payment_history(
    customer_id: int,
    params: dict = Depends(pagination_params),
    payment_status: str = Query(default=""),
    payment_method: str = Query(default=""),
    db: Session = Depends(get_db),
    _=Depends(require_any_permission("customers.view_payments", "customers.view", "view-customers")),
):
    get_customer_detail(db, customer_id)
    paginated = get_customer_payment_history(
        db,
        customer_id,
        page=params["page"],
        limit=params["limit"],
        payment_status=payment_status,
        payment_method=payment_method,
    )
    return {"status": "success", **paginated}


@router.get("/{customer_id}/communications")
def customer_communication_history(
    customer_id: int,
    params: dict = Depends(pagination_params),
    db: Session = Depends(get_db),
    _=Depends(require_any_permission("customers.view_communications", "customers.view", "view-customers")),
):
    get_customer_detail(db, customer_id)
    paginated = get_customer_communication_history(
        db,
        customer_id,
        page=params["page"],
        limit=params["limit"],
    )
    return {"status": "success", **paginated}


@router.post("/{customer_id}/communications")
def send_customer_communication(
    customer_id: int,
    data: SendCustomerMessageRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_permission("customers.communicate")),
):
    return {
        "status": "success",
        "message": "Customer message sent successfully",
        "data": send_customer_message(db, customer_id, data, actor=current_user, request=request),
    }


# self-service booking endpoint (any authenticated user)
class SelfBookingCreate(BookingCreate):
    customer_id: int = 0


@router.post("/me/bookings")
def self_create_booking(
    data: SelfBookingCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Allows any authenticated user to create a booking for themselves."""
    customer = db.query(Customer).filter(Customer.user_id == current_user.id).first()
    if not customer:
        # Auto-create a minimal customer profile so the booking can proceed
        name_parts = (current_user.name or "").split(" ", 1)
        customer = Customer(
            user_id=current_user.id,
            email=current_user.email,
            full_name=current_user.name or current_user.email,
            first_name=name_parts[0],
            last_name=name_parts[1] if len(name_parts) > 1 else "",
        )
        db.add(customer)
        db.flush()
        customer.customer_code = f"CUST-{customer.id:06d}"
        db.commit()
        db.refresh(customer)

    booking_data = data.model_copy(update={
        "customer_id": customer.id,
        "booking_source": "customer",
    })
    result = create_booking(db, booking_data, actor=current_user, request=request)
    return {"status": "success", "message": "Booking created successfully", "data": result}
