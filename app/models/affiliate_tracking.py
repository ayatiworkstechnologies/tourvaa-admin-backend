from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class AffiliateLink(Base):
    """Unique referral links generated per affiliate."""
    __tablename__ = "affiliate_links"

    id = Column(Integer, primary_key=True, index=True)
    affiliate_id = Column(Integer, ForeignKey("affiliates.id"), nullable=False, index=True)
    ref_code = Column(String(60), unique=True, nullable=False, index=True)
    destination_url = Column(String(500), nullable=True)
    label = Column(String(120), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)

    # link_type/tour_id: TOUR links resolve destination_url from the tour at
    # render time so admin doesn't have to keep it in sync if the tour slug
    # changes; CUSTOM links use destination_url as entered. CATEGORY/DESTINATION
    # are accepted values but not yet resolved server-side (first
    # implementation only fully supports TOUR/CUSTOM per product spec).
    link_type = Column(String(20), default="custom", nullable=False)
    tour_id = Column(Integer, ForeignKey("tours.id"), nullable=True, index=True)

    campaign_name = Column(String(150), nullable=True)
    utm_source = Column(String(100), nullable=True)
    utm_medium = Column(String(100), nullable=True)
    utm_campaign = Column(String(100), nullable=True)
    utm_content = Column(String(100), nullable=True)
    utm_term = Column(String(100), nullable=True)

    custom_alias = Column(String(100), unique=True, nullable=True, index=True)

    commission_type_override = Column(String(20), nullable=True)
    commission_percentage_override = Column(Numeric(5, 2), nullable=True)
    commission_fixed_override = Column(Numeric(12, 2), nullable=True)

    attribution_model = Column(String(20), default="last_click", nullable=False)
    attribution_window_days = Column(Integer, default=30, nullable=False)

    valid_from = Column(DateTime(timezone=True), nullable=True)
    valid_until = Column(DateTime(timezone=True), nullable=True)

    # draft, active, disabled, expired, deleted. is_active is kept in sync by
    # the service layer for any older code path that still reads the bool.
    status = Column(String(20), default="active", nullable=False, index=True)

    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    updated_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    affiliate = relationship("Affiliate")
    tour = relationship("Tour")
    clicks = relationship("AffiliateClick", back_populates="link", cascade="all, delete-orphan")
    conversions = relationship("AffiliateConversion", back_populates="link", cascade="all, delete-orphan")


class AffiliateClick(Base):
    __tablename__ = "affiliate_clicks"

    id = Column(Integer, primary_key=True, index=True)
    link_id = Column(Integer, ForeignKey("affiliate_links.id"), nullable=False, index=True)
    affiliate_id = Column(Integer, ForeignKey("affiliates.id"), nullable=False, index=True)
    ip_address = Column(String(50), nullable=True)
    user_agent = Column(String(500), nullable=True)
    referrer = Column(String(500), nullable=True)
    clicked_at = Column(DateTime(timezone=True), server_default=func.now())

    link = relationship("AffiliateLink", back_populates="clicks")


