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


@router.get("/sample-pdf")
def sample_pdf(
    template_type: str = Query(default="agent_reservation_invoice"),
    currency: str = Query(default=""),
    tour_name: str = Query(default=""),
    booking_code: str = Query(default=""),
    recipient_business_name: str = Query(default=""),
    recipient_contact_name: str = Query(default=""),
    recipient_address: str = Query(default=""),
    recipient_email: str = Query(default=""),
    recipient_phone: str = Query(default=""),
    tour_price: float = Query(default=0.0),
    addons_total: float = Query(default=0.0),
    discount_total: float = Query(default=0.0),
    tax_amount: float = Query(default=0.0),
    adult_count: int = Query(default=2),
    child_count: int = Query(default=0),
    travel_date: str = Query(default=""),
    lead_traveller: str = Query(default=""),
    pickup: str = Query(default=""),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_permission("invoices.view", "settings.view")),
):
    import tempfile
    from pathlib import Path
    from app.models.settings import AppSetting
    from app.utils.invoices_pdf import generate_pdf

    keys = [
        "invoice_brand_name", "invoice_brand_tagline", "invoice_logo_url",
        "invoice_header_layout", "invoice_primary_color", "invoice_header_color",
        "invoice_accent_color", "company_legal_name", "company_name",
        "company_address", "support_email", "company_gst_number", "website",
        "invoice_footer_thanks", "invoice_footer_legal",
    ]
    rows = db.query(AppSetting).filter(AppSetting.key.in_(keys)).all()
    vals = {r.key: (r.value or "").strip() for r in rows}

    brand_name = vals.get("invoice_brand_name") or "Tourvaa"
    legal_name = vals.get("company_legal_name") or vals.get("company_name") or "Tourvaa Ltd"
    address = vals.get("company_address") or "Level 1, 123 Queen Street, Auckland 1010, New Zealand"
    email = vals.get("support_email") or "support@tourvaa.com"
    website = vals.get("website") or "www.tourvaa.com"
    gst = vals.get("company_gst_number") or ""

    is_agent = "agent" in template_type
    is_supplier = "supplier" in template_type
    is_tax_invoice = template_type == "tax_invoice"
    is_booking_invoice = template_type in {"agent_reservation_invoice", "customer_reservation_invoice", "customer_reserve"}
    is_deposit_document = template_type in {"deposit_receipt", "customer_deposit"}
    is_full_receipt = "full" in template_type or template_type in {"payment_receipt", "tax_invoice", "supplier_remittance", "supplier_invoice"}

    curr = currency.strip() if currency.strip() else "AUD"
    t_name = tour_name.strip() if tour_name.strip() else "Rotorua Geothermal & Maori Cultural Experience"
    b_code = booking_code.strip() if booking_code.strip() else "TVA-BK-2026-0089"
    t_date = travel_date.strip() if travel_date.strip() else "2026-11-25"

    if is_agent:
        recipient_biz = recipient_business_name.strip() or "Apex Voyages & Holidays Pty Ltd"
        contact_name = recipient_contact_name.strip() or "Sarah Jenkins"
        rec_addr = recipient_address.strip() or "45 St Georges Terrace, Perth WA 6000, Australia"
        rec_email = recipient_email.strip() or "accounts@apexvoyages.com"
        rec_phone = recipient_phone.strip() or "+61 8 9222 1100"
    elif is_supplier:
        recipient_biz = recipient_business_name.strip() or "Rotorua Adventures & Cultural Experiences Ltd"
        contact_name = recipient_contact_name.strip() or "Hemi Te Kanawa"
        rec_addr = recipient_address.strip() or "88 Fenton Street, Rotorua 3010, New Zealand"
        rec_email = recipient_email.strip() or "accounts@rotoruaadventures.co.nz"
        rec_phone = recipient_phone.strip() or "+64 7 348 9900"
    else:
        recipient_biz = recipient_business_name.strip() if (is_tax_invoice and recipient_business_name.strip()) else ""
        contact_name = recipient_contact_name.strip() or recipient_business_name.strip() or "David & Emily Miller"
        rec_addr = recipient_address.strip() or "12 Ocean Drive, Manly NSW 2095, Australia"
        rec_email = recipient_email.strip() or "david.miller@example.com"
        rec_phone = recipient_phone.strip() or "+61 412 345 678"

    t_price_val = tour_price if tour_price > 0 else 1450.0
    addons_val = addons_total if addons_total > 0 else (180.0 if tour_price == 0 else 0.0)
    disc_val = discount_total if discount_total > 0 else (65.0 if tour_price == 0 else 0.0)
    tax_val = tax_amount if tax_amount > 0 else (156.5 if tour_price == 0 else 0.0)
    total_calc = t_price_val + addons_val - disc_val

    tot_travellers = adult_count + child_count
    traveller_qty = f"{tot_travellers} traveller{'s' if tot_travellers > 1 else ''}"

    items = [
        {"description": "Total Tour Price", "quantity": traveller_qty, "total_price": f"{t_price_val:.2f}"},
    ]
    if addons_val > 0:
        items.append({"description": "Add-ons / extras", "quantity": "Included", "total_price": f"{addons_val:.2f}"})
    if disc_val > 0:
        items.append({"description": "Discount", "quantity": "%", "total_price": f"-{disc_val:.2f}"})
    if tax_val > 0:
        items.append({"description": "Including Tax", "quantity": "Included (do not add tax amount or percentage)", "total_price": f"{tax_val:.2f}"})

    booking_total_str = f"{total_calc:.2f}"

    doc_title = None
    doc_number_label = None
    recipient_heading = None

    if is_booking_invoice:
        paid_str = "0.00"
        due_str = booking_total_str
        due_date = "2026-11-05"
        p_date = ""
        p_method = ""
        tx_id = ""
        doc_num = "TVA-INV-SAMPLE" if is_agent else "TVA-INV-CUST-SAMPLE"
        doc_title = "BOOKING INVOICE"
        doc_number_label = "Invoice No."
        recipient_heading = "BILL TO"
    elif is_deposit_document:
        paid_val = min(450.0, total_calc * 0.3)
        paid_str = f"{paid_val:.2f}"
        due_str = f"{(total_calc - paid_val):.2f}"
        due_date = "2026-11-10"
        p_date = "2026-10-28"
        p_method = "Apple Pay"
        tx_id = "ch_3Nxy987654321"
        doc_num = "TVA-DOC-SAMPLE"
        doc_title = "BOOKING INVOICE & PAYMENT RECEIPT"
        doc_number_label = "Document No."
        recipient_heading = "BILL TO"
    elif is_tax_invoice:
        paid_str = booking_total_str
        due_str = "0.00"
        due_date = ""
        p_date = "2026-10-28"
        p_method = "Direct Settlement"
        tx_id = "tx_tax_20261028"
        doc_num = "TVA-TAX-SAMPLE"
        doc_title = "TAX INVOICE"
        doc_number_label = "Tax Inv No."
        recipient_heading = "BILL TO"
    elif is_supplier:
        supplier_payout = total_calc * 0.85
        paid_str = f"{supplier_payout:.2f}"
        due_str = "0.00"
        due_date = ""
        p_date = "2026-10-28"
        p_method = "Direct Bank Remittance (EFT)"
        tx_id = "remit_batch_89021"
        doc_num = "TVA-REMIT-SAMPLE"
        doc_title = "SUPPLIER REMITTANCE VOUCHER"
        doc_number_label = "Remittance No."
        recipient_heading = "REMIT TO"
    else:
        paid_str = booking_total_str
        due_str = "0.00"
        due_date = ""
        p_date = "2026-10-28"
        p_method = "Stripe Credit Card" if is_agent else "VISA Debit"
        tx_id = "ch_3Nxy123456789"
        doc_num = "TVA-REC-SAMPLE"
        doc_title = "PAYMENT RECEIPT"
        doc_number_label = "Receipt No."
        recipient_heading = "RECEIVED FROM"

    data = {
        "is_agent": is_agent,
        "is_booking_invoice": is_booking_invoice,
        "is_deposit_document": is_deposit_document,
        "is_full_receipt": is_full_receipt,
        "document_title": doc_title,
        "doc_number_label": doc_number_label,
        "recipient_heading": recipient_heading,
        "invoice_number": doc_num,
        "invoice_date": "2026-10-28",
        "tourvaa_legal_business_name": legal_name,
        "tourvaa_business_address": address,
        "tourvaa_email": email,
        "tourvaa_website": website,
        "tourvaa_gst_number": gst,
        "invoice_brand_name": brand_name,
        "invoice_brand_tagline": vals.get("invoice_brand_tagline") or "Curated journeys, effortlessly booked.",
        "invoice_logo_url": vals.get("invoice_logo_url") or "",
        "invoice_header_layout": vals.get("invoice_header_layout") or "both",
        "invoice_primary_color": vals.get("invoice_primary_color") or "#07566A",
        "invoice_header_color": vals.get("invoice_header_color") or "#0B263D",
        "invoice_accent_color": vals.get("invoice_accent_color") or "#159C96",
        "recipient_business_name": recipient_biz,
        "recipient_contact_name": contact_name,
        "customer_name": contact_name,
        "recipient_address": rec_addr,
        "recipient_email": rec_email,
        "recipient_phone": rec_phone,
        "booking_code": b_code,
        "tour_name": t_name,
        "travel_date": t_date,
        "adult_count": adult_count,
        "child_count": child_count,
        "lead_traveller": lead_traveller or ("David Miller" if not is_agent else ""),
        "pickup": pickup or ("08:30 AM Hotel Lobby" if not is_agent else ""),
        "currency": curr,
        "items": items,
        "booking_total": booking_total_str,
        "total_amount": booking_total_str,
        "amount_paid": paid_str,
        "cumulative_paid": paid_str,
        "amount_due": due_str,
        "balance_due_date": due_date,
        "payment_date": p_date,
        "payment_method": p_method,
        "transaction_id": tx_id,
        "payment_link": f"https://{website.strip('/')}/payments?booking_id={b_code}",
        "terms_url": f"https://{website.strip('/')}/terms#cancellation-terms",
        "cancellation_policy": f"Free cancellation up to 7 days before tour departure for {t_name}.",
        "booking_status": "confirmed",
        "payment_status": "paid" if due_str == "0.00" else ("outstanding" if paid_str == "0.00" else "partially_paid"),
        "invoice_footer_thanks": vals.get("invoice_footer_thanks") or "Thank you for booking with Tourvaa.",
        "invoice_footer_legal": vals.get("invoice_footer_legal") or "This document is generated by Tourvaa and reflects the financial status as of the issue date.",
    }

    tmp_dir = Path(tempfile.gettempdir()) / "tourvaa_invoice_samples"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = tmp_dir / f"{template_type}_{curr}.pdf"
    generate_pdf(pdf_path, data)
    return FileResponse(path=str(pdf_path), filename=f"sample_{template_type}_{curr}.pdf", media_type="application/pdf")


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
