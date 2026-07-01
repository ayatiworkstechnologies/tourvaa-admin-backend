import csv
import io
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.modules.agents.models import Agent
from app.modules.audit.models import AuditLog
from app.modules.audit.service import log_audit
from app.modules.bookings.models import Booking
from app.modules.cms.models import Country
from app.modules.common.auth import require_any_permission
from app.modules.common.money import money_str, utcnow
from app.modules.customers.models import Customer
from app.modules.invoices.models import Invoice
from app.modules.payments.models import Payment
from app.modules.suppliers.models import Supplier
from app.modules.users.models import User

router = APIRouter(prefix="/reports", tags=["Reports"])

PERIODS = {"day", "week", "month", "quarter", "half_year", "year", "custom", "all"}


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
    revenue = payments_q.with_entities(func.coalesce(func.sum(Payment.captured_amount), 0)).scalar() or 0
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
def supplier_report(params: dict = Depends(_period_params), db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("reports.view", "reports.supplier", "reports.admin"))):
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


# ── Export ──────────────────────────────────────────────────────────────────

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
}

REPORT_LABELS = {
    "summary": "Summary",
    "bookings": "Booking Report",
    "payments": "Payment Report",
    "pending-payments": "Pending Payments",
    "overdue-payments": "Overdue Payments",
    "country-wise": "Country-wise Bookings",
    "cancellations": "Cancellations",
    "suppliers": "Supplier Report",
    "agents": "Agent Report",
    "customers": "Customer Report",
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

    # Revenue Summary
    total_revenue = db.query(func.coalesce(func.sum(Payment.captured_amount), 0)).filter(Payment.payment_status.notin_(["voided", "failed"])).scalar() or 0
    curr_revenue = db.query(func.coalesce(func.sum(Payment.captured_amount), 0)).filter(Payment.payment_status.notin_(["voided", "failed"]), Payment.created_at >= curr_start).scalar() or 0
    last_revenue = db.query(func.coalesce(func.sum(Payment.captured_amount), 0)).filter(Payment.payment_status.notin_(["voided", "failed"]), Payment.created_at >= last_start, Payment.created_at < curr_start).scalar() or 0
    revenue_change = round(((float(curr_revenue) - float(last_revenue)) / float(last_revenue) * 100) if float(last_revenue) > 0 else 0, 1)

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
                "scheduled": 0,
                "total_exports": db.query(func.count(AuditLog.id)).filter(AuditLog.entity_type == "report", AuditLog.action == "export_report").scalar() or 0,
            },
            "recent_exports": recent_exports,
        },
    }
