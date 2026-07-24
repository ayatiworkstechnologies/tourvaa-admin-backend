from decimal import Decimal
from math import ceil
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session, joinedload

from app.services.audit import log_audit
from app.models.bookings import Booking
from app.utils.money import money, utcnow
from app.services.notifications import enqueue_notification
from app.models.supplier_ledger import SupplierLedger, SupplierPayout, SupplierPayoutItem
from app.schemas.supplier_ledger import SupplierPayoutCreate, SupplierPayoutMarkPaid
from app.models.suppliers import Supplier
from app.models.users import User


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
        "paid_by": row.paid_by,
        "payer_name": row.payer.name if row.payer else None,
        "paid_at": row.paid_at,
        "items": [{"ledger_id": i.ledger_id, "amount": str(i.amount)} for i in row.items],
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


# -- ledger --


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
    q = db.query(SupplierLedger).options(joinedload(SupplierLedger.supplier), joinedload(SupplierLedger.booking)).filter(SupplierLedger.supplier_id == supplier_id)
    if status:
        q = q.filter(SupplierLedger.status == status)
    q = q.order_by(SupplierLedger.id.desc())
    total = q.count()
    items = [_serialize_ledger(r) for r in q.offset((page - 1) * limit).limit(limit).all()]
    return {"items": items, "data": items, "total": total, "page": page, "limit": limit, "total_pages": max(1, ceil(total / limit))}


def list_all_ledgers(db: Session, page: int = 1, limit: int = 20, supplier_id: Optional[int] = None, status: str = "") -> dict:
    q = db.query(SupplierLedger).options(joinedload(SupplierLedger.supplier), joinedload(SupplierLedger.booking))
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
    rows = db.query(SupplierLedger).options(joinedload(SupplierLedger.supplier), joinedload(SupplierLedger.booking)).filter(SupplierLedger.supplier_id == supplier_id).all()
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


# -- payouts --


def list_payouts(db: Session, page: int = 1, limit: int = 20, supplier_id: Optional[int] = None, status: str = "") -> dict:
    q = db.query(SupplierPayout).options(
        joinedload(SupplierPayout.supplier),
        joinedload(SupplierPayout.initiator),
        joinedload(SupplierPayout.approver),
        joinedload(SupplierPayout.payer),
        joinedload(SupplierPayout.items),
    )
    if supplier_id:
        q = q.filter(SupplierPayout.supplier_id == supplier_id)
    if status:
        q = q.filter(SupplierPayout.status == status)
    q = q.order_by(SupplierPayout.id.desc())
    total = q.count()
    items = [_serialize_payout(r) for r in q.offset((page - 1) * limit).limit(limit).all()]
    return {"items": items, "data": items, "total": total, "page": page, "limit": limit, "total_pages": max(1, ceil(total / limit))}


def _actor_supplier_id(db: Session, actor: User) -> int | None:
    supplier = db.query(Supplier).filter(Supplier.user_id == actor.id).first() if actor else None
    return supplier.id if supplier else None


def _is_supplier_actor(actor: User) -> bool:
    if not actor:
        return False
    role_slugs = set()
    if actor.role and actor.role.slug:
        role_slugs.add(actor.role.slug)
    for user_role in actor.user_roles or []:
        if user_role.role and user_role.role.slug:
            role_slugs.add(user_role.role.slug)
    return "supplier" in role_slugs and not ({"admin", "super-admin"} & role_slugs)


def _resolve_payout_supplier_id(db: Session, data: SupplierPayoutCreate, actor: User) -> int:
    actor_supplier_id = _actor_supplier_id(db, actor)
    if data.supplier_id:
        if _is_supplier_actor(actor):
            # A supplier-role actor with no linked Supplier row must not fall
            # through this guard silently -- that would let an
            # attacker-controlled supplier_id through unchecked.
            if not actor_supplier_id:
                raise HTTPException(status_code=403, detail="No supplier profile is linked to this account")
            if data.supplier_id != actor_supplier_id:
                raise HTTPException(status_code=403, detail="You can only request payouts for your own supplier account")
        return data.supplier_id
    if _is_supplier_actor(actor) and actor_supplier_id:
        return actor_supplier_id
    raise HTTPException(status_code=422, detail="supplier_id is required")


def _select_payout_ledgers(db: Session, supplier_id: int, data: SupplierPayoutCreate) -> list[SupplierLedger]:
    query = db.query(SupplierLedger).filter(SupplierLedger.supplier_id == supplier_id)
    if data.ledger_ids:
        ledger_rows = query.filter(SupplierLedger.id.in_(data.ledger_ids)).with_for_update().all()
    else:
        ledger_rows = query.filter(
            SupplierLedger.status.in_(("pending", "partial")),
            SupplierLedger.amount_pending > 0,
        ).order_by(SupplierLedger.id.asc()).with_for_update().all()
        if data.amount is not None:
            requested = money(data.amount)
            selected: list[SupplierLedger] = []
            running = Decimal("0")
            for row in ledger_rows:
                selected.append(row)
                running = money(running + money(row.amount_pending))
                if running >= requested:
                    break
            ledger_rows = selected
    if not ledger_rows:
        raise HTTPException(status_code=404, detail="No payable ledger entries found for this supplier")
    return ledger_rows


def create_payout(db: Session, data: SupplierPayoutCreate, actor: User, request=None) -> dict:
    supplier_id = _resolve_payout_supplier_id(db, data, actor)
    # Lock the ledger rows for the duration of this transaction so a concurrent
    # create_payout call can't select the same rows before either commits (double-payout).
    ledger_rows = _select_payout_ledgers(db, supplier_id, data)

    for row in ledger_rows:
        if row.status == "paid":
            raise HTTPException(status_code=400, detail=f"Ledger entry {row.id} is already fully paid")
        if row.status == "reserved":
            raise HTTPException(status_code=400, detail=f"Ledger entry {row.id} is already included in another pending payout")

    available_total = money(sum(r.amount_pending for r in ledger_rows))
    if data.amount is not None and available_total < money(data.amount):
        raise HTTPException(status_code=400, detail="Requested payout amount exceeds available payable balance")

    remaining = money(data.amount) if data.amount is not None else None
    payout_amounts: dict[int, Decimal] = {}
    for row in ledger_rows:
        row_pending = money(row.amount_pending)
        if remaining is None:
            payout_amount = row_pending
        else:
            payout_amount = money(min(row_pending, remaining))
            remaining = money(remaining - payout_amount)
        if payout_amount > 0:
            payout_amounts[row.id] = payout_amount

    total = money(sum(payout_amounts.values()))

    payout = SupplierPayout(
        supplier_id=supplier_id,
        total_amount=total,
        currency=data.currency or ledger_rows[0].currency,
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
        db.add(SupplierPayoutItem(payout_id=payout.id, ledger_id=row.id, amount=payout_amounts[row.id]))
        row.status = "reserved"

    db.commit()
    db.refresh(payout)
    log_audit(db, actor=actor, action="create_supplier_payout", entity_type="supplier_payout", entity_id=payout.id, old_values={}, new_values={"supplier_id": supplier_id, "amount": str(total)}, request=request)
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
    payout.paid_by = actor.id
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




