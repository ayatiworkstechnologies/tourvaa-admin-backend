from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app.modules.common.auth import require_any_permission
from app.modules.common.pagination import pagination_params
from app.modules.invoices.schemas import InvoiceEmailRequest, InvoiceGenerateRequest
from app.modules.invoices.service import (
    download_invoice_pdf,
    email_invoice_to_customer,
    generate_invoice,
    get_invoice,
    list_invoices,
    mark_invoice_emailed,
    regenerate_invoice_pdf,
    serialize_invoice,
)
from app.modules.users.models import User

router = APIRouter(prefix="/invoices", tags=["Invoices"])


class InvoiceEmailBody(BaseModel):
    email: Optional[str] = None


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


@router.post("/{invoice_id}/generate-pdf")
def generate_pdf(invoice_id: int, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("invoices.generate", "invoices.view"))):
    result = regenerate_invoice_pdf(db, invoice_id, current_user, request)
    return {"status": "success", "message": "PDF generated", "data": result}


@router.get("/{invoice_id}/download")
def download(invoice_id: int, db: Session = Depends(get_db), _=Depends(require_any_permission("invoices.download", "invoices.view"))):
    fs_path, filename = download_invoice_pdf(db, invoice_id)
    return FileResponse(path=fs_path, filename=filename, media_type="application/pdf")


@router.post("/{invoice_id}/email")
def email_invoice(invoice_id: int, data: InvoiceEmailBody, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("invoices.email", "invoices.view"))):
    result = email_invoice_to_customer(db, invoice_id, data.email, current_user, request)
    return {"status": "success", "message": "Invoice emailed to customer", "data": result}
