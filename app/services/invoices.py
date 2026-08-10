from math import ceil

from datetime import timedelta, timezone
from decimal import Decimal
from html import escape

from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from app.config import get_private_docs_root
from app.services.audit import log_audit
from app.models.bookings import Booking
from app.utils.money import money, money_str, utcnow
from app.models.invoices import Invoice, InvoiceItem
from app.schemas.invoices import InvoiceEmailRequest, InvoiceGenerateRequest
from app.models.payments import Payment
from app.models.users import User

import logging

logger = logging.getLogger(__name__)


def _invoice_number(invoice_id: int) -> str:
    return f"TVA-INV-{invoice_id:06d}"


def split_gst_inclusive(gross_amount, gst_rate) -> tuple[Decimal, Decimal]:
    """Split a charged, GST-inclusive amount without changing its total."""
    gross = money(gross_amount)
    rate = Decimal(str(gst_rate))
    if rate < 0 or rate > 1:
        raise ValueError("GST rate must be between 0 and 1")
    if gross <= 0 or rate == 0:
        return gross, money(0)
    subtotal = money(gross / (Decimal("1") + rate))
    return subtotal, money(gross - subtotal)


def _balance_due_date(booking: Booking, requested=None):
    if requested:
        return requested
    return booking.tour_start_date


def _invoice_type(requested: str, balance_due: Decimal) -> str:
    if requested != "auto":
        return requested
    return "partial_payment" if balance_due > 0 else "full_payment"


def _traveller_names(booking: Booking) -> str:
    names = [
        (t.full_name or f"{t.first_name} {t.last_name}".strip())
        for t in (booking.travellers or [])
        if (t.full_name or t.first_name or t.last_name)
    ]
    if names:
        return ", ".join(names)
    if booking.customer and booking.customer.user:
        return booking.customer.user.name
    return "-"


def _payment_method_for(booking: Booking, payment: Payment | None) -> str:
    if payment and payment.payment_method:
        return payment.payment_method.replace("_", " ").title()
    for p in sorted(booking.payments or [], key=lambda p: p.id, reverse=True):
        if p.payment_method:
            return p.payment_method.replace("_", " ").title()
    return "Not specified"


def _build_invoice_pdf_data(inv: Invoice, booking: Booking, payment: Payment | None, items: list[dict]) -> dict:
    return {
        "invoice_number": inv.invoice_number,
        "booking_code": booking.booking_code or str(booking.id),
        "customer_name": (booking.customer.user.name if booking.customer and booking.customer.user else ""),
        "tour_name": booking.tour_name or "-",
        "traveller_names": _traveller_names(booking),
        "payment_method": _payment_method_for(booking, payment),
        "invoice_date": utcnow().strftime("%Y-%m-%d"),
        "status": inv.status or "pending",
        "currency": inv.currency,
        "subtotal_amount": money_str(inv.subtotal_amount),
        "gst_rate": money_str(inv.gst_rate),
        "gst_amount": money_str(inv.gst_amount),
        "total_amount": money_str(inv.total_amount),
        "amount_paid": money_str(inv.amount_paid),
        "amount_due": money_str(inv.amount_due),
        "balance_due_date": inv.balance_due_date.strftime("%Y-%m-%d") if inv.balance_due_date else None,
        "items": items,
    }


def serialize_invoice(inv: Invoice, detail: bool = False) -> dict:
    data = {"id": inv.id, "invoice_number": inv.invoice_number, "booking_id": inv.booking_id, "booking_code": inv.booking.booking_code if inv.booking else None, "payment_id": inv.payment_id, "customer_id": inv.customer_id, "customer_name": inv.customer.full_name if inv.customer else None, "invoice_type": inv.invoice_type, "status": inv.status, "currency": inv.currency, "subtotal_amount": money_str(inv.subtotal_amount), "gst_rate": money_str(inv.gst_rate), "gst_amount": money_str(inv.gst_amount), "total_amount": money_str(inv.total_amount), "amount_paid": money_str(inv.amount_paid), "amount_due": money_str(inv.amount_due), "balance_due_date": inv.balance_due_date, "pdf_path": inv.pdf_path, "emailed_at": inv.emailed_at, "created_at": inv.created_at, "updated_at": inv.updated_at}
    if detail:
        data["items"] = [{"id": i.id, "item_type": i.item_type, "description": i.description, "quantity": i.quantity, "unit_price": money_str(i.unit_price), "tax_amount": money_str(i.tax_amount), "total_price": money_str(i.total_price)} for i in inv.items]
    return data


