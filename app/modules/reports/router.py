from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.modules.agents.models import Agent
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
