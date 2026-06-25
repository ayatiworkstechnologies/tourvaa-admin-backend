from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.modules.agents.models import Agent
from app.modules.audit.models import AuditLog
from app.modules.bookings.models import Booking
from app.modules.cms.models import Country
from app.modules.common.auth import require_any_permission
from app.modules.common.money import money_str, utcnow
from app.modules.customers.models import Customer
from app.modules.invoices.models import Invoice
from app.modules.payments.models import Payment
from app.modules.suppliers.models import Supplier

router = APIRouter(prefix="/reports", tags=["Reports"])


def _money(value):
    return money_str(value or 0)


@router.get("/summary")
def summary(db: Session = Depends(get_db), _=Depends(require_any_permission("reports.view"))):
    total_bookings = db.query(func.count(Booking.id)).scalar() or 0
    confirmed = db.query(func.count(Booking.id)).filter(Booking.booking_status == "confirmed").scalar() or 0
    cancelled = db.query(func.count(Booking.id)).filter(Booking.booking_status == "cancelled").scalar() or 0
    revenue = db.query(func.coalesce(func.sum(Payment.captured_amount), 0)).filter(Payment.payment_status.notin_(["voided", "failed"])).scalar() or 0
    pending = db.query(func.coalesce(func.sum(Booking.amount_pending), 0)).scalar() or 0
    invoice_total = db.query(func.coalesce(func.sum(Invoice.total_amount), 0)).scalar() or 0
    return {"status": "success", "data": {"total_bookings": total_bookings, "confirmed_bookings": confirmed, "cancelled_bookings": cancelled, "captured_revenue": _money(revenue), "pending_payments": _money(pending), "invoice_total": _money(invoice_total)}}


@router.get("/bookings")
def booking_report(db: Session = Depends(get_db), _=Depends(require_any_permission("reports.view", "reports.admin"))):
    rows = db.query(Booking.booking_status, func.count(Booking.id), func.coalesce(func.sum(Booking.final_amount), 0)).group_by(Booking.booking_status).all()
    return {"status": "success", "data": [{"status": status, "count": count, "amount": _money(amount)} for status, count, amount in rows]}


@router.get("/payments")
def payment_report(db: Session = Depends(get_db), _=Depends(require_any_permission("reports.view", "reports.admin"))):
    rows = db.query(Payment.payment_status, func.count(Payment.id), func.coalesce(func.sum(Payment.captured_amount), 0), func.coalesce(func.sum(Payment.refunded_amount), 0)).group_by(Payment.payment_status).all()
    return {"status": "success", "data": [{"status": status, "count": count, "captured": _money(captured), "refunded": _money(refunded)} for status, count, captured, refunded in rows]}


@router.get("/pending-payments")
def pending_payments(db: Session = Depends(get_db), _=Depends(require_any_permission("reports.view", "reports.admin"))):
    rows = db.query(Booking).filter(Booking.amount_pending > 0).order_by(Booking.amount_pending.desc()).limit(200).all()
    return {"status": "success", "data": [{"booking_id": b.id, "booking_code": b.booking_code, "customer_id": b.customer_id, "amount_pending": _money(b.amount_pending), "payment_status": b.payment_status} for b in rows]}


@router.get("/overdue-payments")
def overdue_payments(db: Session = Depends(get_db), _=Depends(require_any_permission("reports.view", "reports.admin"))):
    today = utcnow().date()
    rows = db.query(Booking).filter(Booking.amount_pending > 0, Booking.tour_start_date != None, func.date(Booking.tour_start_date) <= today).order_by(Booking.tour_start_date.asc()).limit(200).all()
    return {"status": "success", "data": [{"booking_id": b.id, "booking_code": b.booking_code, "tour_start_date": b.tour_start_date, "amount_pending": _money(b.amount_pending)} for b in rows]}


@router.get("/country-wise")
def country_wise(db: Session = Depends(get_db), _=Depends(require_any_permission("reports.view", "reports.admin"))):
    rows = db.query(Country.country_name, func.count(Booking.id), func.coalesce(func.sum(Booking.final_amount), 0)).join(Booking, Booking.country_id == Country.id, isouter=True).group_by(Country.country_name).all()
    return {"status": "success", "data": [{"country": country, "bookings": count, "amount": _money(amount)} for country, count, amount in rows]}


@router.get("/cancellations")
def cancellations(db: Session = Depends(get_db), _=Depends(require_any_permission("reports.view", "reports.admin"))):
    rows = db.query(Booking).filter(Booking.booking_status == "cancelled").order_by(Booking.cancelled_at.desc()).limit(200).all()
    return {"status": "success", "data": [{"booking_id": b.id, "booking_code": b.booking_code, "reason": b.cancellation_reason, "cancelled_at": b.cancelled_at, "amount": _money(b.final_amount)} for b in rows]}


@router.get("/suppliers")
def supplier_report(db: Session = Depends(get_db), _=Depends(require_any_permission("reports.view", "reports.supplier", "reports.admin"))):
    rows = db.query(Supplier.id, Supplier.supplier_name, func.count(Booking.id), func.coalesce(func.sum(Booking.final_amount), 0)).join(Booking, Booking.supplier_id == Supplier.id, isouter=True).group_by(Supplier.id, Supplier.supplier_name).all()
    return {"status": "success", "data": [{"supplier_id": sid, "supplier_name": name, "bookings": count, "amount": _money(amount)} for sid, name, count, amount in rows]}


@router.get("/agents")
def agent_report(db: Session = Depends(get_db), _=Depends(require_any_permission("reports.view", "reports.agent", "reports.admin"))):
    rows = db.query(Agent.id, Agent.agent_name, func.count(Booking.id), func.coalesce(func.sum(Booking.final_amount), 0)).join(Booking, Booking.agent_id == Agent.id, isouter=True).group_by(Agent.id, Agent.agent_name).all()
    return {"status": "success", "data": [{"agent_id": aid, "agent_name": name, "bookings": count, "amount": _money(amount)} for aid, name, count, amount in rows]}


@router.get("/customers")
def customer_report(db: Session = Depends(get_db), _=Depends(require_any_permission("reports.view", "reports.admin"))):
    rows = db.query(Customer.id, Customer.full_name, func.count(Booking.id), func.coalesce(func.sum(Booking.final_amount), 0), func.coalesce(func.sum(Booking.amount_pending), 0)).join(Booking, Booking.customer_id == Customer.id, isouter=True).group_by(Customer.id, Customer.full_name).all()
    return {"status": "success", "data": [{"customer_id": cid, "customer_name": name, "bookings": count, "amount": _money(amount), "pending": _money(pending)} for cid, name, count, amount, pending in rows]}


@router.get("/exports")
def exports(format: str = Query(default="json"), db: Session = Depends(get_db), _=Depends(require_any_permission("reports.export"))):
    return summary(db)


@router.get("/snapshot")
def snapshot(db: Session = Depends(get_db), _=Depends(require_any_permission("reports.view"))):
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
                "report_types": 6,
                "scheduled": 0,
                "total_exports": db.query(func.count(AuditLog.id)).filter(AuditLog.entity_type == "report", AuditLog.action == "export_report").scalar() or 0,
            },
            "recent_exports": recent_exports,
        },
    }
