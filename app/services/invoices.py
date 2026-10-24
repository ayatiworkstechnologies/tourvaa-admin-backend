from math import ceil

from datetime import timedelta, timezone
from decimal import Decimal
from html import escape

from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from app.config import get_private_docs_root, settings
from app.services.audit import log_audit
from app.models.bookings import Booking
from app.models.customers import Customer
from app.utils.money import money, money_str, utcnow
from app.models.invoices import Invoice, InvoiceItem
from app.schemas.invoices import InvoiceEmailRequest, InvoiceGenerateRequest
from app.models.payments import Payment
from app.models.notifications import NotificationDelivery
from app.models.users import User

import logging

logger = logging.getLogger(__name__)

_CURRENCY_SYMBOL_FALLBACKS = {
    "USD": "$", "EUR": "€", "GBP": "£", "INR": "₹", "JPY": "¥",
    "CNY": "¥", "KRW": "₩", "AED": "د.إ", "SAR": "﷼", "QAR": "ر.ق",
}


def _currency_metadata(inv: Invoice) -> tuple[str, str]:
    """Return the invoice's immutable charged currency and display symbol.

    The database currency master is authoritative. A small fallback keeps old
    invoices readable if their currency has since been disabled or removed.
    """
    code = (inv.currency or "USD").strip().upper()
    symbol = ""
    try:
        from sqlalchemy.orm import object_session
        from app.models.cms import Currency

        session = object_session(inv)
        if session is not None:
            row = session.query(Currency.symbol).filter(Currency.code == code).first()
            symbol = (row[0] or "").strip() if row else ""
    except Exception:
        # Invoice serialization/PDF generation must not fail only because a
        # legacy currency is absent from the master table.
        symbol = ""
    return code, symbol or _CURRENCY_SYMBOL_FALLBACKS.get(code, code)


def _invoice_number(invoice_id: int) -> str:
    return str(invoice_id)


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


def _invoice_due_date(booking: Booking, requested=None):
    """The date printed on the invoice document itself -- unrelated to
    services.bookings._balance_due_date (the actual deposit/balance-payment
    deadline computation); named differently to avoid the two being confused
    for the same function."""
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
    if booking.customer:
        # full_name is always populated directly on Customer regardless of
        # whether a linked User account exists (e.g. a guest/agent-booked
        # customer has no user_id at all) - prefer it over customer.user.name,
        # which is blank for exactly that common case.
        return booking.customer.full_name or (booking.customer.user.name if booking.customer.user else "-")
    return "-"


def _payment_method_for(booking: Booking, payment: Payment | None) -> str:
    if payment and payment.payment_method:
        return payment.payment_method.replace("_", " ").title()
    for p in sorted(booking.payments or [], key=lambda p: p.id, reverse=True):
        if p.payment_method:
            return p.payment_method.replace("_", " ").title()
    return "Not specified"


def _support_contact(inv: Invoice) -> tuple[str, str]:
    """Support email + website for the invoice footer: the admin-configured
    `support_email` setting, falling back to the built-in defaults. Read-only
    (no seed/commit) because invoices are built mid-transaction."""
    from urllib.parse import urlparse
    from sqlalchemy.orm import object_session
    from sqlalchemy.orm.exc import UnmappedInstanceError
    from app.config import settings as app_settings
    from app.models.settings import AppSetting

    email = ""
    try:
        session = object_session(inv)
    except UnmappedInstanceError:
        # Keep PDF regeneration usable in isolated/unit contexts where the
        # invoice-like object is not attached to SQLAlchemy.
        session = None
    if session is not None:
        row = session.query(AppSetting).filter(AppSetting.key == "support_email").first()
        email = (row.value or "").strip() if row else ""
    host = urlparse(app_settings.FRONTEND_URL or "").netloc
    return email or "support@tourvaa.com", host or "www.tourvaa.com"


