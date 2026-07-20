from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.cms import Tour
from app.models.suppliers import Supplier
from app.models.users import User


def is_supplier_user(user: User | None) -> bool:
    if not user:
        return False
    role_slugs = set()
    if getattr(user, "role", None) and user.role.slug:
        role_slugs.add(user.role.slug)
    for user_role in getattr(user, "user_roles", None) or []:
        if user_role.role and user_role.role.slug:
            role_slugs.add(user_role.role.slug)
    return "supplier" in role_slugs and not ({"admin", "super-admin"} & role_slugs)


def get_actor_supplier(db: Session, user: User) -> Supplier:
    supplier = db.query(Supplier).filter(Supplier.user_id == user.id).first()
    if not supplier:
        raise HTTPException(status_code=403, detail="Supplier profile not found")
    return supplier


def ensure_supplier_account_access(db: Session, supplier_id: int, user: User | None) -> None:
    if not is_supplier_user(user):
        return
    if get_actor_supplier(db, user).id != supplier_id:
        raise HTTPException(status_code=403, detail="You can only access your own supplier account")


def ensure_supplier_tour_access(db: Session, tour_id: int, user: User | None) -> Tour:
    tour = db.query(Tour).filter(Tour.id == tour_id).first()
    if not tour:
        raise HTTPException(status_code=404, detail="Tour not found")
    if is_supplier_user(user) and tour.supplier_id != get_actor_supplier(db, user).id:
        raise HTTPException(status_code=403, detail="Access denied: this tour belongs to another supplier")
    return tour


def reject_supplier_review_action(user: User | None) -> None:
    if is_supplier_user(user):
        raise HTTPException(status_code=403, detail="Tour approval decisions are restricted to administrators")