class AffiliateAttribution(Base):
    """Persists a click's referral into an expiring, server-validated window.

    A booking created while a valid (unexpired, unconsumed) attribution
    exists for the same visitor attaches to it. Distinct from AffiliateClick
    (which is just a hit log) so that attribution lifetime/expiry/model
    (first vs last click) can be reasoned about independently of raw click
    volume.
    """
    __tablename__ = "affiliate_attributions"

    id = Column(Integer, primary_key=True, index=True)
    affiliate_id = Column(Integer, ForeignKey("affiliates.id"), nullable=False, index=True)
    affiliate_link_id = Column(Integer, ForeignKey("affiliate_links.id"), nullable=False, index=True)
    affiliate_click_id = Column(Integer, ForeignKey("affiliate_clicks.id"), nullable=True, index=True)

    visitor_id = Column(String(64), nullable=False, index=True)
    session_id = Column(String(64), nullable=True)

    booking_id = Column(Integer, ForeignKey("bookings.id"), nullable=True, index=True)

    attribution_model = Column(String(20), default="last_click", nullable=False)
    attributed_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)

    # active, consumed (attached to a booking), expired
    status = Column(String(20), default="active", nullable=False, index=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    affiliate = relationship("Affiliate")
    link = relationship("AffiliateLink")
    click = relationship("AffiliateClick")
    booking = relationship("Booking", foreign_keys=[booking_id])


class AffiliateCommissionRule(Base):
    """Configurable commission resolved by affiliate_commission.resolve_affiliate_commission_rule.

    All scope columns are nullable; the resolver's priority order (link >
    affiliate+tour > affiliate > tour > category > global default) is what
    gives meaning to which combination of nulls a row has - see
    app/services/affiliate_commission.py.
    """
    __tablename__ = "affiliate_commission_rules"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(150), nullable=True)

    affiliate_id = Column(Integer, ForeignKey("affiliates.id"), nullable=True, index=True)
    tour_id = Column(Integer, ForeignKey("tours.id"), nullable=True, index=True)
    category_id = Column(Integer, ForeignKey("tour_categories.id"), nullable=True, index=True)
    affiliate_link_id = Column(Integer, ForeignKey("affiliate_links.id"), nullable=True, index=True)

    commission_type = Column(String(20), default="percentage", nullable=False)
    percentage = Column(Numeric(5, 2), default=0, nullable=False)
    fixed_amount = Column(Numeric(12, 2), default=0, nullable=False)
    currency = Column(String(10), default="USD", nullable=False)

    valid_from = Column(DateTime(timezone=True), nullable=True)
    valid_until = Column(DateTime(timezone=True), nullable=True)

    priority = Column(Integer, default=0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False, index=True)

    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    updated_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    affiliate = relationship("Affiliate")
    tour = relationship("Tour")
    affiliate_link = relationship("AffiliateLink")


class AffiliateConversion(Base):
    __tablename__ = "affiliate_conversions"

    id = Column(Integer, primary_key=True, index=True)
    link_id = Column(Integer, ForeignKey("affiliate_links.id"), nullable=False, index=True)
    affiliate_id = Column(Integer, ForeignKey("affiliates.id"), nullable=False, index=True)
    booking_id = Column(Integer, ForeignKey("bookings.id"), nullable=False, unique=True, index=True)
    commission_rule_id = Column(Integer, ForeignKey("affiliate_commission_rules.id"), nullable=True, index=True)

    booking_amount = Column(Numeric(12, 2), default=0, nullable=False)
    eligible_amount = Column(Numeric(12, 2), default=0, nullable=False)
    commission_percentage = Column(Numeric(5, 2), default=0, nullable=False)
    commission_amount = Column(Numeric(12, 2), default=0, nullable=False)

    # original_commission is set once at creation and never rewritten;
    # adjustment_amount/final_commission absorb later partial-refund
    # recalculation so the original figure stays auditable. commission_amount
    # is kept as the "current amount" existing callers already read and is
    # kept equal to final_commission going forward.
    original_commission = Column(Numeric(12, 2), nullable=True)
    adjustment_amount = Column(Numeric(12, 2), default=0, nullable=False)
    final_commission = Column(Numeric(12, 2), nullable=True)

    currency = Column(String(10), default="USD", nullable=False)
    status = Column(String(30), default="pending", nullable=False, index=True)
    # pending, confirmed, available, paid, void, reversed

    approved_at = Column(DateTime(timezone=True), nullable=True)
    available_at = Column(DateTime(timezone=True), nullable=True)
    converted_at = Column(DateTime(timezone=True), server_default=func.now())

    link = relationship("AffiliateLink", back_populates="conversions")
    booking = relationship("Booking")
    commission_rule = relationship("AffiliateCommissionRule")


class AffiliatePayoutMethod(Base):
    __tablename__ = "affiliate_payout_methods"

    id = Column(Integer, primary_key=True, index=True)
    affiliate_id = Column(Integer, ForeignKey("affiliates.id"), nullable=False, index=True)

    method_type = Column(String(30), default="bank_transfer", nullable=False)
    account_holder_name = Column(String(150), default="", nullable=False)
    bank_name = Column(String(150), default="", nullable=False)
    account_number = Column(String(100), default="", nullable=False)
    ifsc = Column(String(30), default="", nullable=False)
    swift_code = Column(String(30), default="", nullable=False)
    bank_country = Column(String(100), default="", nullable=False)
    paypal_email = Column(String(150), default="", nullable=False)

    is_default = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    affiliate = relationship("Affiliate")


