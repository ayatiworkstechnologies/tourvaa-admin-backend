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


def _invoice_type(
    requested: str = "auto",
    balance_due: Decimal = Decimal("0"),
    booking: Booking | None = None,
    payment: Payment | None = None,
) -> str:
    if requested != "auto":
        return requested
    if booking is not None:
        if booking.booking_source == "agent" and payment is None:
            return "agent_reservation_invoice"
        if balance_due > 0:
            return "deposit_receipt"
        return "payment_receipt"
    if balance_due > 0:
        return "partial_payment"
    return "full_payment"


def _ensure_document_eligibility(booking: Booking, payment: Payment | None) -> None:
    """Enforce the financial-document rules from the approved templates.

    An authorization is not money received.  Customer receipts therefore
    require a captured payment and every document waits for an accepted,
    confirmed booking.  Agent Reserve Now is the deliberate exception: it is
    a payment-request invoice with no captured payment, but still only after
    the supplier has accepted the reservation.
    """
    accepted = booking.supplier_acceptance_status == "accepted" or booking.booking_status in {
        "confirmed", "upcoming", "ongoing", "completed"
    }
    if not accepted:
        raise HTTPException(status_code=409, detail="An invoice or receipt can be issued only after supplier acceptance and booking confirmation")
    if payment is None:
        if booking.booking_source != "agent":
            raise HTTPException(status_code=409, detail="A customer financial document requires a successfully captured payment")
        return
    if payment.payment_status != "paid" or money(payment.captured_amount or payment.paid_amount or 0) <= 0:
        raise HTTPException(status_code=409, detail="An invoice or receipt cannot be issued for an authorization or unpaid payment")


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


def _recipient_snapshot(db: Session, booking: Booking) -> dict:
    """Freeze the legal financial-document recipient at issue time.

    Agent reservations are billed to the agent's invoicing/business profile,
    never to the traveller. Customer bookings remain billed to the customer.
    For each billing field, prefer Billing and Invoicing Details; if blank,
    fallback to corresponding Agent profile/primary contact, then business details.
    """
    if booking.booking_source == "agent" and booking.agent:
        from app.models.agents import AgentInvoicing

        agent = booking.agent
        invoicing = db.query(AgentInvoicing).filter(AgentInvoicing.agent_id == agent.id).first()
        business = agent.business_info
        primary = next((contact for contact in (agent.contacts or []) if contact.is_primary), None)
        address_parts = [
            invoicing.billing_address if invoicing and invoicing.billing_address else None,
            invoicing.billing_city if invoicing and invoicing.billing_city else None,
            invoicing.billing_state if invoicing and invoicing.billing_state else None,
            invoicing.billing_postal_code if invoicing and invoicing.billing_postal_code else None,
        ]
        address = ", ".join(str(part).strip() for part in address_parts if part and str(part).strip())
        if not address and business:
            bus_addr = [getattr(business, "address_line_1", None), getattr(business, "city", None), getattr(business, "country", None)]
            address = ", ".join(str(part).strip() for part in bus_addr if part and str(part).strip())

        business_name = (
            (business.trading_name if business and business.trading_name else None)
            or (business.registered_company_name if business and hasattr(business, "registered_company_name") and business.registered_company_name else None)
            or agent.agent_name
            or "Agent Partner"
        )
        contact_name = (
            (invoicing.contact_name if invoicing and invoicing.contact_name else None)
            or (primary.contact_name if primary and getattr(primary, "contact_name", None) else None)
            or (agent.user.name if agent.user else None)
        )
        email = (
            (invoicing.email if invoicing and invoicing.email else None)
            or (business.business_email if business and business.business_email else None)
            or (primary.email if primary and primary.email else None)
            or (agent.user.email if agent.user else None)
        )
        phone = (
            (invoicing.phone if invoicing and invoicing.phone else None)
            or (primary.phone if primary and primary.phone else None)
        )
        tax_number = (
            (invoicing.tax_number if invoicing and invoicing.tax_number else None)
            or (business.gst_tax_number if business and business.gst_tax_number else None)
        )
        return {
            "type": "agent",
            "label": "BILL TO",
            "business_name": business_name,
            "contact_name": contact_name,
            "name": business_name,
            "email": email or "",
            "phone": phone or "",
            "address": address or "",
            "tax_number": tax_number or "",
        }
    customer = booking.customer
    return {
        "type": "customer",
        "label": "BILL TO",
        "business_name": "",
        "contact_name": customer.full_name if customer else "",
        "name": customer.full_name if customer else "",
        "email": customer.email if customer else "",
        "phone": customer.phone if customer else "",
        "address": getattr(customer, "address", "") if customer else "",
        "tax_number": "",
    }


