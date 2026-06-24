from math import ceil

from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from app.config import get_storage_root
from app.modules.audit.service import log_audit
from app.modules.bookings.models import Booking, EmailLog
from app.modules.common.money import money, money_str, utcnow
from app.modules.invoices.models import Invoice, InvoiceItem
from app.modules.invoices.schemas import InvoiceEmailRequest, InvoiceGenerateRequest
from app.modules.payments.models import Payment
from app.modules.users.models import User


def _invoice_number(invoice_id: int) -> str:
    return f"TVA-INV-{invoice_id:06d}"


def serialize_invoice(inv: Invoice, detail: bool = False) -> dict:
    data = {"id": inv.id, "invoice_number": inv.invoice_number, "booking_id": inv.booking_id, "payment_id": inv.payment_id, "customer_id": inv.customer_id, "invoice_type": inv.invoice_type, "status": inv.status, "currency": inv.currency, "subtotal_amount": money_str(inv.subtotal_amount), "gst_amount": money_str(inv.gst_amount), "total_amount": money_str(inv.total_amount), "amount_paid": money_str(inv.amount_paid), "amount_due": money_str(inv.amount_due), "pdf_path": inv.pdf_path, "emailed_at": inv.emailed_at, "created_at": inv.created_at, "updated_at": inv.updated_at}
    if detail:
        data["items"] = [{"id": i.id, "item_type": i.item_type, "description": i.description, "quantity": i.quantity, "unit_price": money_str(i.unit_price), "tax_amount": money_str(i.tax_amount), "total_price": money_str(i.total_price)} for i in inv.items]
    return data


def list_invoices(db: Session, page: int = 1, limit: int = 20, booking_id: int | None = None, customer_id: int | None = None):
    query = db.query(Invoice)
    if booking_id: query = query.filter(Invoice.booking_id == booking_id)
    if customer_id: query = query.filter(Invoice.customer_id == customer_id)
    query = query.order_by(Invoice.id.desc())
    total = query.count()
    items = [serialize_invoice(i) for i in query.offset((page - 1) * limit).limit(limit).all()]
    return {"items": items, "data": items, "total": total, "page": page, "limit": limit, "total_pages": max(1, ceil(total / limit))}


def get_invoice(db: Session, invoice_id: int) -> Invoice:
    inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return inv