class AffiliatePayout(Base):
    __tablename__ = "affiliate_payouts"

    id = Column(Integer, primary_key=True, index=True)
    payout_code = Column(String(30), unique=True, nullable=True, index=True)
    affiliate_id = Column(Integer, ForeignKey("affiliates.id"), nullable=False, index=True)
    payout_method_id = Column(Integer, ForeignKey("affiliate_payout_methods.id"), nullable=True)

    total_amount = Column(Numeric(12, 2), default=0, nullable=False)
    currency = Column(String(10), default="USD", nullable=False)
    payment_method = Column(String(50), default="bank_transfer", nullable=False)
    reference_number = Column(String(150), nullable=True)

    # requested, approved, processing, paid, rejected, cancelled. The older
    # admin-direct-pay endpoint (create_payout) still writes "pending"/"paid"
    # directly - both vocabularies coexist since this is a plain string
    # column, not an enum type.
    status = Column(String(30), default="pending", nullable=False, index=True)

    notes = Column(Text, nullable=True)
    requested_at = Column(DateTime(timezone=True), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    approved_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    rejected_at = Column(DateTime(timezone=True), nullable=True)
    rejected_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    rejection_reason = Column(String(255), nullable=True)
    processing_at = Column(DateTime(timezone=True), nullable=True)
    initiated_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    paid_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    affiliate = relationship("Affiliate")
    payout_method = relationship("AffiliatePayoutMethod")
    initiator = relationship("User", foreign_keys=[initiated_by])
    approver = relationship("User", foreign_keys=[approved_by])
    rejecter = relationship("User", foreign_keys=[rejected_by])
    items = relationship("AffiliatePayoutItem", back_populates="payout", cascade="all, delete-orphan")


class AffiliatePayoutItem(Base):
    """Links a payout to the specific conversions it settles."""
    __tablename__ = "affiliate_payout_items"

    id = Column(Integer, primary_key=True, index=True)
    payout_id = Column(Integer, ForeignKey("affiliate_payouts.id"), nullable=False, index=True)
    conversion_id = Column(Integer, ForeignKey("affiliate_conversions.id"), nullable=False, index=True)
    amount = Column(Numeric(12, 2), default=0, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    payout = relationship("AffiliatePayout", back_populates="items")
    conversion = relationship("AffiliateConversion")


class AffiliateWalletTransaction(Base):
    """Append-only ledger. Balances are computed by summing this table
    rather than trusting a mutable cached balance column (same principle as
    AffiliateConversion status aggregation in get_commissions, just at
    transaction granularity so holds/releases are individually auditable).
    """
    __tablename__ = "affiliate_wallet_transactions"

    id = Column(Integer, primary_key=True, index=True)
    affiliate_id = Column(Integer, ForeignKey("affiliates.id"), nullable=False, index=True)
    commission_id = Column(Integer, ForeignKey("affiliate_conversions.id"), nullable=True, index=True)
    payout_id = Column(Integer, ForeignKey("affiliate_payouts.id"), nullable=True, index=True)

    # COMMISSION_CREDIT, COMMISSION_ADJUSTMENT, PAYOUT_HOLD, PAYOUT_RELEASE,
    # PAYOUT_DEBIT, MANUAL_ADJUSTMENT
    transaction_type = Column(String(30), nullable=False, index=True)

    amount = Column(Numeric(12, 2), default=0, nullable=False)
    currency = Column(String(10), default="USD", nullable=False)

    reference_type = Column(String(30), nullable=True)
    reference_id = Column(Integer, nullable=True)
    description = Column(String(255), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    affiliate = relationship("Affiliate")
    commission = relationship("AffiliateConversion")
    payout = relationship("AffiliatePayout")