def _document_snapshot(db: Session, booking: Booking, payment: Payment | None, balance_due: Decimal) -> dict:
    """Create the immutable data used by every issued invoice/receipt PDF."""
    booking_total = money(booking.final_amount or booking.total_cost or 0)
    current_payment = money(payment.captured_amount or payment.paid_amount or 0) if payment else money(0)
    payment_date = getattr(payment, "updated_at", None) or getattr(payment, "created_at", None) if payment else None
    return {
        "recipient": _recipient_snapshot(db, booking),
        "booking": {
            "code": booking.booking_code or str(booking.id),
            "tour_name": booking.tour_name or "Tour",
            "traveller_names": _traveller_names(booking),
            "travel_date": str(booking.tour_start_date or booking.tour_date or ""),
            "adult_count": int(booking.adults_count or booking.no_of_adults or 0),
            "child_count": int(booking.children_count or booking.no_of_children or 0),
            "lead_traveller": next((t.full_name or f"{t.first_name} {t.last_name}".strip() for t in (booking.travellers or []) if t.is_primary_contact), _traveller_names(booking)),
            "pickup": next((t.pickup_location for t in (booking.travellers or []) if t.pickup_location), None) or booking.pickup_location or (booking.tour.start_time if booking.tour else ""),
            "booking_status": booking.booking_status,
            "payment_status": booking.payment_status,
            "total": str(booking_total),
            "tour_price": str(money(booking.base_amount or 0)),
            "addons_total": str(money((booking.optional_activity_amount or 0) + (booking.accommodation_amount or 0) + (booking.extension_amount or 0))),
            "discount_total": str(money((booking.discount_amount or 0) + (booking.group_discount_amount or 0))),
            "tax_amount": str(money(booking.tax_amount or 0)),
            "cumulative_paid": str(money(booking.amount_paid or 0)),
            "balance_due": str(balance_due),
            "balance_due_date": str(booking.payment_due_date or "") if booking.payment_due_date else "",
            "cancellation_policy": booking.cancellation_policy_snapshot or "Cancellation policy recorded with this booking.",
            "terms_url": f"{settings.FRONTEND_URL.rstrip('/')}/terms#cancellation-terms",
            "payment_link": f"{settings.FRONTEND_URL.rstrip('/')}/payments?booking_id={booking.id}",
        },
        "payment": {
            "amount": str(current_payment),
            "method": _payment_method_for(booking, payment),
            "transaction_id": (getattr(payment, "transaction_id", None) or getattr(payment, "gateway_transaction_id", None) or "") if payment else "",
            "paid_at": payment_date.isoformat() if payment_date else "",
        },
    }


def _document_line_items(booking: Booking, invoice_total: Decimal, subtotal: Decimal, gst: Decimal) -> list[dict]:
    """Customer-facing price rows only; never expose supplier settlement data.
    Format Quantity according to template requirements:
    - Total Tour Price: count of travellers
    - Add-ons / extras: count or 'Included'
    - Discount: '%'
    - Including Tax: 'Included (do not add tax amount or percentage)'
    """
    traveller_count = int(booking.adults_count or booking.no_of_adults or 1) + int(booking.children_count or booking.no_of_children or 0)
    qty_str = f"{traveller_count} traveller{'s' if traveller_count > 1 else ''}"

    rows = [{
        "description": "Total Tour Price",
        "quantity": qty_str,
        "unit_price": money_str(booking.base_amount or 0),
        "tax_amount": "0.00",
        "total_price": money_str(booking.base_amount or 0),
    }]
    addons = money((booking.optional_activity_amount or 0) + (booking.accommodation_amount or 0) + (booking.extension_amount or 0))
    if addons > 0:
        rows.append({
            "description": "Add-ons / extras",
            "quantity": "Included",
            "unit_price": money_str(addons),
            "tax_amount": "0.00",
            "total_price": money_str(addons),
        })
    discount = money((booking.discount_amount or 0) + (booking.group_discount_amount or 0))
    if discount > 0:
        rows.append({
            "description": "Discount",
            "quantity": "%",
            "unit_price": money_str(-discount),
            "tax_amount": "0.00",
            "total_price": money_str(-discount),
        })
    tax_amt = money(booking.tax_amount or gst or 0)
    if tax_amt > 0:
        rows.append({
            "description": "Including Tax",
            "quantity": "Included (do not add tax amount or percentage)",
            "unit_price": money_str(tax_amt),
            "tax_amount": "0.00",
            "total_price": money_str(tax_amt),
        })
    if not rows or money(booking.base_amount or 0) <= 0:
        rows = [{
            "description": f"Booking {booking.booking_code or booking.id} - {booking.tour_name or 'Tour'}",
            "quantity": "1",
            "unit_price": money_str(subtotal),
            "tax_amount": money_str(gst),
            "total_price": money_str(invoice_total),
        }]
    return rows


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


