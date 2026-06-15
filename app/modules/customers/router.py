from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.modules.common.auth import require_any_permission
from app.modules.common.pagination import pagination_params
from app.modules.customers.schemas import (
    CustomerBlockRequest,
    CustomerCreate,
    CustomerStatusUpdate,
    CustomerUpdate,
    SendCustomerMessageRequest,
)
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
    unblock_customer,
    update_customer,
    update_customer_status,
)
from app.modules.users.models import User

router = APIRouter(prefix="/customers", tags=["Customers"])


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
    db: Session = Depends(get_db),
    _=Depends(require_any_permission("customers.view", "view-customers")),
):
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
def unblock_customer_account(
    customer_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_permission("customers.unblock", "update-customers")),
):
    return {
        "status": "success",
        "message": "Customer unblocked successfully",
        "data": unblock_customer(db, customer_id, actor=current_user, request=request),
    }


@router.post("/{customer_id}/unblock")
def unblock_customer_account_compat(
    customer_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_permission("customers.unblock", "update-customers")),
):
    return {
        "status": "success",
        "message": "Customer unblocked successfully",
        "data": unblock_customer(db, customer_id, actor=current_user, request=request),
    }


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
