"""Admin CRUD for affiliate_commission_rules. Resolution logic itself lives
in app/services/affiliate_commission.py - this module is just management."""
from math import ceil
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.affiliate_tracking import AffiliateCommissionRule, AffiliateConversion
from app.models.users import User
from app.schemas.affiliate_tracking import AffiliateCommissionRuleCreate, AffiliateCommissionRuleUpdate
from app.services.audit import log_audit


def _s_rule(r: AffiliateCommissionRule) -> dict:
    return {
        "id": r.id, "name": r.name, "affiliate_id": r.affiliate_id, "tour_id": r.tour_id,
        "category_id": r.category_id, "affiliate_link_id": r.affiliate_link_id,
        "commission_type": r.commission_type, "percentage": str(r.percentage), "fixed_amount": str(r.fixed_amount),
        "currency": r.currency, "valid_from": r.valid_from, "valid_until": r.valid_until,
        "priority": r.priority, "is_active": r.is_active,
        "created_at": r.created_at, "updated_at": r.updated_at,
    }


def create_rule(db: Session, data: AffiliateCommissionRuleCreate, actor: User) -> dict:
    rule = AffiliateCommissionRule(**data.model_dump(), created_by=getattr(actor, "id", None))
    db.add(rule)
    db.commit()
    db.refresh(rule)
    log_audit(db, actor=actor, action="create_affiliate_commission_rule", entity_type="affiliate_commission_rule", entity_id=rule.id, new_values=_s_rule(rule))
    db.commit()
    return _s_rule(rule)


def get_rule(db: Session, rule_id: int) -> AffiliateCommissionRule:
    rule = db.query(AffiliateCommissionRule).filter(AffiliateCommissionRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Commission rule not found")
    return rule


def list_rules(db: Session, *, affiliate_id: Optional[int] = None, tour_id: Optional[int] = None, is_active: Optional[bool] = None, page: int = 1, limit: int = 20) -> dict:
    q = db.query(AffiliateCommissionRule)
    if affiliate_id:
        q = q.filter(AffiliateCommissionRule.affiliate_id == affiliate_id)
    if tour_id:
        q = q.filter(AffiliateCommissionRule.tour_id == tour_id)
    if is_active is not None:
        q = q.filter(AffiliateCommissionRule.is_active == is_active)
    q = q.order_by(AffiliateCommissionRule.priority.desc(), AffiliateCommissionRule.id.desc())
    total = q.count()
    items = [_s_rule(r) for r in q.offset((page - 1) * limit).limit(limit).all()]
    return {"items": items, "total": total, "page": page, "limit": limit, "total_pages": max(1, ceil(total / limit))}


def update_rule(db: Session, rule_id: int, data: AffiliateCommissionRuleUpdate, actor: User) -> dict:
    rule = get_rule(db, rule_id)
    old = _s_rule(rule)
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(rule, key, value)
    rule.updated_by = getattr(actor, "id", None)
    db.commit()
    db.refresh(rule)
    log_audit(db, actor=actor, action="update_affiliate_commission_rule", entity_type="affiliate_commission_rule", entity_id=rule.id, old_values=old, new_values=_s_rule(rule))
    db.commit()
    return _s_rule(rule)


def delete_rule(db: Session, rule_id: int, actor: User) -> dict:
    """Never hard-deletes a rule that's already been used to snapshot a
    commission (spec: "do not hard-delete rules already used historically")
    - deactivates instead."""
    rule = get_rule(db, rule_id)
    old = _s_rule(rule)
    used = db.query(AffiliateConversion).filter(AffiliateConversion.commission_rule_id == rule.id).first()
    if used:
        rule.is_active = False
        db.commit()
        log_audit(db, actor=actor, action="deactivate_affiliate_commission_rule", entity_type="affiliate_commission_rule", entity_id=rule.id, old_values=old, new_values=_s_rule(rule))
        db.commit()
        return {"deleted": False, "deactivated": True}
    log_audit(db, actor=actor, action="delete_affiliate_commission_rule", entity_type="affiliate_commission_rule", entity_id=rule.id, old_values=old)
    db.delete(rule)
    db.commit()
    return {"deleted": True, "deactivated": False}