def _user_role(user: User | None) -> str:
    if not user or not user.role:
        return "admin"
    slug = user.role.slug or ""
    if "supplier" in slug:
        return "supplier"
    if "agent" in slug:
        return "agent"
    if "customer" in slug:
        return "customer"
    return "admin"


def _ensure_invoice_access(inv: Invoice, actor: User | None) -> None:
    role = _user_role(actor)
    if role == "admin" or actor is None:
        return
    if role == "customer" and inv.customer and inv.customer.user_id == actor.id:
        return
    booking = inv.booking
    if role == "supplier" and booking and booking.supplier and booking.supplier.user_id == actor.id:
        return
    if role == "agent" and booking and booking.agent and booking.agent.user_id == actor.id:
        return
    raise HTTPException(status_code=403, detail="Invoice access denied")


def list_invoices(db: Session, page: int = 1, limit: int = 20, booking_id: int | None = None, customer_id: int | None = None, actor: User | None = None):
    query = db.query(Invoice)
    role = _user_role(actor)
    if role == "supplier":
        query = query.join(Invoice.booking).join(Booking.supplier).filter_by(user_id=actor.id)
    elif role == "agent":
        query = query.join(Invoice.booking).join(Booking.agent).filter_by(user_id=actor.id)
    elif role == "customer":
        query = query.join(Invoice.customer).filter_by(user_id=actor.id)
    if booking_id: query = query.filter(Invoice.booking_id == booking_id)
    if customer_id: query = query.filter(Invoice.customer_id == customer_id)
    query = query.order_by(Invoice.id.desc())
    total = query.count()
    items = [serialize_invoice(i) for i in query.offset((page - 1) * limit).limit(limit).all()]
    return {"items": items, "total": total, "page": page, "limit": limit, "total_pages": max(1, ceil(total / limit))}


def get_invoice(db: Session, invoice_id: int, actor: User | None = None) -> Invoice:
    inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")
    _ensure_invoice_access(inv, actor)
    return inv