def _invoice_template_copy(inv: Invoice) -> dict[str, str]:
    """Load admin-editable copy for the fixed, compliant invoice layout."""
    from sqlalchemy.orm import object_session
    from sqlalchemy.orm.exc import UnmappedInstanceError
    from app.models.settings import AppSetting

    defaults = {
        "invoice_brand_name": "Tourvaa",
        "invoice_brand_tagline": "Curated journeys, effortlessly booked.",
        "invoice_logo_url": "",
        "invoice_header_layout": "both",
        "invoice_primary_color": "#07566A",
        "invoice_header_color": "#0B263D",
        "invoice_accent_color": "#159C96",
        "invoice_footer_thanks": "Thank you for booking with Tourvaa.",
        "invoice_footer_legal": "This is a system-generated invoice and does not require a signature.",
        "invoice_column_description": "Description", "invoice_column_quantity": "Qty", "invoice_column_unit_price": "Unit Price", "invoice_column_tax": "Tax", "invoice_column_total": "Total", "invoice_label_amount_due": "Amount Due",
    }
    try:
        session = object_session(inv)
    except UnmappedInstanceError:
        session = None
    if session is None:
        return defaults
    keys_to_query = list(defaults.keys()) + ["logo"]
    rows = session.query(AppSetting).filter(AppSetting.key.in_(keys_to_query)).all()
    values = {row.key: (row.value or "").strip() for row in rows}
    result = {key: values.get(key) or default for key, default in defaults.items()}
    if not result.get("invoice_logo_url") and values.get("logo"):
        result["invoice_logo_url"] = values["logo"]
    return result


