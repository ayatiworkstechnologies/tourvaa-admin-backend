from decimal import Decimal
from math import ceil
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.modules.audit.service import log_audit
from app.modules.bookings.models import Booking
from app.modules.common.money import money, utcnow
from app.modules.notifications.service import enqueue_notification
from app.modules.supplier_ledger.models import SupplierLedger, SupplierPayout, SupplierPayoutItem
from app.modules.supplier_ledger.schemas import SupplierPayoutCreate, SupplierPayoutMarkPaid
from app.modules.suppliers.models import Supplier
from app.modules.users.models import User


def _payout_code(payout_id: int) -> str:
    return f"SPO-{payout_id:06d}"


def _serialize_ledger(row: SupplierLedger) -> dict:
    return {
        "id": row.id,
        "supplier_id": row.supplier_id,
        "supplier_name": row.supplier.supplier_name if row.supplier else None,
        "booking_id": row.booking_id,
        "booking_code": row.booking.booking_code if row.booking else None,
        "gross_amount": str(row.gross_amount),
        "commission_amount": str(row.commission_amount),
        "commission_percentage": str(row.commission_percentage),
        "net_payable": str(row.net_payable),
        "amount_paid": str(row.amount_paid),
        "amount_pending": str(row.amount_pending),
        "currency": row.currency,
        "status": row.status,
        "notes": row.notes,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _serialize_payout(row: SupplierPayout) -> dict:
    return {
        "id": row.id,
        "payout_code": row.payout_code,
        "supplier_id": row.supplier_id,
        "supplier_name": row.supplier.supplier_name if row.supplier else None,
        "total_amount": str(row.total_amount),
        "currency": row.currency,
        "payment_method": row.payment_method,
        "reference_number": row.reference_number,
        "status": row.status,
        "notes": row.notes,
        "initiated_by": row.initiated_by,
        "initiator_name": row.initiator.name if row.initiator else None,
        "approved_by": row.approved_by,
        "approver_name": row.approver.name if row.approver else None,
        "paid_at": row.paid_at,
        "items": [{"ledger_id": i.ledger_id, "amount": str(i.amount)} for i in row.items],
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


# ---------------------------------------------------------------------------
# Ledger
# ---------------------------------------------------------------------------


def create_ledger_entry(db: Session, *, booking: Booking, supplier_id: int, gross_amount: Decimal, commission_percentage: Decimal) -> SupplierLedger:
    """Called from booking service when a booking is confirmed and assigned to a supplier."""
    commission_amount = money((gross_amount * commission_percentage) / 100)
    net_payable = money(gross_amount - commission_amount)
    entry = SupplierLedger(
        supplier_id=supplier_id,
        booking_id=booking.id,
        gross_amount=money(gross_amount),
        commission_amount=commission_amount,
        commission_percentage=commission_percentage,
        net_payable=net_payable,
        amount_paid=Decimal("0"),
        amount_pending=net_payable,
        currency=booking.currency or "USD",
        status="pending",
    )
    db.add(entry)
    return entry


def get_supplier_ledger(db: Session, supplier_id: int, page: int = 1, limit: int = 20, status: str = "") -> dict:
    q = db.query(SupplierLedger).filter(SupplierLedger.supplier_id == supplier_id)
    if status:
        q = q.filter(SupplierLedger.status == status)
    q = q.order_by(SupplierLedger.id.desc())
    total = q.count()
    items = [_serialize_ledger(r) for r in q.offset((page - 1) * limit).limit(limit).all()]
    return {"items": items, "data": items, "total": total, "page": page, "limit": limit, "total_pages": max(1, ceil(total / limit))}


def list_all_ledgers(db: Session, page: int = 1, limit: int = 20, supplier_id: Optional[int] = None, status: str = "") -> dict:
    q = db.query(SupplierLedger)
    if supplier_id:
        q = q.filter(SupplierLedger.supplier_id == supplier_id)
    if status:
        q = q.filter(SupplierLedger.status == status)
    q = q.order_by(SupplierLedger.id.desc())
    total = q.count()
    items = [_serialize_ledger(r) for r in q.offset((page - 1) * limit).limit(limit).all()]
    return {"items": items, "data": items, "total": total, "page": page, "limit": limit, "total_pages": max(1, ceil(total / limit))}


def get_supplier_statement(db: Session, supplier_id: int) -> dict:
    supplier = db.query(Supplier).filter(Supplier.id == supplier_id).first()
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")
    rows = db.query(SupplierLedger).filter(SupplierLedger.supplier_id == supplier_id).all()
    total_gross = sum(money(r.gross_amount) for r in rows)
    total_commission = sum(money(r.commission_amount) for r in rows)
    total_net = sum(money(r.net_payable) for r in rows)
    total_paid = sum(money(r.amount_paid) for r in rows)
    total_pending = sum(money(r.amount_pending) for r in rows)
    return {
        "supplier_id": supplier_id,
        "supplier_name": supplier.supplier_name,
        "total_gross": str(total_gross),
        "total_commission": str(total_commission),
        "total_net_payable": str(total_net),
        "total_paid": str(total_paid),
        "total_pending": str(total_pending),
        "entries": [_serialize_ledger(r) for r in rows],
    }


# ---------------------------------------------------------------------------
# Payouts
# ---------------------------------------------------------------------------


def list_payouts(db: Session, page: int = 1, limit: int = 20, supplier_id: Optional[int] = None, status: str = "") -> dict:
    q = db.query(SupplierPayout)
    if supplier_id:
        q = q.filter(SupplierPayout.supplier_id == supplier_id)
    if status:
        q = q.filter(SupplierPayout.status == status)
    q = q.order_by(SupplierPayout.id.desc())
    total = q.count()
    items = [_serialize_payout(r) for r in q.offset((page - 1) * limit).limit(limit).all()]
    return {"items": items, "data": items, "total": total, "page": page, "limit": limit, "total_pages": max(1, ceil(total / limit))}


def create_payout(db: Session, data: SupplierPayoutCreate, actor: User, request=None) -> dict:
    # Lock the ledger rows for the duration of this transaction so a concurrent
    # create_payout call can't select the same rows before either commits (double-payout).
    ledger_rows = db.query(SupplierLedger).filter(
        SupplierLedger.id.in_(data.ledger_ids),
        SupplierLedger.supplier_id == data.supplier_id,
    ).with_for_update().all()
    if not ledger_rows:
        raise HTTPException(status_code=404, detail="No matching ledger entries found for this supplier")

    for row in ledger_rows:
        if row.status == "paid":
            raise HTTPException(status_code=400, detail=f"Ledger entry {row.id} is already fully paid")
        if row.status == "reserved":
            raise HTTPException(status_code=400, detail=f"Ledger entry {row.id} is already included in another pending payout")

    total = money(sum(r.amount_pending for r in ledger_rows))

    payout = SupplierPayout(
        supplier_id=data.supplier_id,
        total_amount=total,
        currency=ledger_rows[0].currency,
        payment_method=data.payment_method,
        reference_number=data.reference_number,
        status="pending",
        notes=data.notes,
        initiated_by=actor.id,
    )
    db.add(payout)
    db.flush()
    payout.payout_code = _payout_code(payout.id)

    for row in ledger_rows:
        db.add(SupplierPayoutItem(payout_id=payout.id, ledger_id=row.id, amount=row.amount_pending))
        row.status = "reserved"

    db.commit()
    db.refresh(payout)
    log_audit(db, actor=actor, action="create_supplier_payout", entity_type="supplier_payout", entity_id=payout.id, old_values={}, new_values={"supplier_id": data.supplier_id, "amount": str(total)}, request=request)
    return _serialize_payout(payout)


def approve_payout(db: Session, payout_id: int, actor: User, request=None) -> dict:
    payout = db.query(SupplierPayout).filter(SupplierPayout.id == payout_id).first()
    if not payout:
        raise HTTPException(status_code=404, detail="Payout not found")
    if payout.status != "pending":
        raise HTTPException(status_code=400, detail=f"Payout cannot be approved from status '{payout.status}'")

    payout.status = "approved"
    payout.approved_by = actor.id
    db.commit()
    db.refresh(payout)
    log_audit(db, actor=actor, action="approve_supplier_payout", entity_type="supplier_payout", entity_id=payout_id, old_values={"status": "pending"}, new_values={"status": "approved"}, request=request)
    return _serialize_payout(payout)


def mark_payout_paid(db: Session, payout_id: int, data: SupplierPayoutMarkPaid, actor: User, request=None) -> dict:
    payout = db.query(SupplierPayout).filter(SupplierPayout.id == payout_id).with_for_update().first()
    if not payout:
        raise HTTPException(status_code=404, detail="Payout not found")
    if payout.status == "paid":
        raise HTTPException(status_code=400, detail="Payout is already marked as paid")
    if payout.status != "approved":
        raise HTTPException(status_code=400, detail=f"Payout must be approved before marking as paid (current status: '{payout.status}')")

    payout.status = "paid"
    payout.approved_by = actor.id
    payout.paid_at = utcnow()
    if data.reference_number:
        payout.reference_number = data.reference_number
    if data.notes:
        payout.notes = data.notes

    # Lock and update ledger entries
    ledger_ids = [item.ledger_id for item in payout.items]
    locked_ledgers = {
        row.id: row
        for row in db.query(SupplierLedger).filter(SupplierLedger.id.in_(ledger_ids)).with_for_update().all()
    } if ledger_ids else {}
    for item in payout.items:
        ledger = locked_ledgers.get(item.ledger_id)
        if not ledger:
            continue
        ledger.amount_paid = money(money(ledger.amount_paid) + money(item.amount))
        ledger.amount_pending = money(max(Decimal("0"), money(ledger.net_payable) - money(ledger.amount_paid)))
        ledger.status = "paid" if ledger.amount_pending == 0 else "partial"

    db.commit()
    db.refresh(payout)

    # Notify supplier
    if payout.supplier and payout.supplier.user_id:
        enqueue_notification(db, user_id=payout.supplier.user_id, notification_type="payout_completed", title="Payout Processed", message=f"Your payout of {payout.total_amount} {payout.currency} has been processed. Ref: {payout.reference_number or 'N/A'}", entity_type="supplier_payout", entity_id=payout.id)
        db.commit()

    log_audit(db, actor=actor, action="mark_payout_paid", entity_type="supplier_payout", entity_id=payout_id, old_values={"status": "pending"}, new_values={"status": "paid"}, request=request)
    return _serialize_payout(payout)
