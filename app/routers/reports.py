import csv
import io
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models.agents import Agent
from app.models.audit import AuditLog
from app.services.audit import log_audit
from app.models.bookings import Booking
from app.models.cms import City, Country, Tour, TourCategory
from app.models.cancellations import CancellationRequest
from app.models.reviews import TourReview
from app.models.supplier_ledger import SupplierLedger, SupplierPayout, SupplierPayoutItem
from app.auth.permissions import require_any_permission
from app.utils.money import money_str, utcnow
from app.models.customers import Customer
from app.models.invoices import Invoice
from app.models.payments import Payment
from app.models.reports import ReportSchedule
from app.models.suppliers import Supplier
from app.models.users import User
from pydantic import BaseModel

router = APIRouter(prefix="/reports", tags=["Reports"])
logger = logging.getLogger(__name__)

PERIODS = {"day", "week", "month", "quarter", "half_year", "year", "custom", "all"}


def _scheduled_report_count(db: Session) -> int:
    # report_schedules (migration 20260728_0050) may not exist yet on every
    # deployed database; degrade to 0 instead of a 500 until that migration
    # has run everywhere.
    try:
        return db.query(func.count(ReportSchedule.id)).filter(ReportSchedule.is_active == True).scalar() or 0  # noqa: E712
    except SQLAlchemyError:
        logger.exception("Failed to count report schedules")
        return 0


def _report_role(actor: User | None) -> str:
    if not actor or not actor.role:
        return "admin"
    slug = actor.role.slug or ""
    if "supplier" in slug:
        return "supplier"
    if "agent" in slug:
        return "agent"
    return "admin"


def _scope_bookings(query, db: Session, actor: User | None):
    """Restrict a Booking-based query to the caller's own tenant for supplier/agent roles."""
    role = _report_role(actor)
    if role == "supplier":
        supplier = db.query(Supplier).filter(Supplier.user_id == actor.id).first()
        return query.filter(Booking.supplier_id == (supplier.id if supplier else -1))
    if role == "agent":
        agent = db.query(Agent).filter(Agent.user_id == actor.id).first()
        return query.filter(Booking.agent_id == (agent.id if agent else -1))
    return query


def _require_admin_report(actor: User | None):
    if _report_role(actor) != "admin":
        raise HTTPException(status_code=403, detail="This report is restricted to administrators")


def _money(value):
    return money_str(value or 0)


def _period_range(period: str, start_date: str = "", end_date: str = ""):
    """Return (start, end) datetimes for the given calendar-aligned period, or
    None for a bound that shouldn't be filtered (e.g. "all", or a custom bound
    left blank)."""
    now = utcnow()
    period = (period or "all").strip().lower()

    if period == "custom":
        start = _parse_date(start_date) if start_date else None
        end = _parse_date(end_date, end_of_day=True) if end_date else None
        return start, end

    if period == "day":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "week":
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        start = today - timedelta(days=today.weekday())
    elif period == "month":
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    elif period == "quarter":
        quarter_start_month = ((now.month - 1) // 3) * 3 + 1
        start = now.replace(month=quarter_start_month, day=1, hour=0, minute=0, second=0, microsecond=0)
    elif period == "half_year":
        half_start_month = 1 if now.month <= 6 else 7
        start = now.replace(month=half_start_month, day=1, hour=0, minute=0, second=0, microsecond=0)
    elif period == "year":
        start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        return None, None

    return start, now


def _parse_date(value: str, end_of_day: bool = False):
    dt = datetime.strptime(value.strip(), "%Y-%m-%d").replace(tzinfo=timezone.utc)
    if end_of_day:
        dt = dt.replace(hour=23, minute=59, second=59)
    return dt


def _apply_range(query, column, start, end):
    if start is not None:
        query = query.filter(column >= start)
    if end is not None:
        query = query.filter(column <= end)
    return query


def _period_params(
    period: str = Query(default="all", description="day|week|month|quarter|half_year|year|custom|all"),
    start_date: str = Query(default=""),
    end_date: str = Query(default=""),
):
    if period not in PERIODS:
        raise HTTPException(status_code=400, detail=f"period must be one of {sorted(PERIODS)}")
    start, end = _period_range(period, start_date, end_date)
    return {"period": period, "start": start, "end": end}


@router.get("/summary")
def summary(params: dict = Depends(_period_params), db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("reports.view"))):
    start, end = params["start"], params["end"]
    bookings_q = _scope_bookings(_apply_range(db.query(Booking), Booking.created_at, start, end), db, current_user)
    payments_q = _apply_range(db.query(Payment).filter(Payment.payment_status.notin_(["voided", "failed"])), Payment.created_at, start, end)
    if _report_role(current_user) != "admin":
        payments_q = payments_q.join(Booking, Payment.booking_id == Booking.id)
        payments_q = _scope_bookings(payments_q, db, current_user)

    total_bookings = bookings_q.with_entities(func.count(Booking.id)).scalar() or 0
    confirmed = bookings_q.filter(Booking.booking_status == "confirmed").with_entities(func.count(Booking.id)).scalar() or 0
    cancelled = bookings_q.filter(Booking.booking_status == "cancelled").with_entities(func.count(Booking.id)).scalar() or 0
    # Net of refunds - captured_amount is left unchanged by a refund (only
    # refunded_amount and payment_status change, see services/payments.py
    # process_refund), so it must be subtracted here or a refunded booking's
    # original charge keeps counting as revenue.
    captured = payments_q.with_entities(func.coalesce(func.sum(Payment.captured_amount), 0)).scalar() or 0
    refunded = payments_q.with_entities(func.coalesce(func.sum(Payment.refunded_amount), 0)).scalar() or 0
    revenue = max(0, captured - refunded)
    pending = bookings_q.with_entities(func.coalesce(func.sum(Booking.amount_pending), 0)).scalar() or 0
    invoice_q = _apply_range(db.query(Invoice), Invoice.created_at, start, end)
    if _report_role(current_user) != "admin":
        invoice_q = invoice_q.join(Booking, Invoice.booking_id == Booking.id)
        invoice_q = _scope_bookings(invoice_q, db, current_user)
    invoice_total = invoice_q.with_entities(func.coalesce(func.sum(Invoice.total_amount), 0)).scalar() or 0
    return {"status": "success", "data": {"total_bookings": total_bookings, "confirmed_bookings": confirmed, "cancelled_bookings": cancelled, "captured_revenue": _money(revenue), "pending_payments": _money(pending), "invoice_total": _money(invoice_total)}}