def _tourvaa_company_snapshot(inv: Invoice) -> dict:
    from sqlalchemy.orm import object_session
    from sqlalchemy.orm.exc import UnmappedInstanceError
    from app.models.settings import AppSetting

    defaults = {
        "legal_business_name": "Tourvaa Ltd",
        "business_address": "Level 1, 123 Queen Street, Auckland 1010, New Zealand",
        "email": "support@tourvaa.com",
        "website": "www.tourvaa.com",
        "gst_number": "",
    }
    try:
        session = object_session(inv)
    except UnmappedInstanceError:
        session = None
    if session is not None:
        keys = ["company_legal_name", "company_name", "company_address", "support_email", "company_gst_number"]
        rows = session.query(AppSetting).filter(AppSetting.key.in_(keys)).all()
        vals = {r.key: (r.value or "").strip() for r in rows}
        if vals.get("company_legal_name"):
            defaults["legal_business_name"] = vals["company_legal_name"]
        elif vals.get("company_name"):
            defaults["legal_business_name"] = vals["company_name"]
        if vals.get("company_address"):
            defaults["business_address"] = vals["company_address"]
        if vals.get("support_email"):
            defaults["email"] = vals["support_email"]
        if vals.get("company_gst_number"):
            defaults["gst_number"] = vals["company_gst_number"]
    return defaults


