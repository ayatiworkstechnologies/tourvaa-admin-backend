"""Commission rule resolution for the affiliate module.

Single source of truth for "what commission applies to this
affiliate/tour/link combination" so record_conversion (affiliate_tracking.py)
and any admin preview/estimate endpoints don't duplicate the hierarchy.
"""
from decimal import Decimal
from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.affiliate_tracking import AffiliateCommissionRule, AffiliateLink
from app.models.affiliates import Affiliate
from app.utils.money import money, utcnow


def _active_rules(db: Session):
    now = utcnow()
    return (
        db.query(AffiliateCommissionRule)
        .filter(AffiliateCommissionRule.is_active == True)  # noqa: E712
        .filter(or_(AffiliateCommissionRule.valid_from.is_(None), AffiliateCommissionRule.valid_from <= now))
        .filter(or_(AffiliateCommissionRule.valid_until.is_(None), AffiliateCommissionRule.valid_until >= now))
    )


def _best(db: Session, **filters) -> Optional[AffiliateCommissionRule]:
    q = _active_rules(db)
    for key, value in filters.items():
        q = q.filter(getattr(AffiliateCommissionRule, key) == value)
    return q.order_by(AffiliateCommissionRule.priority.desc(), AffiliateCommissionRule.id.desc()).first()


def resolve_affiliate_commission_rule(
    db: Session,
    *,
    affiliate_id: int,
    tour_id: Optional[int] = None,
    category_id: Optional[int] = None,
    affiliate_link_id: Optional[int] = None,
) -> Optional[AffiliateCommissionRule]:
    """Priority: link -> affiliate+tour -> affiliate -> tour -> category -> global default.

    Returns None if no configured rule matches at any level (caller falls
    back to the affiliate's flat Affiliate.commission_percentage, which is
    what every affiliate has always had - this keeps existing affiliates
    working exactly as before if nobody ever creates a commission rule).
    """
    if affiliate_link_id:
        rule = _best(db, affiliate_link_id=affiliate_link_id)
        if rule:
            return rule

    if tour_id:
        rule = _best(db, affiliate_id=affiliate_id, tour_id=tour_id)
        if rule:
            return rule

    rule = _best(db, affiliate_id=affiliate_id, tour_id=None, category_id=None, affiliate_link_id=None)
    if rule:
        return rule

    if tour_id:
        rule = _best(db, affiliate_id=None, tour_id=tour_id, category_id=None, affiliate_link_id=None)
        if rule:
            return rule

    if category_id:
        rule = _best(db, affiliate_id=None, tour_id=None, category_id=category_id, affiliate_link_id=None)
        if rule:
            return rule

    return _best(db, affiliate_id=None, tour_id=None, category_id=None, affiliate_link_id=None)


def compute_commission(
    db: Session,
    *,
    affiliate: Affiliate,
    link: AffiliateLink,
    eligible_amount: Decimal,
) -> dict:
    """Resolve the applicable rate/rule and compute the commission amount.

    Link-level overrides (set directly on the link by whoever created it -
    admin or, per allowed self-service fields, the affiliate) win outright,
    matching spec's "link specific" being priority 1 of the hierarchy - they
    don't need a row in affiliate_commission_rules.
    """
    eligible_amount = money(eligible_amount)

    if link.commission_type_override:
        commission_type = link.commission_type_override
        percentage = money(link.commission_percentage_override or 0)
        fixed_amount = money(link.commission_fixed_override or 0)
        rule_id = None
    else:
        rule = resolve_affiliate_commission_rule(
            db,
            affiliate_id=affiliate.id,
            tour_id=link.tour_id,
            category_id=getattr(link.tour, "category_id", None) if link.tour_id else None,
            affiliate_link_id=link.id,
        )
        if rule:
            commission_type = rule.commission_type
            percentage = money(rule.percentage or 0)
            fixed_amount = money(rule.fixed_amount or 0)
            rule_id = rule.id
        else:
            commission_type = "percentage"
            percentage = money(affiliate.commission_percentage or 0)
            fixed_amount = money(0)
            rule_id = None

    if commission_type == "fixed":
        commission_amount = fixed_amount
    else:
        commission_amount = money((eligible_amount * percentage) / 100)

    return {
        "commission_rule_id": rule_id,
        "commission_type": commission_type,
        "commission_percentage": percentage if commission_type == "percentage" else money(0),
        "commission_fixed_amount": fixed_amount if commission_type == "fixed" else money(0),
        "commission_amount": commission_amount,
    }
