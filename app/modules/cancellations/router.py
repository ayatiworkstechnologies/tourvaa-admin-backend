from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.modules.cancellations import service
from app.modules.cancellations.schemas import (
    CancellationApprove, CancellationReject, CancellationRequestCreate,
    ProcessRefundBody, RefundRuleCreate,
)
from app.modules.common.auth import get_current_user, require_any_permission
from app.modules.common.pagination import pagination_params

router = APIRouter(tags=["Cancellations"])


@router.post("/bookings/{booking_id}/cancel-request")
def customer_cancel_request(
    booking_id: int,
    body: CancellationRequestCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    body.booking_id = booking_id
    result = service.create_request(db, data=body, actor=current_user, request=request)
    return {"status": "success", "message": "Cancellation request submitted", "data": result}


# admin side - list + approve/reject/refund

@router.get("/cancellations")
def list_cancellations(pagination=Depends(pagination_params), status: str = Query(default=""), customer_id: int = Query(default=0), db: Session = Depends(get_db), _=Depends(require_any_permission("bookings.cancel", "bookings.view"))):
    return {"status": "success", **service.list_requests(db, page=pagination["page"], limit=pagination["limit"], status=status, customer_id=customer_id or None)}


@router.patch("/cancellations/{request_id}/approve")
def approve_cancellation(request_id: int, data: CancellationApprove, request: Request, db: Session = Depends(get_db), current_user=Depends(require_any_permission("bookings.cancel", "bookings.update_status"))):
    result = service.approve_request(db, request_id=request_id, data=data, actor=current_user, request=request)
    return {"status": "success", "message": "Cancellation approved and booking cancelled", "data": result}


@router.patch("/cancellations/{request_id}/reject")
def reject_cancellation(request_id: int, data: CancellationReject, request: Request, db: Session = Depends(get_db), current_user=Depends(require_any_permission("bookings.cancel", "bookings.update_status"))):
    result = service.reject_request(db, request_id=request_id, data=data, actor=current_user, request=request)
    return {"status": "success", "message": "Cancellation request rejected", "data": result}


@router.post("/cancellations/{request_id}/process-refund")
def process_refund(
    request_id: int,
    data: ProcessRefundBody,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(require_any_permission("payments.refund", "bookings.cancel")),
):
    result = service.process_refund(db, request_id=request_id, data=data, actor=current_user, request=request)
    return {"status": "success", "message": "Refund processed", "data": result}


# refund policy rules

@router.get("/refund-rules")
def list_rules(tour_id: int = Query(default=0), db: Session = Depends(get_db), _=Depends(require_any_permission("tours.view", "view-tours"))):
    return service.list_rules(db, tour_id=tour_id or None)


@router.post("/refund-rules")
def create_rule(data: RefundRuleCreate, request: Request, db: Session = Depends(get_db), current_user=Depends(require_any_permission("tours.edit", "update-tours"))):
    result = service.create_rule(db, data=data, actor=current_user, request=request)
    return {"status": "success", "data": result}


@router.delete("/refund-rules/{rule_id}")
def delete_rule(rule_id: int, request: Request, db: Session = Depends(get_db), current_user=Depends(require_any_permission("tours.edit", "update-tours"))):
    service.delete_rule(db, rule_id=rule_id, actor=current_user, request=request)
    return {"status": "success", "message": "Rule deleted"}