def generate_invoice(db: Session, data: InvoiceGenerateRequest, actor: User, request: Request | None = None):
    booking = db.query(Booking).filter(Booking.id == data.booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    payment = db.query(Payment).filter(Payment.id == data.payment_id).first() if data.payment_id else None
    subtotal = money(payment.captured_amount if payment else booking.final_amount)
    gst = money(subtotal * data.gst_rate)
    total = money(subtotal + gst)
    paid = money(payment.captured_amount if payment else booking.amount_paid)
    inv = Invoice(booking_id=booking.id, payment_id=payment.id if payment else None, customer_id=booking.customer_id, invoice_type=data.invoice_type, currency=booking.currency, subtotal_amount=subtotal, gst_amount=gst, total_amount=total, amount_paid=paid, amount_due=max(money(0), total - paid), created_by=actor.id)
    db.add(inv)
    db.flush()
    inv.invoice_number = _invoice_number(inv.id)
    db.add(InvoiceItem(invoice_id=inv.id, item_type="booking", description=f"Booking {booking.booking_code or booking.id}", quantity=1, unit_price=subtotal, tax_amount=gst, total_price=total))
    storage = get_storage_root().joinpath("invoices")
    storage.mkdir(parents=True, exist_ok=True)
    pdf_path = storage.joinpath(f"{inv.invoice_number}.pdf")
    invoice_data = {
        "invoice_number": inv.invoice_number,
        "booking_code": booking.booking_code or str(booking.id),
        "customer_name": (booking.customer.user.name if booking.customer and booking.customer.user else ""),
        "invoice_date": utcnow().strftime("%Y-%m-%d"),
        "status": inv.status or "pending",
        "currency": inv.currency,
        "subtotal_amount": money_str(inv.subtotal_amount),
        "gst_amount": money_str(inv.gst_amount),
        "total_amount": money_str(inv.total_amount),
        "amount_paid": money_str(inv.amount_paid),
        "amount_due": money_str(inv.amount_due),
        "items": [{"description": f"Booking {booking.booking_code or booking.id}", "quantity": 1, "unit_price": money_str(subtotal), "tax_amount": money_str(gst), "total_price": money_str(total)}],
    }
    from app.modules.invoices.pdf_generator import generate_pdf
    generate_pdf(pdf_path, invoice_data)
    inv.pdf_path = f"/storage/invoices/{inv.invoice_number}.pdf"
    from app.modules.notifications.service import enqueue_notification, notify_admins
    notify_admins(db, notification_type="invoice_generated", title="Invoice generated", message=f"Invoice {inv.invoice_number} was generated", entity_type="invoice", entity_id=inv.id)
    if booking.customer and booking.customer.user_id:
        enqueue_notification(db, user_id=booking.customer.user_id, notification_type="invoice_generated", title="Invoice generated", message=f"Invoice {inv.invoice_number} is ready", entity_type="invoice", entity_id=inv.id)
    log_audit(db, actor=actor, action="generate_invoice", entity_type="invoice", entity_id=inv.id, request=request)
    db.commit()
    db.refresh(inv)
    return serialize_invoice(inv, detail=True)


def regenerate_invoice_pdf(db: Session, invoice_id: int, actor: User, request: Request | None = None):
    inv = get_invoice(db, invoice_id)
    booking = inv.booking
    if not booking:
        raise HTTPException(status_code=400, detail="Invoice has no associated booking")
    storage = get_storage_root().joinpath("invoices")
    storage.mkdir(parents=True, exist_ok=True)
    pdf_path = storage.joinpath(f"{inv.invoice_number}.pdf")
    invoice_data = {
        "invoice_number": inv.invoice_number,
        "booking_code": booking.booking_code or str(booking.id),
        "customer_name": (booking.customer.user.name if booking.customer and booking.customer.user else ""),
        "invoice_date": utcnow().strftime("%Y-%m-%d"),
        "status": inv.status or "pending",
        "currency": inv.currency,
        "subtotal_amount": money_str(inv.subtotal_amount),
        "gst_amount": money_str(inv.gst_amount),
        "total_amount": money_str(inv.total_amount),
        "amount_paid": money_str(inv.amount_paid),
        "amount_due": money_str(inv.amount_due),
        "items": [{"description": i.description, "quantity": i.quantity, "unit_price": money_str(i.unit_price), "tax_amount": money_str(i.tax_amount), "total_price": money_str(i.total_price)} for i in inv.items],
    }
    from app.modules.invoices.pdf_generator import generate_pdf
    generate_pdf(pdf_path, invoice_data)
    inv.pdf_path = f"/storage/invoices/{inv.invoice_number}.pdf"
    log_audit(db, actor=actor, action="regenerate_invoice_pdf", entity_type="invoice", entity_id=inv.id, request=request)
    db.commit()
    db.refresh(inv)
    return serialize_invoice(inv, detail=True)


def download_invoice_pdf(db: Session, invoice_id: int) -> tuple[str, str]:
    """Returns (file_system_path, filename) for FileResponse."""
    from app.config import get_storage_root
    inv = get_invoice(db, invoice_id)
    if not inv.pdf_path:
        raise HTTPException(status_code=404, detail="PDF not yet generated for this invoice")
    fs_path = str(get_storage_root()) + inv.pdf_path.replace("/storage", "")
    import os
    if not os.path.exists(fs_path):
        raise HTTPException(status_code=404, detail="PDF file not found on server — please regenerate")
    return fs_path, f"{inv.invoice_number}.pdf"


def email_invoice_to_customer(db: Session, invoice_id: int, email: str | None, actor: User, request: Request | None = None):
    inv = get_invoice(db, invoice_id)
    booking = inv.booking
    recipient = email or (booking.customer.user.email if booking and booking.customer and booking.customer.user else None)
    if not recipient:
        raise HTTPException(status_code=400, detail="No recipient email address available")
    from app.modules.common.mailer import try_send_email
    subject = f"Your Invoice {inv.invoice_number} from Tourvaa"
    body = f"""
<p>Dear Customer,</p>
<p>Please find attached your invoice <b>{inv.invoice_number}</b>.</p>
<p>Total Amount: <b>{inv.currency} {money_str(inv.total_amount)}</b></p>
<p>Amount Due: <b>{inv.currency} {money_str(inv.amount_due)}</b></p>
<p>Thank you for booking with Tourvaa.</p>
"""
    try_send_email(recipient, subject, body)
    inv.status = "emailed"
    inv.emailed_at = utcnow()
    db.add(EmailLog(recipient_email=recipient, subject=subject, template_key="invoice_emailed", entity_type="invoice", entity_id=inv.id, status="sent", sent_at=utcnow()))
    log_audit(db, actor=actor, action="email_invoice", entity_type="invoice", entity_id=inv.id, request=request)
    db.commit()
    db.refresh(inv)
    return serialize_invoice(inv, detail=True)


def mark_invoice_emailed(db: Session, invoice_id: int, data: InvoiceEmailRequest, actor: User, request: Request | None = None):
    inv = get_invoice(db, invoice_id)
    inv.status = "emailed"
    inv.emailed_at = utcnow()
    db.add(EmailLog(recipient_email=data.email or "", subject=f"Invoice {inv.invoice_number}", template_key="invoice_sent", entity_type="invoice", entity_id=inv.id, status="sent", sent_at=utcnow()))
    from app.modules.notifications.service import notify_admins
    notify_admins(db, notification_type="invoice_sent", title="Invoice emailed", message=f"Invoice {inv.invoice_number} was marked emailed", entity_type="invoice", entity_id=inv.id)
    log_audit(db, actor=actor, action="email_invoice", entity_type="invoice", entity_id=inv.id, request=request)
    db.commit()
    db.refresh(inv)
    return serialize_invoice(inv, detail=True)


