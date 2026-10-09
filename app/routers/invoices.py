from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth.permissions import get_current_user, require_any_permission
from app.services.supplier_scope import is_supplier_user
from app.utils.pagination import pagination_params
from app.schemas.invoices import InvoiceEmailRequest, InvoiceGenerateRequest
from app.services.invoices import (
    download_invoice_pdf,
    email_invoice_to_customer,
    generate_invoice,
    get_invoice,
    list_invoices,
    mark_invoice_emailed,
    regenerate_invoice_pdf,
    serialize_invoice,
)
from app.models.users import User

router = APIRouter(prefix="/invoices", tags=["Invoices"])
supplier_router = APIRouter(prefix="/supplier/invoices", tags=["Supplier Invoices"])


def _require_supplier(current_user: User) -> User:
    if not is_supplier_user(current_user):
        raise HTTPException(status_code=403, detail="Supplier invoice access denied")
    return current_user


@router.get("")
@router.get("/")
def invoices(params: dict = Depends(pagination_params), booking_id: int = Query(default=0), customer_id: int = Query(default=0), db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("invoices.view"))):
    return {"status": "success", **list_invoices(db, params["page"], params["limit"], booking_id or None, customer_id or None, actor=current_user)}


@router.post("/generate")
def generate(data: InvoiceGenerateRequest, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("invoices.generate"))):
    return {"status": "success", "data": generate_invoice(db, data, current_user, request)}


@router.get("/{invoice_id}")
def detail(invoice_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("invoices.view"))):
    return {"status": "success", "data": serialize_invoice(get_invoice(db, invoice_id, current_user), detail=True)}


@router.post("/{invoice_id}/generate-pdf")
def generate_pdf(invoice_id: int, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("invoices.generate", "invoices.view"))):
    result = regenerate_invoice_pdf(db, invoice_id, current_user, request)
    return {"status": "success", "message": "PDF generated", "data": result}


@router.get("/{invoice_id}/download")
def download(invoice_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("invoices.download", "invoices.view"))):
    fs_path, filename = download_invoice_pdf(db, invoice_id, current_user)
    return FileResponse(path=fs_path, filename=filename, media_type="application/pdf")


@router.post("/{invoice_id}/email")
def email_invoice(invoice_id: int, data: InvoiceEmailRequest, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("invoices.email", "invoices.view"))):
    result = email_invoice_to_customer(db, invoice_id, data, current_user, request)
    return {"status": "success", "message": "Invoice emailed to customer", "data": result}


@supplier_router.get("")
@supplier_router.get("/")
def supplier_invoices(
    params: dict = Depends(pagination_params),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List only invoices for bookings fulfilled by the signed-in supplier."""
    actor = _require_supplier(current_user)
    return {"status": "success", **list_invoices(db, params["page"], params["limit"], actor=actor)}


@supplier_router.get("/{invoice_id}/download")
def download_supplier_invoice(
    invoice_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Download only an invoice belonging to the signed-in supplier's booking."""
    actor = _require_supplier(current_user)
    fs_path, filename = download_invoice_pdf(db, invoice_id, actor)
    return FileResponse(path=fs_path, filename=filename, media_type="application/pdf")