def generate_invoice(db: Session, data: InvoiceGenerateRequest, actor: User, request: Request | None = None):
    booking = db.query(Booking).filter(Booking.id == data.booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    payment = db.query(Payment).filter(Payment.id == data.payment_id).first() if data.payment_id else None
    if payment and payment.booking_id != booking.id:
        raise HTTPException(status_code=400, detail="Payment does not belong to the specified booking")
    existing = db.query(Invoice).filter(Invoice.booking_id == booking.id, Invoice.payment_id == (payment.id if payment else None)).first()
    if existing:
        return serialize_invoice(existing, detail=True)
    booking_total = money(booking.final_amount or booking.total_cost or 0)
    paid = money(payment.captured_amount if payment else booking.amount_paid)
    invoice_total = paid if payment else booking_total
    subtotal, gst = split_gst_inclusive(invoice_total, data.gst_rate)
    balance_due = max(money(0), booking_total - money(booking.amount_paid))
    inv = Invoice(
        booking_id=booking.id,
        payment_id=payment.id if payment else None,
        customer_id=booking.customer_id,
        invoice_type=_invoice_type(data.invoice_type, balance_due),
        currency=booking.currency,
        subtotal_amount=subtotal,
        gst_rate=Decimal(str(data.gst_rate)).quantize(Decimal("0.0001")),
        gst_amount=gst,
        total_amount=invoice_total,
        amount_paid=paid,
        amount_due=balance_due,
        balance_due_date=_balance_due_date(booking, data.balance_due_date) if balance_due > 0 else None,
        created_by=actor.id,
    )
    db.add(inv)
    db.flush()
    inv.invoice_number = _invoice_number(inv.id)
    db.add(InvoiceItem(invoice_id=inv.id, item_type="booking", description=f"Booking {booking.booking_code or booking.id} - {booking.tour_name or 'Tour'}", quantity=1, unit_price=subtotal, tax_amount=gst, total_price=invoice_total))
    storage = get_private_docs_root().joinpath("invoices")
    storage.mkdir(parents=True, exist_ok=True)
    pdf_path = storage.joinpath(f"{inv.invoice_number}.pdf")
    invoice_data = _build_invoice_pdf_data(
        inv, booking, payment,
        items=[{"description": f"Booking {booking.booking_code or booking.id} - {booking.tour_name or 'Tour'}", "quantity": 1, "unit_price": money_str(subtotal), "tax_amount": money_str(gst), "total_price": money_str(invoice_total)}],
    )
    from app.utils.invoices_pdf import generate_pdf
    generate_pdf(pdf_path, invoice_data)
    inv.pdf_path = f"/private-docs/invoices/{inv.invoice_number}.pdf"
    from app.services.notifications import enqueue_notification, notify_admins
    notify_admins(db, notification_type="invoice_generated", title="Invoice generated", message=f"Invoice {inv.invoice_number} was generated", entity_type="invoice", entity_id=inv.id)
    if booking.customer and booking.customer.user_id:
        enqueue_notification(db, user_id=booking.customer.user_id, notification_type="invoice_generated", title="Invoice generated", message=f"Invoice {inv.invoice_number} is ready", entity_type="invoice", entity_id=inv.id)
    log_audit(db, actor=actor, action="generate_invoice", entity_type="invoice", entity_id=inv.id, request=request)
    db.commit()
    db.refresh(inv)
    return serialize_invoice(inv, detail=True)


def regenerate_invoice_pdf(db: Session, invoice_id: int, actor: User, request: Request | None = None):
    inv = get_invoice(db, invoice_id, actor)
    booking = inv.booking
    if not booking:
        raise HTTPException(status_code=400, detail="Invoice has no associated booking")
    storage = get_private_docs_root().joinpath("invoices")
    storage.mkdir(parents=True, exist_ok=True)
    pdf_path = storage.joinpath(f"{inv.invoice_number}.pdf")
    payment = db.query(Payment).filter(Payment.id == inv.payment_id).first() if inv.payment_id else None
    invoice_data = _build_invoice_pdf_data(
        inv, booking, payment,
        items=[{"description": i.description, "quantity": i.quantity, "unit_price": money_str(i.unit_price), "tax_amount": money_str(i.tax_amount), "total_price": money_str(i.total_price)} for i in inv.items],
    )
    from app.utils.invoices_pdf import generate_pdf
    generate_pdf(pdf_path, invoice_data)
    inv.pdf_path = f"/private-docs/invoices/{inv.invoice_number}.pdf"
    log_audit(db, actor=actor, action="regenerate_invoice_pdf", entity_type="invoice", entity_id=inv.id, request=request)
    db.commit()
    db.refresh(inv)
    return serialize_invoice(inv, detail=True)


def download_invoice_pdf(db: Session, invoice_id: int, actor: User | None = None) -> tuple[str, str]:
    """Returns (file_system_path, filename) for FileResponse."""
    from app.utils.media import resolve_private_docs_path
    inv = get_invoice(db, invoice_id, actor)
    if not inv.pdf_path:
        raise HTTPException(status_code=404, detail="PDF not yet generated for this invoice")
    fs_path = resolve_private_docs_path(inv.pdf_path, "/private-docs/")
    if not fs_path or not fs_path.exists():
        raise HTTPException(status_code=404, detail="PDF file not found on server - please regenerate")
    return str(fs_path), f"{inv.invoice_number}.pdf"


def email_invoice_to_customer(db: Session, invoice_id: int, data: InvoiceEmailRequest, actor: User, request: Request | None = None):
    inv = get_invoice(db, invoice_id, actor)
    booking = inv.booking
    recipient = data.email or (booking.customer.user.email if booking and booking.customer and booking.customer.user else None)
    if not recipient:
        raise HTTPException(status_code=400, detail="No recipient email address available")
    from app.utils.mailer import try_send_email
    subject = f"Your Invoice {inv.invoice_number} from Tourvaa"
    personal_message = f"<p>{escape(data.message)}</p>" if data.message else ""
    body = f"""
<p>Dear Customer,</p>
<p>Please find attached your invoice <b>{inv.invoice_number}</b>.</p>
{personal_message}
<p>Total Amount: <b>{inv.currency} {money_str(inv.total_amount)}</b></p>
<p>Amount Due: <b>{inv.currency} {money_str(inv.amount_due)}</b></p>
<p>Balance Due Date: <b>{inv.balance_due_date.strftime('%Y-%m-%d') if inv.balance_due_date else 'Fully paid'}</b></p>
<p>Thank you for booking with Tourvaa.</p>
"""
    attachments = []
    if inv.pdf_path:
        from app.utils.media import resolve_private_docs_path
        fs_path = resolve_private_docs_path(inv.pdf_path, "/private-docs/")
        if fs_path and fs_path.exists():
            with open(fs_path, "rb") as pdf_file:
                attachments.append((f"{inv.invoice_number}.pdf", pdf_file.read(), "pdf"))
    delivered = try_send_email(
        recipient,
        subject,
        body,
        attachments,
        template_key="invoice_emailed",
        entity_type="invoice",
        entity_id=inv.id,
    )
    if not delivered:
        raise HTTPException(status_code=502, detail="Invoice email delivery failed; check email logs")
    inv.status = "emailed"
    inv.emailed_at = utcnow()
    log_audit(db, actor=actor, action="email_invoice", entity_type="invoice", entity_id=inv.id, request=request)
    db.commit()
    db.refresh(inv)
    return serialize_invoice(inv, detail=True)


def mark_invoice_emailed(db: Session, invoice_id: int, data: InvoiceEmailRequest, actor: User, request: Request | None = None):
    from app.models.bookings import EmailLog

    inv = get_invoice(db, invoice_id, actor)
    inv.status = "emailed"
    inv.emailed_at = utcnow()
    db.add(EmailLog(recipient_email=data.email or "", subject=f"Invoice {inv.invoice_number}", template_key="invoice_sent", entity_type="invoice", entity_id=inv.id, status="sent", sent_at=utcnow()))
    from app.services.notifications import notify_admins
    notify_admins(db, notification_type="invoice_sent", title="Invoice emailed", message=f"Invoice {inv.invoice_number} was marked emailed", entity_type="invoice", entity_id=inv.id)
    log_audit(db, actor=actor, action="email_invoice", entity_type="invoice", entity_id=inv.id, request=request)
    db.commit()
    db.refresh(inv)
    return serialize_invoice(inv, detail=True)


_REMINDER_LABELS = {
    "upcoming": "is due soon",
    "due": "is due today",
    "overdue": "is overdue",
}
_OVERDUE_RESEND_INTERVAL = timedelta(days=7)


def _reminder_stage(now, due_date) -> str | None:
    """Which reminder stage `due_date` currently falls into, or None if it's
    more than 3 days away and no reminder is due yet."""
    if due_date.tzinfo is None:
        due_date = due_date.replace(tzinfo=timezone.utc)
    days_until_due = (due_date.date() - now.date()).days
    if days_until_due > 3:
        return None
    if days_until_due > 0:
        return "upcoming"
    if days_until_due == 0:
        return "due"
    return "overdue"


def check_balance_due_reminders(db: Session) -> list[int]:
    """Email/notify customers with an outstanding invoice balance as their
    `balance_due_date` approaches, arrives, or passes. Called periodically by
    the background loop in app/main.py. Sends once per stage transition;
    overdue invoices are re-reminded every _OVERDUE_RESEND_INTERVAL."""
    from app.services.notifications import enqueue_notification
    from app.utils.mailer import try_send_email

    now = utcnow()
    invoices = (
        db.query(Invoice)
        .filter(Invoice.amount_due > 0, Invoice.balance_due_date.isnot(None))
        .all()
    )
    reminded: list[int] = []
    for inv in invoices:
        stage = _reminder_stage(now, inv.balance_due_date)
        if stage is None:
            continue

        should_send = stage != inv.balance_reminder_stage
        if not should_send and stage == "overdue":
            last = inv.last_balance_reminder_at
            if last and last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            should_send = last is None or (now - last) >= _OVERDUE_RESEND_INTERVAL
        if not should_send:
            continue

        try:
            label = _REMINDER_LABELS[stage]
            due_str = inv.balance_due_date.strftime("%Y-%m-%d")
            booking_code = inv.booking.booking_code if inv.booking else inv.booking_id
            subject = f"Payment reminder: Invoice {inv.invoice_number} {label}"
            body = (
                f"<p>Your invoice <b>{inv.invoice_number}</b> for booking {booking_code} "
                f"has an outstanding balance of <b>{inv.currency} {money_str(inv.amount_due)}</b>, "
                f"due <b>{due_str}</b>.</p>"
            )
            if inv.customer and inv.customer.email:
                try_send_email(
                    inv.customer.email, subject, body,
                    template_key="balance_due_reminder", entity_type="invoice", entity_id=inv.id,
                )
            if inv.customer and inv.customer.user_id:
                enqueue_notification(
                    db, user_id=inv.customer.user_id, notification_type="balance_due_reminder",
                    title="Payment reminder",
                    message=f"Invoice {inv.invoice_number} balance of {inv.currency} {money_str(inv.amount_due)} {label}",
                    entity_type="invoice", entity_id=inv.id,
                )
            inv.balance_reminder_stage = stage
            inv.last_balance_reminder_at = now
            reminded.append(inv.id)
        except Exception:
            logger.exception("Failed to send balance-due reminder for invoice %s", inv.id)
            db.rollback()

    if reminded:
        db.commit()
    return reminded