@router.get("/bookings")
def booking_report(params: dict = Depends(_period_params), db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("reports.view", "reports.admin"))):
    query = _scope_bookings(_apply_range(db.query(Booking), Booking.created_at, params["start"], params["end"]), db, current_user)
    rows = query.with_entities(Booking.booking_status, func.count(Booking.id), func.coalesce(func.sum(Booking.final_amount), 0)).group_by(Booking.booking_status).all()
    return {"status": "success", "data": [{"status": status, "count": count, "amount": _money(amount)} for status, count, amount in rows]}


@router.get("/payments")
def payment_report(params: dict = Depends(_period_params), db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("reports.view", "reports.admin"))):
    query = _apply_range(db.query(Payment), Payment.created_at, params["start"], params["end"])
    if _report_role(current_user) != "admin":
        query = _scope_bookings(query.join(Booking, Payment.booking_id == Booking.id), db, current_user)
    rows = query.with_entities(Payment.payment_status, func.count(Payment.id), func.coalesce(func.sum(Payment.captured_amount), 0), func.coalesce(func.sum(Payment.refunded_amount), 0)).group_by(Payment.payment_status).all()
    return {"status": "success", "data": [{"status": status, "count": count, "captured": _money(captured), "refunded": _money(refunded)} for status, count, captured, refunded in rows]}


@router.get("/pending-payments")
def pending_payments(db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("reports.view", "reports.admin"))):
    query = _scope_bookings(db.query(Booking).filter(Booking.amount_pending > 0), db, current_user)
    rows = query.order_by(Booking.amount_pending.desc()).limit(200).all()
    return {"status": "success", "data": [{"booking_id": b.id, "booking_code": b.booking_code, "customer_id": b.customer_id, "amount_pending": _money(b.amount_pending), "payment_status": b.payment_status} for b in rows]}


@router.get("/overdue-payments")
def overdue_payments(db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("reports.view", "reports.admin"))):
    today = utcnow().date()
    query = _scope_bookings(db.query(Booking).filter(Booking.amount_pending > 0, Booking.tour_start_date != None, func.date(Booking.tour_start_date) <= today), db, current_user)
    rows = query.order_by(Booking.tour_start_date.asc()).limit(200).all()
    return {"status": "success", "data": [{"booking_id": b.id, "booking_code": b.booking_code, "tour_start_date": b.tour_start_date, "amount_pending": _money(b.amount_pending)} for b in rows]}


@router.get("/country-wise")
def country_wise(params: dict = Depends(_period_params), db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("reports.view", "reports.admin"))):
    query = db.query(Country.country_name, func.count(Booking.id), func.coalesce(func.sum(Booking.final_amount), 0)).join(Booking, Booking.country_id == Country.id, isouter=True)
    query = _apply_range(query, Booking.created_at, params["start"], params["end"])
    query = _scope_bookings(query, db, current_user)
    rows = query.group_by(Country.country_name).all()
    return {"status": "success", "data": [{"country": country, "bookings": count, "amount": _money(amount)} for country, count, amount in rows]}


@router.get("/cancellations")
def cancellations(params: dict = Depends(_period_params), db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("reports.view", "reports.admin"))):
    query = db.query(Booking).filter(Booking.booking_status == "cancelled")
    query = _apply_range(query, Booking.cancelled_at, params["start"], params["end"])
    query = _scope_bookings(query, db, current_user)
    rows = query.order_by(Booking.cancelled_at.desc()).limit(200).all()
    return {"status": "success", "data": [{"booking_id": b.id, "booking_code": b.booking_code, "reason": b.cancellation_reason, "cancelled_at": b.cancelled_at, "amount": _money(b.final_amount)} for b in rows]}


@router.get("/suppliers")
def supplier_report(
    params: dict = Depends(_period_params),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_permission("reports.view", "reports.supplier", "reports.admin")),
):
    _require_admin_report(current_user)
    query = db.query(Supplier.id, Supplier.supplier_name, func.count(Booking.id), func.coalesce(func.sum(Booking.final_amount), 0)).join(Booking, Booking.supplier_id == Supplier.id, isouter=True)
    query = _apply_range(query, Booking.created_at, params["start"], params["end"])
    rows = query.group_by(Supplier.id, Supplier.supplier_name).all()
    return {"status": "success", "data": [{"supplier_id": sid, "supplier_name": name, "bookings": count, "amount": _money(amount)} for sid, name, count, amount in rows]}