def _build_invoice_pdf_data(inv: Invoice, booking: Booking, payment: Payment | None, items: list[dict]) -> dict:
    support_email, website = _support_contact(inv)
    currency, currency_symbol = _currency_metadata(inv)
    tourvaa_company = _tourvaa_company_snapshot(inv)
    label = {
        "agent_reservation_invoice": "BOOKING INVOICE",
        "deposit_receipt": "BOOKING INVOICE & PAYMENT RECEIPT",
        "payment_receipt": "PAYMENT RECEIPT",
    }.get(inv.invoice_type, "INVOICE")
    snapshot = inv.document_snapshot or {}
    recipient = snapshot.get("recipient") or {}
    snapshot_booking = snapshot.get("booking") or {}
    snapshot_payment = snapshot.get("payment") or {}
    is_agent = recipient.get("type") == "agent" or booking.booking_source == "agent"
    is_booking_invoice = inv.invoice_type == "agent_reservation_invoice"
    is_deposit_document = inv.invoice_type == "deposit_receipt"
    is_full_receipt = inv.invoice_type == "payment_receipt"

    if is_booking_invoice:
        label = "AGENT BOOKING INVOICE"
    elif is_deposit_document:
        label = "CUSTOMER DEPOSIT INVOICE & PAYMENT RECEIPT"
    elif is_full_receipt:
        label = "AGENT FULL PAYMENT RECEIPT" if is_agent else "CUSTOMER FULL PAYMENT RECEIPT"
    return {
        "support_email": support_email,
        "website": website,
        **_invoice_template_copy(inv),
        "tourvaa_legal_business_name": tourvaa_company["legal_business_name"],
        "tourvaa_business_address": tourvaa_company["business_address"],
        "tourvaa_email": tourvaa_company["email"],
        "tourvaa_website": tourvaa_company["website"],
        "tourvaa_gst_number": tourvaa_company["gst_number"],
        "is_booking_invoice": is_booking_invoice,
        "is_deposit_document": is_deposit_document,
        "is_full_receipt": is_full_receipt,
        "is_agent": is_agent,
        "invoice_number": inv.invoice_number,
        "document_label": label,
        "booking_code": booking.booking_code or str(booking.id),
        "recipient_label": recipient.get("label") or "BILL TO",
        "recipient_business_name": recipient.get("business_name") or "",
        "recipient_contact_name": recipient.get("contact_name") or "",
        "customer_name": recipient.get("name") or ((booking.customer.full_name or (booking.customer.user.name if booking.customer.user else "")) if booking.customer else ""),
        "recipient_email": recipient.get("email") or "",
        "recipient_phone": recipient.get("phone") or "",
        "recipient_address": recipient.get("address") or "",
        "recipient_tax_number": recipient.get("tax_number") or "",
        "tour_name": snapshot_booking.get("tour_name") or booking.tour_name or "-",
        "traveller_names": snapshot_booking.get("traveller_names") or _traveller_names(booking),
        "travel_date": snapshot_booking.get("travel_date") or "",
        "adult_count": snapshot_booking.get("adult_count") or 0,
        "child_count": snapshot_booking.get("child_count") or 0,
        "lead_traveller": snapshot_booking.get("lead_traveller") or "",
        "pickup": snapshot_booking.get("pickup") or "",
        "tour_price": snapshot_booking.get("tour_price") or "",
        "addons_total": snapshot_booking.get("addons_total") or "",
        "discount_total": snapshot_booking.get("discount_total") or "",
        "tax_included": snapshot_booking.get("tax_amount") or "",
        "payment_link": snapshot_booking.get("payment_link") or "",
        "payment_method": snapshot_payment.get("method") or _payment_method_for(booking, payment),
        "transaction_id": snapshot_payment.get("transaction_id") or "",
        "payment_date": snapshot_payment.get("paid_at") or "",
        "booking_total": snapshot_booking.get("total") or money_str(booking.final_amount or booking.total_cost),
        "cumulative_paid": snapshot_booking.get("cumulative_paid") or money_str(booking.amount_paid),
        "cancellation_policy": snapshot_booking.get("cancellation_policy") or "",
        "terms_url": snapshot_booking.get("terms_url") or "",
        "payment_status": booking.payment_status,
        "booking_status": booking.booking_status,
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
        "balance_due_date": snapshot_booking.get("balance_due_date") or (inv.balance_due_date.strftime("%Y-%m-%d") if inv.balance_due_date else None),
        "items": items,
    }


def serialize_invoice(inv: Invoice, detail: bool = False) -> dict:
    currency, currency_symbol = _currency_metadata(inv)
    data = {"id": inv.id, "invoice_number": inv.invoice_number, "booking_id": inv.booking_id, "booking_code": inv.booking.booking_code if inv.booking else None, "payment_id": inv.payment_id, "customer_id": inv.customer_id, "customer_name": inv.customer.full_name if inv.customer else None, "recipient_type": inv.recipient_type, "invoice_type": inv.invoice_type, "status": inv.status, "currency": currency, "currency_symbol": currency_symbol, "subtotal_amount": money_str(inv.subtotal_amount), "gst_rate": money_str(inv.gst_rate), "gst_amount": money_str(inv.gst_amount), "total_amount": money_str(inv.total_amount), "amount_paid": money_str(inv.amount_paid), "amount_due": money_str(inv.amount_due), "balance_due_date": inv.balance_due_date, "pdf_path": inv.pdf_path, "emailed_at": inv.emailed_at, "created_at": inv.created_at, "updated_at": inv.updated_at}
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
    if role == "agent" and booking and booking.agent and booking.agent.user_id == actor.id:
        return
    raise HTTPException(status_code=403, detail="Invoice access denied")


