from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.modules.common.auth import require_any_permission
from app.modules.common.pagination import pagination_params
from app.modules.payments.schemas import PaymentAuthorize, PaymentCapture, PaymentCreate, PaymentStatusUpdate, PaymentUpdate, PaymentVoid, RefundRequest
from app.modules.payments.service import authorize_payment, capture_payment, create_payment, get_customer_payments, get_payment_detail, get_payments, process_refund, update_payment, update_payment_status, void_payment
from app.modules.users.models import User

router = APIRouter(prefix="/payments", tags=["Payments"])


@router.get("")
@router.get("/")
def list_payments(params: dict = Depends(pagination_params), customer_id: int = Query(default=0), booking_id: int = Query(default=0), payment_status: str = Query(default=""), payment_method: str = Query(default=""), start_date: str = Query(default=""), end_date: str = Query(default=""), db: Session = Depends(get_db), _=Depends(require_any_permission("payments.view", "view-payments"))):
    return {"status": "success", **get_payments(db, page=params["page"], limit=params["limit"], search=params["search"], customer_id=customer_id or None, booking_id=booking_id or None, payment_status=payment_status, payment_method=payment_method, start_date=start_date, end_date=end_date)}


@router.post("/")
def add_payment(data: PaymentCreate, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("payments.create", "create-payments"))):
    return {"status": "success", "message": "Payment recorded successfully", "data": create_payment(db, data, actor=current_user, request=request)}


@router.post("/authorize")
def authorize(data: PaymentAuthorize, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("payments.create", "payments.capture", "create-payments"))):
    return {"status": "success", "message": "Payment authorized", "data": authorize_payment(db, data, actor=current_user, request=request)}


@router.get("/customer/{customer_id}")
def customer_payment_list(customer_id: int, params: dict = Depends(pagination_params), payment_status: str = Query(default=""), payment_method: str = Query(default=""), db: Session = Depends(get_db), _=Depends(require_any_permission("payments.view", "view-payments"))):
    return {"status": "success", **get_customer_payments(db, customer_id=customer_id, page=params["page"], limit=params["limit"], payment_status=payment_status, payment_method=payment_method)}


@router.get("/{payment_id}")
def payment_detail(payment_id: int, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("payments.view", "view-payments"))):
    return {"status": "success", "data": get_payment_detail(db, payment_id, actor=current_user, request=request)}


@router.put("/{payment_id}")
def edit_payment(payment_id: int, data: PaymentUpdate, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("payments.edit", "update-payments"))):
    return {"status": "success", "message": "Payment updated successfully", "data": update_payment(db, payment_id, data, actor=current_user, request=request)}


@router.patch("/{payment_id}/status")
def change_payment_status(payment_id: int, data: PaymentStatusUpdate, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("payments.edit", "update-payments"))):
    return {"status": "success", "message": "Payment status updated successfully", "data": update_payment_status(db, payment_id, data, actor=current_user, request=request)}


@router.post("/{payment_id}/capture")
def capture(payment_id: int, data: PaymentCapture, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("payments.capture", "update-payments"))):
    return {"status": "success", "message": "Payment captured", "data": capture_payment(db, payment_id, data, actor=current_user, request=request)}


@router.post("/{payment_id}/void")
def void(payment_id: int, data: PaymentVoid, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("payments.void", "update-payments"))):
    return {"status": "success", "message": "Payment voided", "data": void_payment(db, payment_id, data, actor=current_user, request=request)}


@router.post("/{payment_id}/refund")
def refund_payment(payment_id: int, data: RefundRequest, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("payments.refund", "update-payments"))):
    return {"status": "success", "message": "Refund processed successfully", "data": process_refund(db, payment_id, data, actor=current_user, request=request)}
