from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.modules.bookings.schemas import (
    BookingCancelRequest,
    BookingCreate,
    BookingStatusUpdate,
    BookingUpdate,
)
from app.modules.bookings.service import (
    cancel_booking,
    create_booking,
    get_booking_detail,
    get_bookings,
    update_booking,
    update_booking_status,
)
from app.modules.common.auth import require_any_permission
from app.modules.common.pagination import pagination_params
from app.modules.users.models import User

router = APIRouter(prefix="/bookings", tags=["Bookings"])


@router.get("")
@router.get("/")
def list_bookings(
    params: dict = Depends(pagination_params),
    customer_id: int = Query(default=0),
    booking_status: str = Query(default=""),
    payment_status: str = Query(default=""),
    start_date: str = Query(default=""),
    end_date: str = Query(default=""),
    sort_by: str = Query(default="newest"),
    db: Session = Depends(get_db),
    _=Depends(require_any_permission("bookings.view", "view-bookings")),
):
    result = get_bookings(
        db,
        page=params["page"],
        limit=params["limit"],
        search=params["search"],
        customer_id=customer_id or None,
        booking_status=booking_status,
        payment_status=payment_status,
        start_date=start_date,
        end_date=end_date,
        sort_by=sort_by,
    )
    return {"status": "success", **result}


@router.post("/")
def add_booking(
    data: BookingCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_permission("bookings.create", "create-bookings")),
):
    return {
        "status": "success",
        "message": "Booking created successfully",
        "data": create_booking(db, data, actor=current_user, request=request),
    }


@router.get("/{booking_id}")
def booking_detail(
    booking_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_permission("bookings.view", "view-bookings")),
):
    return {
        "status": "success",
        "data": get_booking_detail(db, booking_id, actor=current_user, request=request),
    }


@router.put("/{booking_id}")
def edit_booking(
    booking_id: int,
    data: BookingUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_permission("bookings.edit", "update-bookings")),
):
    return {
        "status": "success",
        "message": "Booking updated successfully",
        "data": update_booking(db, booking_id, data, actor=current_user, request=request),
    }


@router.patch("/{booking_id}/status")
def change_booking_status(
    booking_id: int,
    data: BookingStatusUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_permission("bookings.edit", "update-bookings")),
):
    return {
        "status": "success",
        "message": "Booking status updated successfully",
        "data": update_booking_status(db, booking_id, data, actor=current_user, request=request),
    }


@router.patch("/{booking_id}/cancel")
def cancel_booking_endpoint(
    booking_id: int,
    request: Request,
    data: BookingCancelRequest | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_permission("bookings.cancel", "update-bookings")),
):
    cancel_data = data or BookingCancelRequest(reason="Cancelled by admin")
    return {
        "status": "success",
        "message": "Booking cancelled successfully",
        "data": cancel_booking(db, booking_id, cancel_data, actor=current_user, request=request),
    }