def list_invoices(db: Session, page: int = 1, limit: int = 20, booking_id: int | None = None, customer_id: int | None = None, actor: User | None = None):
    query = db.query(Invoice)
    role = _user_role(actor)
    if role == "supplier":
        # Financial documents are intentionally unavailable to suppliers:
        # they must never see customer/agent billing or Tourvaa margins.
        return {"items": [], "total": 0, "page": page, "limit": limit, "total_pages": 1}
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
    _ensure_document_eligibility(booking, payment)
    existing = db.query(Invoice).filter(Invoice.booking_id == booking.id, Invoice.payment_id == (payment.id if payment else None)).first()
    if existing:
        # Upgrade legacy records in place. Earlier records used generic types
        # and had no immutable recipient/policy snapshot; a reissue must not
        # preserve an outdated document merely because the ID already exists.
        if not existing.document_snapshot:
            booking_total = money(booking.final_amount or booking.total_cost or 0)
            balance_due = max(money(0), booking_total - money(booking.amount_paid))
            snapshot = _document_snapshot(db, booking, payment, balance_due)
            existing.recipient_type = snapshot["recipient"]["type"]
            existing.document_snapshot = snapshot
            existing.invoice_type = _invoice_type(data.invoice_type, balance_due, booking, payment)
            existing.amount_paid = money(payment.captured_amount if payment else booking.amount_paid)
            existing.amount_due = balance_due
            existing.balance_due_date = _invoice_due_date(booking, data.balance_due_date) if balance_due > 0 else None
            db.add(existing)
            db.commit()
            return regenerate_invoice_pdf(db, existing.id, actor, request)
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
    snapshot = _document_snapshot(db, booking, payment, balance_due)
    inv = Invoice(
        booking_id=booking.id,
        payment_id=payment.id if payment else None,
        customer_id=booking.customer_id,
        recipient_type=snapshot["recipient"]["type"],
        document_snapshot=snapshot,
        invoice_type=_invoice_type(data.invoice_type, balance_due, booking, payment),
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
    document_items = _document_line_items(booking, invoice_total, subtotal, gst)
    for item in document_items:
        db.add(InvoiceItem(invoice_id=inv.id, item_type="booking", description=item["description"], quantity=item["quantity"], unit_price=item["unit_price"], tax_amount=item["tax_amount"], total_price=item["total_price"]))
    storage = get_private_docs_root().joinpath("invoices")
    storage.mkdir(parents=True, exist_ok=True)
    pdf_path = storage.joinpath(f"{inv.invoice_number}.pdf")
    invoice_data = _build_invoice_pdf_data(
        inv, booking, payment,
        items=document_items,
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
    snapshot_recipient = (inv.document_snapshot or {}).get("recipient") or {}
    if booking.booking_source == "agent" and booking.agent:
        recipient_name = snapshot_recipient.get("name") or booking.agent.agent_name
        recipient_email = snapshot_recipient.get("email") or (booking.agent.user.email if booking.agent.user else None)
        recipient_type = "agent"
        recipient_url = f"{settings.FRONTEND_URL}/agent/invoices"
    elif booking.customer:
        recipient_name, recipient_email, recipient_type = booking.customer.full_name, booking.customer.email, "customer"
        recipient_url = f"{settings.FRONTEND_URL}/customer/invoices"
    invoice_values = {"name": recipient_name or "Traveller", "invoice_number": inv.invoice_number,
                      "booking_code": booking.booking_code or booking.id, "currency": inv.currency,
                      "total": money_str(inv.total_amount), "login_url": recipient_url or "",
                      "button_text": "View invoice", "button_url": recipient_url or ""}
    # The issued PDF goes to the legal recipient only. A portal link remains
    # available, but an email client must not require a later download to
    # retain the exact receipt that was sent at issue time.
    generated_attachments = []
    if inv.pdf_path:
        from app.utils.media import resolve_private_docs_path
        generated_pdf = resolve_private_docs_path(inv.pdf_path, "/private-docs/")
        if generated_pdf and generated_pdf.is_file():
            generated_attachments.append((f"{inv.invoice_number}.pdf", generated_pdf.read_bytes(), "pdf"))
    dispatch_lifecycle_email(
        db, event="invoice_generated", entity_type="invoice", entity_id=inv.id,
        recipient_type=recipient_type or "booking_owner", recipient_email=recipient_email,
        template_key="invoice_generated", values=invoice_values,
        fallback_subject=f"Invoice available - {inv.invoice_number}",
        fallback_html=f"<p>Invoice {inv.invoice_number} is available for booking {booking.booking_code or booking.id}.</p><p><a href='{recipient_url or ''}'>View invoice</a></p>",
        event_version=str(inv.id), attachments=generated_attachments,
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
        recipient = (inv.document_snapshot or {}).get("recipient", {}).get("email") or (
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
