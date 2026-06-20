from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.modules.common.auth import require_any_permission
from app.modules.common.pagination import pagination_params
from app.modules.invoices.schemas import InvoiceEmailRequest, InvoiceGenerateRequest
from app.modules.invoices.service import generate_invoice, get_invoice, list_invoices, mark_invoice_emailed, serialize_invoice
from app.modules.users.models import User

router = APIRouter(prefix="/invoices", tags=["Invoices"])

@router.get("")
@router.get("/")
def invoices(params: dict = Depends(pagination_params), booking_id: int = Query(default=0), customer_id: int = Query(default=0), db: Session = Depends(get_db), _=Depends(require_any_permission("invoices.view"))):
    return {"status": "success", **list_invoices(db, params["page"], params["limit"], booking_id or None, customer_id or None)}

@router.post("/generate")
def generate(data: InvoiceGenerateRequest, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("invoices.generate"))):
    return {"status": "success", "data": generate_invoice(db, data, current_user, request)}

@router.get("/{invoice_id}")
def detail(invoice_id: int, db: Session = Depends(get_db), _=Depends(require_any_permission("invoices.view"))):
    return {"status": "success", "data": serialize_invoice(get_invoice(db, invoice_id), detail=True)}

@router.get("/{invoice_id}/download")
def download(invoice_id: int, db: Session = Depends(get_db), _=Depends(require_any_permission("invoices.download", "invoices.view"))):
    return {"status": "success", "data": serialize_invoice(get_invoice(db, invoice_id), detail=True)}

@router.post("/{invoice_id}/email")
def email(invoice_id: int, data: InvoiceEmailRequest, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("invoices.email"))):
    return {"status": "success", "data": mark_invoice_emailed(db, invoice_id, data, current_user, request)}