@router.get("/agents")
def agent_report(params: dict = Depends(_period_params), db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("reports.view", "reports.agent", "reports.admin"))):
    _require_admin_report(current_user)
    query = db.query(Agent.id, Agent.agent_name, func.count(Booking.id), func.coalesce(func.sum(Booking.final_amount), 0)).join(Booking, Booking.agent_id == Agent.id, isouter=True)
    query = _apply_range(query, Booking.created_at, params["start"], params["end"])
    rows = query.group_by(Agent.id, Agent.agent_name).all()
    return {"status": "success", "data": [{"agent_id": aid, "agent_name": name, "bookings": count, "amount": _money(amount)} for aid, name, count, amount in rows]}


@router.get("/customers")
def customer_report(params: dict = Depends(_period_params), db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("reports.view", "reports.admin"))):
    _require_admin_report(current_user)
    query = db.query(Customer.id, Customer.full_name, func.count(Booking.id), func.coalesce(func.sum(Booking.final_amount), 0), func.coalesce(func.sum(Booking.amount_pending), 0)).join(Booking, Booking.customer_id == Customer.id, isouter=True)
    query = _apply_range(query, Booking.created_at, params["start"], params["end"])
    rows = query.group_by(Customer.id, Customer.full_name).all()
    return {"status": "success", "data": [{"customer_id": cid, "customer_name": name, "bookings": count, "amount": _money(amount), "pending": _money(pending)} for cid, name, count, amount, pending in rows]}


ROW_REPORT_LIMIT = 500


def _adult_child_counts(b: Booking) -> tuple[int, int]:
    # Two parallel pairs of columns exist on Booking - adults_count/children_count
    # is the one services/bookings.py prefers when both are populated.
    adults = b.adults_count if b.adults_count is not None else b.no_of_adults
    children = b.children_count if b.children_count is not None else b.no_of_children
    return adults or 0, children or 0


@router.get("/booking-report")
def booking_detail_report(
    params: dict = Depends(_period_params),
    booking_status: str = Query(default=""),
    payment_status: str = Query(default=""),
    country_id: int | None = Query(default=None),
    supplier_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_permission("reports.view", "reports.admin")),
):
    _require_admin_report(current_user)
    query = _apply_range(
        db.query(Booking).options(joinedload(Booking.customer), joinedload(Booking.agent), joinedload(Booking.tour), joinedload(Booking.supplier)),
        Booking.created_at, params["start"], params["end"],
    )
    if booking_status:
        query = query.filter(Booking.booking_status == booking_status.strip().lower())
    if payment_status:
        query = query.filter(Booking.payment_status == payment_status.strip().lower())
    if country_id:
        query = query.filter(Booking.country_id == country_id)
    if supplier_id:
        query = query.filter(Booking.supplier_id == supplier_id)
    rows = query.order_by(Booking.created_at.desc()).limit(ROW_REPORT_LIMIT).all()

    data = []
    for b in rows:
        adults, children = _adult_child_counts(b)
        data.append({
            "booking_id": b.id,
            "booking_code": b.booking_code,
            "booking_date": b.created_at,
            "customer_or_agent": (b.agent.agent_name if b.agent else None) or (b.customer.full_name if b.customer else None) or "-",
            "tour_name": b.tour.title if b.tour else b.tour_name,
            "supplier": b.supplier.supplier_name if b.supplier else b.supplier_name,
            "travel_date": b.tour_start_date or b.tour_date,
            "adults": adults,
            "children": children,
            "booking_amount": _money(b.final_amount),
            "payment_status": b.payment_status,
            "booking_status": b.booking_status,
            "cancellation_status": "cancelled" if b.booking_status == "cancelled" else "-",
        })
    return {"status": "success", "data": data}