def _build_invoice_pdf_data(inv: Invoice, booking: Booking, payment: Payment | None, items: list[dict]) -> dict:
    support_email, website = _support_contact(inv)
    currency, currency_symbol = _currency_metadata(inv)
    return {
        "support_email": support_email,
        "website": website,
        **_invoice_template_copy(inv),
        "invoice_number": inv.invoice_number,
        "booking_code": booking.booking_code or str(booking.id),
        # Same fallback as _traveller_names above: Customer.full_name is
        # always set, customer.user is only set for a customer who actually
        # has a login account.
        "customer_name": (booking.customer.full_name or (booking.customer.user.name if booking.customer.user else "")) if booking.customer else "",
        "tour_name": booking.tour_name or "-",
        "traveller_names": _traveller_names(booking),
        "payment_method": _payment_method_for(booking, payment),
        "invoice_date": utcnow().strftime("%Y-%m-%d"),
        "status": inv.status or "pending",
        "currency": currency,
        "currency_symbol": currency_symbol,
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
    currency, currency_symbol = _currency_metadata(inv)
    data = {"id": inv.id, "invoice_number": inv.invoice_number, "booking_id": inv.booking_id, "booking_code": inv.booking.booking_code if inv.booking else None, "payment_id": inv.payment_id, "customer_id": inv.customer_id, "customer_name": inv.customer.full_name if inv.customer else None, "invoice_type": inv.invoice_type, "status": inv.status, "currency": currency, "currency_symbol": currency_symbol, "subtotal_amount": money_str(inv.subtotal_amount), "gst_rate": money_str(inv.gst_rate), "gst_amount": money_str(inv.gst_amount), "total_amount": money_str(inv.total_amount), "amount_paid": money_str(inv.amount_paid), "amount_due": money_str(inv.amount_due), "balance_due_date": inv.balance_due_date, "pdf_path": inv.pdf_path, "emailed_at": inv.emailed_at, "created_at": inv.created_at, "updated_at": inv.updated_at}
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
    if actor is None:
        raise HTTPException(status_code=403, detail="Invoice access denied")
    role = _user_role(actor)
    if role == "admin":
        return
    if (
        role == "customer"
        and inv.booking
        and inv.booking.booking_source != "agent"
        and inv.customer
        and inv.customer.user_id == actor.id
    ):
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
        query = query.join(Invoice.customer).join(Invoice.booking).filter(Customer.user_id == actor.id)
        query = query.filter(Booking.booking_source != "agent")
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


def generate_invoice(db: Session, data: InvoiceGenerateRequest, actor: User | None, request: Request | None = None):
    booking = db.query(Booking).filter(Booking.id == data.booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    payment = db.query(Payment).filter(Payment.id == data.payment_id).first() if data.payment_id else None
    if payment and payment.booking_id != booking.id:
        raise HTTPException(status_code=400, detail="Payment does not belong to the specified booking")
    existing = db.query(Invoice).filter(Invoice.booking_id == booking.id, Invoice.payment_id == (payment.id if payment else None)).first()
    if existing:
        # A prior process may have committed the invoice record before its
        # private PDF was persisted, or the file may have been removed during
        # a deployment. Re-running generation must repair that record instead
        # of returning an invoice that can never be downloaded.
        try:
            download_invoice_pdf(db, existing.id, actor)
        except HTTPException as error:
            if error.status_code != 404:
                raise
            return regenerate_invoice_pdf(db, existing.id, actor, request)
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
        balance_due_date=_invoice_due_date(booking, data.balance_due_date) if balance_due > 0 else None,
        created_by=actor.id if actor else None,
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
    if booking.booking_source != "agent" and booking.customer and booking.customer.user_id:
        enqueue_notification(db, user_id=booking.customer.user_id, notification_type="invoice_generated", title="Invoice generated", message=f"Invoice {inv.invoice_number} is ready", entity_type="invoice", entity_id=inv.id)
    if booking.agent and booking.agent.user_id:
        enqueue_notification(db, user_id=booking.agent.user_id, notification_type="invoice_generated", title="Reservation invoice ready", message=f"Invoice {inv.invoice_number} for booking {booking.booking_code or booking.id} is ready", entity_type="invoice", entity_id=inv.id)
    # An invoice is a financial document: keep its recipient scoped to the
    # booking owner (agent for agent reservations, customer otherwise).
    from app.services.notification_delivery import dispatch_admin_lifecycle_emails, dispatch_lifecycle_email
    recipient_name = None
    recipient_email = None
    recipient_type = None
    recipient_url = None
    if booking.booking_source == "agent" and booking.agent and booking.agent.user:
        recipient_name, recipient_email, recipient_type = booking.agent.agent_name, booking.agent.user.email, "agent"
        recipient_url = f"{settings.FRONTEND_URL}/agent/invoices"
    elif booking.customer:
        recipient_name, recipient_email, recipient_type = booking.customer.full_name, booking.customer.email, "customer"
        recipient_url = f"{settings.FRONTEND_URL}/customer/invoices"
    invoice_values = {"name": recipient_name or "Traveller", "invoice_number": inv.invoice_number,
                      "booking_code": booking.booking_code or booking.id, "currency": inv.currency,
                      "total": money_str(inv.total_amount), "login_url": recipient_url or "",
                      "button_text": "View invoice", "button_url": recipient_url or ""}
    dispatch_lifecycle_email(
        db, event="invoice_generated", entity_type="invoice", entity_id=inv.id,
        recipient_type=recipient_type or "booking_owner", recipient_email=recipient_email,
        template_key="invoice_generated", values=invoice_values,
        fallback_subject=f"Invoice available - {inv.invoice_number}",
        fallback_html=f"<p>Invoice {inv.invoice_number} is available for booking {booking.booking_code or booking.id}.</p><p><a href='{recipient_url or ''}'>View invoice</a></p>",
        event_version=str(inv.id),
    )
    admin_url = f"{settings.FRONTEND_URL}/admin/invoices/{inv.id}"
    dispatch_admin_lifecycle_emails(
        db, event="invoice_generated", entity_type="invoice", entity_id=inv.id,
        template_key="admin_booking_event",
        values={"event_title": "Invoice generated", "detail": f"Invoice {inv.invoice_number} was generated for booking {booking.booking_code or booking.id}.",
                "booking_code": booking.booking_code or booking.id, "tour_name": booking.tour_name,
                "admin_url": admin_url, "button_text": "View invoice", "button_url": admin_url},
        fallback_subject=f"Invoice generated - {inv.invoice_number}",
        fallback_html=f"<p>Invoice {inv.invoice_number} was generated.</p><p><a href='{admin_url}'>View invoice</a></p>",
        event_version=str(inv.id),
    )
    log_audit(db, actor=actor, action="generate_invoice", entity_type="invoice", entity_id=inv.id, request=request)
    db.commit()
    db.refresh(inv)
    return serialize_invoice(inv, detail=True)


def regenerate_invoice_pdf(db: Session, invoice_id: int, actor: User | None, request: Request | None = None):
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
    def _valid_pdf(path) -> bool:
        try:
            return bool(path and path.is_file() and path.stat().st_size > 5 and path.read_bytes()[:5] == b"%PDF-")
        except OSError:
            return False

    if not _valid_pdf(fs_path):
        # PDF files are derived, private artifacts; the invoice and its line
        # items in the database are the source of truth.  A container rebuild
        # or an old host cleanup must not leave a valid invoice permanently
        # downloadable only after an administrator manually repairs it.
        logger.warning("Invoice PDF is missing; regenerating invoice_id=%s", invoice_id)
        regenerated = regenerate_invoice_pdf(db, invoice_id, actor)
        fs_path = resolve_private_docs_path(regenerated.pdf_path, "/private-docs/")
        if not _valid_pdf(fs_path):
            raise HTTPException(status_code=404, detail="PDF file could not be regenerated on server")
    return str(fs_path), f"{inv.invoice_number}.pdf"


def email_invoice_to_customer(db: Session, invoice_id: int, data: InvoiceEmailRequest, actor: User, request: Request | None = None):
    inv = get_invoice(db, invoice_id, actor)
    booking = inv.booking
    is_agent_booking = bool(booking and getattr(booking, "booking_source", None) == "agent")
    # An agent-created booking is a B2B reservation: its invoice belongs to
    # the agent, not the lead traveller. Ignore a manually supplied customer
    # address so this endpoint cannot accidentally disclose it to the party
    # travelling on the booking.
    if is_agent_booking:
        from app.models.agents import AgentInvoicing

        invoicing = db.query(AgentInvoicing).filter(AgentInvoicing.agent_id == booking.agent_id).first() if booking.agent_id else None
        recipient = (
            (invoicing.email if invoicing and invoicing.email else None)
            or (booking.agent.user.email if booking.agent and booking.agent.user and booking.agent.user.email else None)
        )
        if not recipient and booking.agent:
            recipient = next((contact.email for contact in booking.agent.contacts if contact.is_primary and contact.email), None)
    else:
        recipient = data.email or (booking.customer.user.email if booking and booking.customer and booking.customer.user else None)
    if not recipient:
        raise HTTPException(status_code=400, detail="No agent invoice email address available" if is_agent_booking else "No recipient email address available")
    from app.services.notification_delivery import dispatch_lifecycle_email
    subject = f"Your Invoice {inv.invoice_number} from Tourvaa"
    personal_message = f"<p>{escape(data.message)}</p>" if data.message else ""
    body = f"""
<p>Hello,</p>
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
    queued = dispatch_lifecycle_email(
        db, event="invoice_emailed", entity_type="invoice", entity_id=inv.id,
        recipient_type="agent" if is_agent_booking else "customer", recipient_email=recipient,
        template_key="invoice_emailed",
        values={"name": booking.agent.agent_name if is_agent_booking and booking.agent else "Customer",
                "invoice_number": inv.invoice_number, "booking_code": getattr(booking, "booking_code", inv.invoice_number),
                "currency": inv.currency, "total": money_str(inv.total_amount),
                "amount_due": money_str(inv.amount_due), "login_url": f"{settings.FRONTEND_URL}/{'agent' if is_agent_booking else 'customer'}/invoices",
                "button_text": "View invoice", "button_url": f"{settings.FRONTEND_URL}/{'agent' if is_agent_booking else 'customer'}/invoices"},
        fallback_subject=subject, fallback_html=body, attachments=attachments,
        event_version=str(getattr(inv, "updated_at", None) or inv.id),
    )
    if not queued:
        # A duplicate reservation means this invoice/version was already queued.
        existing_delivery = db.query(NotificationDelivery.id).filter(
            NotificationDelivery.entity_type == "invoice", NotificationDelivery.entity_id == inv.id,
            NotificationDelivery.event_type == "invoice_emailed", NotificationDelivery.recipient_email == recipient.lower(),
        ).first()
        if not existing_delivery:
            raise HTTPException(status_code=400, detail="No invoice email recipient could be queued")
    inv.status = "email_queued"
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
    from app.services.notification_delivery import dispatch_lifecycle_email

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
            if inv.booking and inv.booking.booking_source != "agent" and inv.customer and inv.customer.email:
                portal_url = f"{settings.FRONTEND_URL}/customer/invoices"
                event_version = stage if stage != "overdue" else f"overdue:{now.date().isoformat()}"
                dispatch_lifecycle_email(
                    db,
                    event="payment_due_reminder",
                    entity_type="invoice",
                    entity_id=inv.id,
                    recipient_type="customer",
                    recipient_email=inv.customer.email,
                    template_key="balance_due_reminder",
                    values={
                        "name": inv.customer.full_name,
                        "invoice_number": inv.invoice_number,
                        "booking_code": booking_code,
                        "currency": inv.currency,
                        "amount_due": money_str(inv.amount_due),
                        "due_date": due_str,
                        "due_label": label,
                        "login_url": portal_url,
                        "button_text": "View invoice",
                        "button_url": portal_url,
                    },
                    fallback_subject=subject,
                    fallback_html=body,
                    event_version=event_version,
                )
            if inv.booking and inv.booking.booking_source != "agent" and inv.customer and inv.customer.user_id:
                enqueue_notification(
                    db, user_id=inv.customer.user_id, notification_type="balance_due_reminder",
                    title="Payment reminder",
                    message=f"Invoice {inv.invoice_number} balance of {inv.currency} {money_str(inv.amount_due)} {label}",
                    entity_type="invoice", entity_id=inv.id,
                )
            inv.balance_reminder_stage = stage
            inv.last_balance_reminder_at = now
            db.commit()
            reminded.append(inv.id)
        except Exception:
            logger.exception("Failed to send balance-due reminder for invoice %s", inv.id)
            db.rollback()

    return reminded