@router.get("/sales-revenue-report")
def sales_revenue_report(
    params: dict = Depends(_period_params),
    granularity: str = Query(default="day", description="day|week|month"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_permission("reports.view", "reports.admin")),
):
    _require_admin_report(current_user)
    start, end = params["start"], params["end"]
    booking_q = _apply_range(db.query(Booking), Booking.created_at, start, end)
    payment_q = _apply_range(db.query(Payment).filter(Payment.payment_status.notin_(["voided", "failed"])), Payment.created_at, start, end)

    total_bookings = booking_q.with_entities(func.count(Booking.id)).scalar() or 0
    gross_booking_value = float(booking_q.with_entities(func.coalesce(func.sum(Booking.final_amount), 0)).scalar() or 0)
    discounts = float(booking_q.with_entities(func.coalesce(func.sum(Booking.discount_amount), 0)).scalar() or 0)
    taxes = float(booking_q.with_entities(func.coalesce(func.sum(Booking.tax_amount), 0)).scalar() or 0)

    ledger_q = db.query(SupplierLedger).join(Booking, SupplierLedger.booking_id == Booking.id)
    ledger_q = _apply_range(ledger_q, Booking.created_at, start, end)
    platform_commission = float(ledger_q.with_entities(func.coalesce(func.sum(SupplierLedger.commission_amount), 0)).scalar() or 0)
    supplier_payable = float(ledger_q.with_entities(func.coalesce(func.sum(SupplierLedger.net_payable), 0)).scalar() or 0)

    captured = float(payment_q.with_entities(func.coalesce(func.sum(Payment.captured_amount), 0)).scalar() or 0)
    refunded = float(payment_q.with_entities(func.coalesce(func.sum(Payment.refunded_amount), 0)).scalar() or 0)
    net_platform_revenue = max(0.0, captured - refunded)

    # Daily/weekly/monthly sales breakdown, bucketed on the payment date.
    if granularity not in {"day", "week", "month"}:
        raise HTTPException(status_code=400, detail="granularity must be one of day, week, month")
    if granularity == "day":
        bucket = func.date(Payment.created_at)
    elif granularity == "week":
        bucket = func.date_format(Payment.created_at, "%Y-%u")
    else:
        bucket = func.date_format(Payment.created_at, "%Y-%m")
    series_rows = (
        payment_q.with_entities(bucket.label("bucket"), func.coalesce(func.sum(Payment.captured_amount), 0))
        .group_by(bucket)
        .order_by(bucket)
        .all()
    )
    time_series = [{"period": str(bucket_value), "sales": _money(amount)} for bucket_value, amount in series_rows]

    return {
        "status": "success",
        "data": {
            "total_bookings": total_bookings,
            "gross_booking_value": _money(gross_booking_value),
            "discounts": _money(discounts),
            "taxes": _money(taxes),
            "platform_commission": _money(platform_commission),
            "supplier_payable": _money(supplier_payable),
            "refund_amount": _money(refunded),
            "net_platform_revenue": _money(net_platform_revenue),
            "granularity": granularity,
            "time_series": time_series,
        },
    }


@router.get("/payment-report")
def payment_detail_report(
    params: dict = Depends(_period_params),
    payment_status: str = Query(default=""),
    gateway: str = Query(default=""),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_permission("reports.view", "reports.admin")),
):
    _require_admin_report(current_user)
    query = _apply_range(db.query(Payment), Payment.created_at, params["start"], params["end"])
    if payment_status:
        query = query.filter(Payment.payment_status == payment_status.strip().lower())
    if gateway:
        query = query.filter(Payment.gateway == gateway.strip().lower())
    rows = query.order_by(Payment.created_at.desc()).limit(ROW_REPORT_LIMIT).all()

    data = []
    for p in rows:
        refund_status = "refunded" if p.payment_status == "refunded" else "partially_refunded" if p.payment_status == "partially_refunded" else "none"
        data.append({
            "transaction_id": p.transaction_id or p.gateway_payment_id,
            "booking_id": p.booking_id,
            "payment_gateway": p.gateway,
            "payment_method": p.payment_method,
            "paid_amount": _money(p.captured_amount or p.paid_amount),
            "payment_date": p.payment_date or p.created_at,
            "payment_status": p.payment_status,
            "failed_payment_reason": p.failure_reason,
            "refund_status": refund_status,
        })
    return {"status": "success", "data": data}


@router.get("/supplier-report")
def supplier_detail_report(
    params: dict = Depends(_period_params),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_permission("reports.view", "reports.admin")),
):
    _require_admin_report(current_user)
    suppliers = db.query(Supplier).all()
    data = []
    for s in suppliers:
        booking_q = _apply_range(db.query(Booking).filter(Booking.supplier_id == s.id), Booking.created_at, params["start"], params["end"])
        total_bookings = booking_q.with_entities(func.count(Booking.id)).scalar() or 0
        gross_sales = booking_q.with_entities(func.coalesce(func.sum(Booking.final_amount), 0)).scalar() or 0
        active_tours = db.query(func.count(Tour.id)).filter(Tour.supplier_id == s.id, Tour.status == "published").scalar() or 0

        ledger_q = _apply_range(db.query(SupplierLedger).filter(SupplierLedger.supplier_id == s.id), SupplierLedger.created_at, params["start"], params["end"])
        commission_deducted = ledger_q.with_entities(func.coalesce(func.sum(SupplierLedger.commission_amount), 0)).scalar() or 0
        amount_paid = ledger_q.with_entities(func.coalesce(func.sum(SupplierLedger.amount_paid), 0)).scalar() or 0
        outstanding_payable = ledger_q.with_entities(func.coalesce(func.sum(SupplierLedger.amount_pending), 0)).scalar() or 0

        data.append({
            "supplier_name": s.supplier_name,
            # No distinct "company name" field exists on Supplier - the
            # supplier's own name IS the company name in this data model.
            "company_name": s.supplier_name,
            "registration_date": s.created_at,
            "verification_status": s.approval_status,
            "active_tours": active_tours,
            "total_bookings": total_bookings,
            "gross_sales": _money(gross_sales),
            "commission_deducted": _money(commission_deducted),
            "amount_paid": _money(amount_paid),
            "outstanding_payable": _money(outstanding_payable),
            "supplier_status": s.status,
        })
    return {"status": "success", "data": data}


@router.get("/supplier-payout-report")
def supplier_payout_report(
    status: str = Query(default=""),
    supplier_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_permission("reports.view", "reports.admin")),
):
    _require_admin_report(current_user)
    query = db.query(SupplierPayout).options(joinedload(SupplierPayout.supplier))
    if status:
        query = query.filter(SupplierPayout.status == status.strip().lower())
    if supplier_id:
        query = query.filter(SupplierPayout.supplier_id == supplier_id)
    payouts = query.order_by(SupplierPayout.created_at.desc()).limit(ROW_REPORT_LIMIT).all()

    data = []
    for payout in payouts:
        items = (
            db.query(SupplierLedger)
            .join(SupplierPayoutItem, SupplierPayoutItem.ledger_id == SupplierLedger.id)
            .filter(SupplierPayoutItem.payout_id == payout.id)
            .options(joinedload(SupplierLedger.booking))
            .all()
        )
        total_booking_amount = sum(float(item.gross_amount or 0) for item in items)
        commission = sum(float(item.commission_amount or 0) for item in items)
        booking_dates = [item.booking.created_at for item in items if item.booking and item.booking.created_at]
        payout_period = f"{min(booking_dates).date()} - {max(booking_dates).date()}" if booking_dates else str(payout.created_at.date())

        data.append({
            "payout_id": payout.payout_code or payout.id,
            "supplier": payout.supplier.supplier_name if payout.supplier else None,
            "payout_period": payout_period,
            "total_booking_amount": _money(total_booking_amount),
            "commission": _money(commission),
            # No adjustment/refund-deduction line-item model exists on
            # supplier payouts today - a refund against an already-paid
            # ledger row is only flagged in a free-text note (see
            # services/supplier_ledger.py reverse_ledger_entry), not
            # itemized as a numeric deduction, so these are honestly 0
            # rather than a fabricated figure.
            "refund_deductions": _money(0),
            "other_adjustments": _money(0),
            "net_payable": _money(payout.total_amount),
            "payment_reference": payout.reference_number,
            "payout_status": payout.status,
            "paid_date": payout.paid_at,
        })
    return {"status": "success", "data": data}


@router.get("/tour-performance-report")
def tour_performance_report(
    supplier_id: int | None = Query(default=None),
    category_id: int | None = Query(default=None),
    country_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_permission("reports.view", "reports.admin")),
):
    _require_admin_report(current_user)
    query = db.query(Tour).options(joinedload(Tour.supplier), joinedload(Tour.country), joinedload(Tour.city), joinedload(Tour.category))
    if supplier_id:
        query = query.filter(Tour.supplier_id == supplier_id)
    if category_id:
        query = query.filter(Tour.category_id == category_id)
    if country_id:
        query = query.filter(Tour.country_id == country_id)
    tours = query.order_by(Tour.id.desc()).limit(ROW_REPORT_LIMIT).all()

    data = []
    for tour in tours:
        booking_q = db.query(Booking).filter(Booking.tour_id == tour.id)
        total_bookings = booking_q.with_entities(func.count(Booking.id)).scalar() or 0
        cancelled_bookings = booking_q.filter(Booking.booking_status == "cancelled").with_entities(func.count(Booking.id)).scalar() or 0
        confirmed_travellers = (
            booking_q.filter(Booking.booking_status.in_(["confirmed", "ongoing", "completed"]))
            .with_entities(func.coalesce(func.sum(Booking.total_travellers), 0))
            .scalar() or 0
        )
        revenue = booking_q.with_entities(func.coalesce(func.sum(Booking.final_amount), 0)).scalar() or 0
        cancellation_rate = round((cancelled_bookings / total_bookings * 100) if total_bookings else 0, 1)
        avg_rating = db.query(func.avg(TourReview.rating)).filter(TourReview.tour_id == tour.id, TourReview.status == "approved").scalar()

        data.append({
            "tour_name": tour.title,
            "supplier": tour.supplier.supplier_name if tour.supplier else None,
            "destination": ", ".join(filter(None, [tour.city.city_name if tour.city else None, tour.country.country_name if tour.country else None])),
            "category": tour.category.category_name if tour.category else None,
            # No page-view or tour-scoped enquiry tracking exists anywhere in
            # the codebase today - shown honestly as "Not tracked" rather
            # than a fabricated number, same for the conversion rate that
            # depends on views.
            "views": "Not tracked",
            "enquiries": "Not tracked",
            "bookings": total_bookings,
            "confirmed_travellers": confirmed_travellers,
            "booking_conversion_rate": "Not tracked",
            "cancellation_rate": f"{cancellation_rate}%",
            "revenue": _money(revenue),
            "average_rating": round(float(avg_rating), 1) if avg_rating is not None else None,
        })
    return {"status": "success", "data": data}


@router.get("/cancellation-refund-report")
def cancellation_refund_report(
    params: dict = Depends(_period_params),
    supplier_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_permission("reports.view", "reports.admin")),
):
    _require_admin_report(current_user)
    query = db.query(Booking).filter(Booking.booking_status == "cancelled").options(
        joinedload(Booking.customer), joinedload(Booking.supplier)
    )
    query = _apply_range(query, Booking.cancelled_at, params["start"], params["end"])
    if supplier_id:
        query = query.filter(Booking.supplier_id == supplier_id)
    bookings = query.order_by(Booking.cancelled_at.desc()).limit(ROW_REPORT_LIMIT).all()

    booking_ids = [b.id for b in bookings]
    requests_by_booking = {}
    if booking_ids:
        for req in db.query(CancellationRequest).filter(CancellationRequest.booking_id.in_(booking_ids)).all():
            requests_by_booking[req.booking_id] = req

    canceller_ids = [b.cancelled_by for b in bookings if b.cancelled_by]
    canceller_roles: dict[int, str] = {}
    if canceller_ids:
        for user in db.query(User).options(joinedload(User.role)).filter(User.id.in_(canceller_ids)).all():
            canceller_roles[user.id] = user.role.slug if user.role else "-"

    data = []
    for b in bookings:
        req = requests_by_booking.get(b.id)
        refundable_amount = req.refund_amount if req else None
        cancellation_charge = (float(b.final_amount or 0) - float(refundable_amount)) if refundable_amount is not None else None
        cancelled_by_role = canceller_roles.get(b.cancelled_by, "-")
        data.append({
            "booking_id": b.id,
            "tour": b.tour_name,
            "customer": b.customer.full_name if b.customer else None,
            "supplier": b.supplier.supplier_name if b.supplier else b.supplier_name,
            "cancellation_date": b.cancelled_at,
            "cancelled_by": cancelled_by_role,
            "cancellation_reason": b.cancellation_reason or (req.reason if req else None),
            "booking_amount": _money(b.final_amount),
            "cancellation_charge": _money(cancellation_charge) if cancellation_charge is not None else "-",
            "refundable_amount": _money(refundable_amount) if refundable_amount is not None else "-",
            "refund_status": req.status if req else ("refunded" if b.payment_status in {"refunded", "partially_refunded"} else "-"),
            "refund_date": req.refund_processed_at if req else None,
        })
    return {"status": "success", "data": data}


# ---------------------------------------------------------------------------
# Supplier-facing reports - always scoped to the caller's own supplier
# profile via get_actor_supplier, never platform-wide.
# ---------------------------------------------------------------------------

@router.get("/my-bookings")
def my_bookings_report(
    booking_status: str = Query(default=""),
    payment_status: str = Query(default=""),
    start_date: str = Query(default=""),
    end_date: str = Query(default=""),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_permission("reports.view", "reports.supplier")),
):
    from app.services.supplier_scope import get_actor_supplier
    supplier = get_actor_supplier(db, current_user)
    query = db.query(Booking).filter(Booking.supplier_id == supplier.id).options(joinedload(Booking.customer), joinedload(Booking.agent))
    if booking_status:
        query = query.filter(Booking.booking_status == booking_status.strip().lower())
    if payment_status:
        query = query.filter(Booking.payment_status == payment_status.strip().lower())
    if start_date:
        query = query.filter(Booking.created_at >= _parse_date(start_date))
    if end_date:
        query = query.filter(Booking.created_at <= _parse_date(end_date, end_of_day=True))
    rows = query.order_by(Booking.created_at.desc()).limit(ROW_REPORT_LIMIT).all()

    data = []
    for b in rows:
        adults, children = _adult_child_counts(b)
        data.append({
            "booking_id": b.id,
            "booking_code": b.booking_code,
            "customer_or_agent": (b.agent.agent_name if b.agent else None) or (b.customer.full_name if b.customer else None) or "-",
            "tour_name": b.tour_name,
            "booking_date": b.created_at,
            "travel_date": b.tour_start_date or b.tour_date,
            "adults": adults,
            "children": children,
            "total_amount": _money(b.final_amount),
            "booking_status": b.booking_status,
            "payment_status": b.payment_status,
            "special_requests": b.customer_notes,
        })
    return {"status": "success", "data": data}


@router.get("/my-earnings")
def my_earnings_report(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_permission("reports.view", "reports.supplier")),
):
    from app.services.supplier_scope import get_actor_supplier
    from app.services.supplier_ledger import get_supplier_statement
    supplier = get_actor_supplier(db, current_user)
    statement = get_supplier_statement(db, supplier.id)
    return {
        "status": "success",
        "data": {
            "total_sales": statement["total_gross"],
            "platform_commission": statement["total_commission"],
            # No adjustment/refund-deduction line-item model exists yet (see
            # the equivalent note on /reports/supplier-payout-report) - a
            # refunded pending ledger row is simply excluded from the totals
            # above rather than itemized, so this is honestly 0.
            "refund_deductions": _money(0),
            "adjustments": _money(0),
            "net_earnings": statement["total_net_payable"],
            "paid_earnings": statement["total_paid"],
            "pending_earnings": statement["total_pending"],
        },
    }


@router.get("/my-travellers")
def my_travellers_report(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_permission("reports.view", "reports.supplier")),
):
    from app.models.bookings import BookingTraveller
    from app.services.supplier_scope import get_actor_supplier
    supplier = get_actor_supplier(db, current_user)
    rows = (
        db.query(BookingTraveller, Booking)
        .join(Booking, BookingTraveller.booking_id == Booking.id)
        .filter(Booking.supplier_id == supplier.id)
        .order_by(Booking.created_at.desc())
        .limit(ROW_REPORT_LIMIT)
        .all()
    )
    data = [
        {
            "booking_id": booking.id,
            "traveller_name": traveller.full_name,
            "contact_information": traveller.email or traveller.phone,
            "travel_date": booking.tour_start_date or booking.tour_date,
            "number_of_travellers": booking.total_travellers,
            "pickup_location": traveller.pickup_location,
            "emergency_contact": traveller.emergency_contact,
            "special_requirements": traveller.special_requirements,
            "booking_status": booking.booking_status,
        }
        for traveller, booking in rows
    ]
    return {"status": "success", "data": data}


# export
REPORT_FETCHERS = {
    "summary": lambda db, params, actor: [summary(params, db, actor)["data"]],
    "bookings": lambda db, params, actor: booking_report(params, db, actor)["data"],
    "payments": lambda db, params, actor: payment_report(params, db, actor)["data"],
    "pending-payments": lambda db, params, actor: pending_payments(db, actor)["data"],
    "overdue-payments": lambda db, params, actor: overdue_payments(db, actor)["data"],
    "country-wise": lambda db, params, actor: country_wise(params, db, actor)["data"],
    "cancellations": lambda db, params, actor: cancellations(params, db, actor)["data"],
    "suppliers": lambda db, params, actor: supplier_report(params, db, actor)["data"],
    "agents": lambda db, params, actor: agent_report(params, db, actor)["data"],
    "customers": lambda db, params, actor: customer_report(params, db, actor)["data"],
    "booking-report": lambda db, params, actor: booking_detail_report(params, "", "", None, None, db, actor)["data"],
    "sales-revenue-report": lambda db, params, actor: sales_revenue_report(params, "day", db, actor)["data"]["time_series"],
    "payment-report": lambda db, params, actor: payment_detail_report(params, "", "", db, actor)["data"],
    "supplier-report": lambda db, params, actor: supplier_detail_report(params, db, actor)["data"],
    "supplier-payout-report": lambda db, params, actor: supplier_payout_report("", None, db, actor)["data"],
    "tour-performance-report": lambda db, params, actor: tour_performance_report(None, None, None, db, actor)["data"],
    "cancellation-refund-report": lambda db, params, actor: cancellation_refund_report(params, None, db, actor)["data"],
    "my-bookings": lambda db, params, actor: my_bookings_report("", "", "", "", db, actor)["data"],
    "my-earnings": lambda db, params, actor: [my_earnings_report(db, actor)["data"]],
    "my-travellers": lambda db, params, actor: my_travellers_report(db, actor)["data"],
}

REPORT_LABELS = {
    "summary": "Summary",
    "bookings": "Bookings Summary",
    "payments": "Payments Summary",
    "pending-payments": "Pending Payments",
    "overdue-payments": "Overdue Payments",
    "country-wise": "Country-wise Bookings",
    "cancellations": "Cancellations Summary",
    "suppliers": "Suppliers Summary",
    "agents": "Agent Report",
    "customers": "Customer Report",
    "booking-report": "Booking Report",
    "sales-revenue-report": "Sales and Revenue Report",
    "payment-report": "Payment Report",
    "supplier-report": "Supplier Report",
    "supplier-payout-report": "Supplier Payout Report",
    "tour-performance-report": "Tour Performance Report",
    "cancellation-refund-report": "Cancellation and Refund Report",
    "my-bookings": "My Booking Report",
    "my-earnings": "Earnings Report",
    "my-travellers": "Traveller Report",
}


@router.get("/exports")
def exports(
    report: str = Query(default="summary"),
    format: str = Query(default="csv"),
    period: str = Query(default="all"),
    start_date: str = Query(default=""),
    end_date: str = Query(default=""),
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_permission("reports.export")),
):
    if report not in REPORT_FETCHERS:
        raise HTTPException(status_code=400, detail=f"Unknown report '{report}'. Valid options: {sorted(REPORT_FETCHERS)}")
    if format.lower() not in {"csv"}:
        raise HTTPException(status_code=400, detail="Only CSV export is currently supported")

    params = _period_params(period, start_date, end_date)
    rows = REPORT_FETCHERS[report](db, params, current_user)

    buffer = io.StringIO()
    if rows:
        writer = csv.DictWriter(buffer, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    else:
        buffer.write("No data for the selected period\n")

    label = f"{REPORT_LABELS.get(report, report)} ({period})"
    log_audit(
        db,
        actor=current_user,
        action="export_report",
        entity_type="report",
        entity_id=0,
        new_values={"label": label, "format": "CSV", "report": report, "period": period},
        request=request,
    )
    db.commit()

    buffer.seek(0)
    filename = f"{report}-{period}.csv"
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _serialize_schedule(row: ReportSchedule) -> dict:
    return {
        "id": row.id,
        "report_type": row.report_type,
        "cadence": row.cadence,
        "recipient_emails": row.recipient_emails,
        "is_active": row.is_active,
        "created_by": row.created_by,
        "created_at": row.created_at,
        "last_run_at": row.last_run_at,
    }


class ReportScheduleCreate(BaseModel):
    report_type: str
    cadence: str = "weekly"
    recipient_emails: str


@router.get("/schedule")
def list_report_schedules(db: Session = Depends(get_db), _=Depends(require_any_permission("reports.view"))):
    rows = db.query(ReportSchedule).order_by(ReportSchedule.id.desc()).all()
    return {"status": "success", "data": [_serialize_schedule(row) for row in rows]}


@router.post("/schedule")
def create_report_schedule(data: ReportScheduleCreate, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("reports.export", "reports.view"))):
    if data.report_type not in REPORT_FETCHERS:
        raise HTTPException(status_code=400, detail=f"Unknown report '{data.report_type}'. Valid options: {sorted(REPORT_FETCHERS)}")
    row = ReportSchedule(
        report_type=data.report_type,
        cadence=data.cadence,
        recipient_emails=data.recipient_emails,
        created_by=current_user.id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {
        "status": "success",
        "message": f"Schedule saved. The report will be emailed to the listed recipients {data.cadence}.",
        "data": _serialize_schedule(row),
    }


@router.delete("/schedule/{schedule_id}")
def delete_report_schedule(schedule_id: int, db: Session = Depends(get_db), _=Depends(require_any_permission("reports.export", "reports.view"))):
    row = db.query(ReportSchedule).filter(ReportSchedule.id == schedule_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Schedule not found")
    db.delete(row)
    db.commit()
    return {"status": "success", "message": "Schedule deleted"}


@router.get("/snapshot")
def snapshot(db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("reports.view"))):
    _require_admin_report(current_user)
    now = utcnow()
    curr_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if now.month == 1:
        last_start = curr_start.replace(year=now.year - 1, month=12)
    else:
        last_start = curr_start.replace(month=now.month - 1)

    # Booking Performance
    total_bookings = db.query(func.count(Booking.id)).scalar() or 0
    curr_bookings = db.query(func.count(Booking.id)).filter(Booking.created_at >= curr_start).scalar() or 0
    last_bookings = db.query(func.count(Booking.id)).filter(Booking.created_at >= last_start, Booking.created_at < curr_start).scalar() or 0
    booking_change = round(((curr_bookings - last_bookings) / last_bookings * 100) if last_bookings > 0 else 0, 1)

    # Revenue Summary - net of refunds. captured_amount is left unchanged by
    # a refund (only refunded_amount and payment_status change, see
    # services/payments.py process_refund), so it must be subtracted here or
    # a refunded booking's original charge keeps counting as revenue.
    def _net_revenue(*extra_filters) -> float:
        captured = db.query(func.coalesce(func.sum(Payment.captured_amount), 0)).filter(Payment.payment_status.notin_(["voided", "failed"]), *extra_filters).scalar() or 0
        refunded = db.query(func.coalesce(func.sum(Payment.refunded_amount), 0)).filter(Payment.payment_status.notin_(["voided", "failed"]), *extra_filters).scalar() or 0
        return max(0.0, float(captured) - float(refunded))

    total_revenue = _net_revenue()
    curr_revenue = _net_revenue(Payment.created_at >= curr_start)
    last_revenue = _net_revenue(Payment.created_at >= last_start, Payment.created_at < curr_start)
    revenue_change = round(((curr_revenue - last_revenue) / last_revenue * 100) if last_revenue > 0 else 0, 1)

    # Supplier Approval
    total_suppliers = db.query(func.count(Supplier.id)).scalar() or 0
    pending_suppliers = db.query(func.count(Supplier.id)).filter(Supplier.approval_status == "pending").scalar() or 0

    # Agent Sales
    agent_total = db.query(func.count(Booking.id)).filter(Booking.agent_id.isnot(None)).scalar() or 0
    agent_curr = db.query(func.count(Booking.id)).filter(Booking.agent_id.isnot(None), Booking.created_at >= curr_start).scalar() or 0
    agent_last = db.query(func.count(Booking.id)).filter(Booking.agent_id.isnot(None), Booking.created_at >= last_start, Booking.created_at < curr_start).scalar() or 0
    agent_change = round(((agent_curr - agent_last) / agent_last * 100) if agent_last > 0 else 0, 1)

    # Payment Collection
    total_final = float(db.query(func.coalesce(func.sum(Booking.final_amount), 0)).scalar() or 0)
    total_paid = float(db.query(func.coalesce(func.sum(Booking.amount_paid), 0)).scalar() or 0)
    total_pending_amt = float(db.query(func.coalesce(func.sum(Booking.amount_pending), 0)).scalar() or 0)
    collected_pct = round((total_paid / total_final * 100) if total_final > 0 else 0, 1)
    pending_pct = round(100 - collected_pct, 1)

    # Country-wise
    country_count = db.query(func.count(func.distinct(Booking.country_id))).filter(Booking.country_id.isnot(None)).scalar() or 0

    # Recent exports from audit log
    export_logs = (
        db.query(AuditLog)
        .filter(AuditLog.entity_type == "report", AuditLog.action == "export_report")
        .order_by(AuditLog.id.desc())
        .limit(5)
        .all()
    )
    recent_exports = [
        {
            "id": log.id,
            "label": (log.new_values or {}).get("label", "Report Export"),
            "format": (log.new_values or {}).get("format", "CSV").upper(),
            "exported_at": log.created_at,
        }
        for log in export_logs
    ]

    return {
        "status": "success",
        "data": {
            "booking_performance": {
                "total": total_bookings,
                "current_month": curr_bookings,
                "change_pct": booking_change,
            },
            "revenue_summary": {
                "total": _money(total_revenue),
                "total_raw": float(total_revenue),
                "current_month": _money(curr_revenue),
                "change_pct": revenue_change,
            },
            "supplier_approval": {
                "total": total_suppliers,
                "pending": pending_suppliers,
            },
            "agent_sales": {
                "total": agent_total,
                "current_month": agent_curr,
                "change_pct": agent_change,
            },
            "payment_collection": {
                "collected_pct": collected_pct,
                "pending_pct": pending_pct,
                "total_amount": _money(total_final),
                "collected_amount": _money(total_paid),
                "pending_amount": _money(total_pending_amt),
            },
            "country_wise": {
                "country_count": country_count,
            },
            "meta": {
                "report_types": len(REPORT_FETCHERS),
                "scheduled": _scheduled_report_count(db),
                "total_exports": db.query(func.count(AuditLog.id)).filter(AuditLog.entity_type == "report", AuditLog.action == "export_report").scalar() or 0,
            },
            "recent_exports": recent_exports,
        },
    }
