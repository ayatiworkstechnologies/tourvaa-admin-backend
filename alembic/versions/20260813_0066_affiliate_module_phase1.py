"""Affiliate module phase 1: link enrichment, attribution, commission rules,
payout lifecycle, payout methods/items, and wallet ledger.

Revision ID: 20260813_0066
Revises: 20260813_0065
Create Date: 2026-08-13
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260813_0066"
down_revision = "20260813_0065"
branch_labels = None
depends_on = None


def _has_table(inspector, table: str) -> bool:
    return table in inspector.get_table_names()


def _has_column(inspector, table: str, column: str) -> bool:
    return column in {c["name"] for c in inspector.get_columns(table)}


def _add_column_if_missing(inspector, table, column):
    if not _has_column(inspector, table, column.name):
        op.add_column(table, column)


def upgrade():
    bind = op.get_bind()
    inspector = inspect(bind)

    # --- extend affiliate_links -------------------------------------------------
    link_columns = [
        sa.Column("link_type", sa.String(length=20), nullable=False, server_default="custom"),
        sa.Column("tour_id", sa.Integer(), sa.ForeignKey("tours.id"), nullable=True),
        sa.Column("campaign_name", sa.String(length=150), nullable=True),
        sa.Column("utm_source", sa.String(length=100), nullable=True),
        sa.Column("utm_medium", sa.String(length=100), nullable=True),
        sa.Column("utm_campaign", sa.String(length=100), nullable=True),
        sa.Column("utm_content", sa.String(length=100), nullable=True),
        sa.Column("utm_term", sa.String(length=100), nullable=True),
        sa.Column("custom_alias", sa.String(length=100), nullable=True),
        sa.Column("commission_type_override", sa.String(length=20), nullable=True),
        sa.Column("commission_percentage_override", sa.Numeric(5, 2), nullable=True),
        sa.Column("commission_fixed_override", sa.Numeric(12, 2), nullable=True),
        sa.Column("attribution_model", sa.String(length=20), nullable=False, server_default="last_click"),
        sa.Column("attribution_window_days", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    ]
    for col in link_columns:
        _add_column_if_missing(inspector, "affiliate_links", col)
    existing_link_indexes = {ix["name"] for ix in inspector.get_indexes("affiliate_links")}
    if "ix_affiliate_links_custom_alias" not in existing_link_indexes:
        op.create_index("ix_affiliate_links_custom_alias", "affiliate_links", ["custom_alias"], unique=True)
    if "ix_affiliate_links_status" not in existing_link_indexes:
        op.create_index("ix_affiliate_links_status", "affiliate_links", ["status"])
    if "ix_affiliate_links_tour_id" not in existing_link_indexes:
        op.create_index("ix_affiliate_links_tour_id", "affiliate_links", ["tour_id"])
    # backfill status from the existing is_active flag so current links keep working
    op.execute("UPDATE affiliate_links SET status = CASE WHEN is_active = 1 THEN 'active' ELSE 'disabled' END")

    # --- affiliate_commission_rules ---------------------------------------------
    if not _has_table(inspector, "affiliate_commission_rules"):
        op.create_table(
            "affiliate_commission_rules",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("name", sa.String(length=150), nullable=True),
            sa.Column("affiliate_id", sa.Integer(), sa.ForeignKey("affiliates.id"), nullable=True),
            sa.Column("tour_id", sa.Integer(), sa.ForeignKey("tours.id"), nullable=True),
            sa.Column("category_id", sa.Integer(), sa.ForeignKey("tour_categories.id"), nullable=True),
            sa.Column("affiliate_link_id", sa.Integer(), sa.ForeignKey("affiliate_links.id"), nullable=True),
            sa.Column("commission_type", sa.String(length=20), nullable=False, server_default="percentage"),
            sa.Column("percentage", sa.Numeric(5, 2), nullable=False, server_default="0"),
            sa.Column("fixed_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
            sa.Column("currency", sa.String(length=10), nullable=False, server_default="USD"),
            sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True),
            sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
            sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("updated_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index("ix_affiliate_commission_rules_affiliate_id", "affiliate_commission_rules", ["affiliate_id"])
        op.create_index("ix_affiliate_commission_rules_tour_id", "affiliate_commission_rules", ["tour_id"])
        op.create_index("ix_affiliate_commission_rules_category_id", "affiliate_commission_rules", ["category_id"])
        op.create_index("ix_affiliate_commission_rules_affiliate_link_id", "affiliate_commission_rules", ["affiliate_link_id"])
        op.create_index("ix_affiliate_commission_rules_is_active", "affiliate_commission_rules", ["is_active"])

    # --- affiliate_attributions ---------------------------------------------------
    if not _has_table(inspector, "affiliate_attributions"):
        op.create_table(
            "affiliate_attributions",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("affiliate_id", sa.Integer(), sa.ForeignKey("affiliates.id"), nullable=False),
            sa.Column("affiliate_link_id", sa.Integer(), sa.ForeignKey("affiliate_links.id"), nullable=False),
            sa.Column("affiliate_click_id", sa.Integer(), sa.ForeignKey("affiliate_clicks.id"), nullable=True),
            sa.Column("visitor_id", sa.String(length=64), nullable=False),
            sa.Column("session_id", sa.String(length=64), nullable=True),
            sa.Column("booking_id", sa.Integer(), sa.ForeignKey("bookings.id"), nullable=True),
            sa.Column("attribution_model", sa.String(length=20), nullable=False, server_default="last_click"),
            sa.Column("attributed_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index("ix_affiliate_attributions_affiliate_id", "affiliate_attributions", ["affiliate_id"])
        op.create_index("ix_affiliate_attributions_affiliate_link_id", "affiliate_attributions", ["affiliate_link_id"])
        op.create_index("ix_affiliate_attributions_affiliate_click_id", "affiliate_attributions", ["affiliate_click_id"])
        op.create_index("ix_affiliate_attributions_visitor_id", "affiliate_attributions", ["visitor_id"])
        op.create_index("ix_affiliate_attributions_booking_id", "affiliate_attributions", ["booking_id"])
        op.create_index("ix_affiliate_attributions_expires_at", "affiliate_attributions", ["expires_at"])
        op.create_index("ix_affiliate_attributions_status", "affiliate_attributions", ["status"])

    # --- bookings.affiliate_attribution_id ---------------------------------------
    if not _has_column(inspector, "bookings", "affiliate_attribution_id"):
        op.add_column(
            "bookings",
            sa.Column("affiliate_attribution_id", sa.Integer(), sa.ForeignKey("affiliate_attributions.id"), nullable=True),
        )
        op.create_index("ix_bookings_affiliate_attribution_id", "bookings", ["affiliate_attribution_id"])

    # --- extend affiliate_conversions ---------------------------------------------
    conversion_columns = [
        sa.Column("commission_rule_id", sa.Integer(), sa.ForeignKey("affiliate_commission_rules.id"), nullable=True),
        sa.Column("eligible_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("original_commission", sa.Numeric(12, 2), nullable=True),
        sa.Column("adjustment_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("final_commission", sa.Numeric(12, 2), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=True),
    ]
    for col in conversion_columns:
        _add_column_if_missing(inspector, "affiliate_conversions", col)
    op.execute("UPDATE affiliate_conversions SET eligible_amount = booking_amount WHERE eligible_amount = 0")
    op.execute("UPDATE affiliate_conversions SET original_commission = commission_amount WHERE original_commission IS NULL")
    op.execute("UPDATE affiliate_conversions SET final_commission = commission_amount WHERE final_commission IS NULL")

    # --- affiliate_payout_methods --------------------------------------------------
    if not _has_table(inspector, "affiliate_payout_methods"):
        op.create_table(
            "affiliate_payout_methods",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("affiliate_id", sa.Integer(), sa.ForeignKey("affiliates.id"), nullable=False),
            sa.Column("method_type", sa.String(length=30), nullable=False, server_default="bank_transfer"),
            sa.Column("account_holder_name", sa.String(length=150), nullable=False, server_default=""),
            sa.Column("bank_name", sa.String(length=150), nullable=False, server_default=""),
            sa.Column("account_number", sa.String(length=100), nullable=False, server_default=""),
            sa.Column("ifsc", sa.String(length=30), nullable=False, server_default=""),
            sa.Column("swift_code", sa.String(length=30), nullable=False, server_default=""),
            sa.Column("bank_country", sa.String(length=100), nullable=False, server_default=""),
            sa.Column("paypal_email", sa.String(length=150), nullable=False, server_default=""),
            sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index("ix_affiliate_payout_methods_affiliate_id", "affiliate_payout_methods", ["affiliate_id"])

    # --- extend affiliate_payouts --------------------------------------------------
    payout_columns = [
        sa.Column("payout_method_id", sa.Integer(), sa.ForeignKey("affiliate_payout_methods.id"), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejected_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("rejection_reason", sa.String(length=255), nullable=True),
        sa.Column("processing_at", sa.DateTime(timezone=True), nullable=True),
    ]
    for col in payout_columns:
        _add_column_if_missing(inspector, "affiliate_payouts", col)

    # --- affiliate_payout_items ------------------------------------------------------
    if not _has_table(inspector, "affiliate_payout_items"):
        op.create_table(
            "affiliate_payout_items",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("payout_id", sa.Integer(), sa.ForeignKey("affiliate_payouts.id"), nullable=False),
            sa.Column("conversion_id", sa.Integer(), sa.ForeignKey("affiliate_conversions.id"), nullable=False),
            sa.Column("amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index("ix_affiliate_payout_items_payout_id", "affiliate_payout_items", ["payout_id"])
        op.create_index("ix_affiliate_payout_items_conversion_id", "affiliate_payout_items", ["conversion_id"])

    # --- affiliate_wallet_transactions -----------------------------------------------
    if not _has_table(inspector, "affiliate_wallet_transactions"):
        op.create_table(
            "affiliate_wallet_transactions",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("affiliate_id", sa.Integer(), sa.ForeignKey("affiliates.id"), nullable=False),
            sa.Column("commission_id", sa.Integer(), sa.ForeignKey("affiliate_conversions.id"), nullable=True),
            sa.Column("payout_id", sa.Integer(), sa.ForeignKey("affiliate_payouts.id"), nullable=True),
            sa.Column("transaction_type", sa.String(length=30), nullable=False),
            sa.Column("amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
            sa.Column("currency", sa.String(length=10), nullable=False, server_default="USD"),
            sa.Column("reference_type", sa.String(length=30), nullable=True),
            sa.Column("reference_id", sa.Integer(), nullable=True),
            sa.Column("description", sa.String(length=255), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index("ix_affiliate_wallet_transactions_affiliate_id", "affiliate_wallet_transactions", ["affiliate_id"])
        op.create_index("ix_affiliate_wallet_transactions_commission_id", "affiliate_wallet_transactions", ["commission_id"])
        op.create_index("ix_affiliate_wallet_transactions_payout_id", "affiliate_wallet_transactions", ["payout_id"])
        op.create_index("ix_affiliate_wallet_transactions_transaction_type", "affiliate_wallet_transactions", ["transaction_type"])
        op.create_index("ix_affiliate_wallet_transactions_created_at", "affiliate_wallet_transactions", ["created_at"])


def downgrade():
    bind = op.get_bind()
    inspector = inspect(bind)

    for table in (
        "affiliate_wallet_transactions",
        "affiliate_payout_items",
    ):
        if _has_table(inspector, table):
            op.drop_table(table)

    for col in (
        "payout_method_id", "requested_at", "approved_at", "approved_by",
        "rejected_at", "rejected_by", "rejection_reason", "processing_at",
    ):
        if _has_column(inspector, "affiliate_payouts", col):
            op.drop_column("affiliate_payouts", col)

    if _has_table(inspector, "affiliate_payout_methods"):
        op.drop_table("affiliate_payout_methods")

    for col in (
        "commission_rule_id", "eligible_amount", "original_commission",
        "adjustment_amount", "final_commission", "approved_at", "available_at",
    ):
        if _has_column(inspector, "affiliate_conversions", col):
            op.drop_column("affiliate_conversions", col)

    if _has_column(inspector, "bookings", "affiliate_attribution_id"):
        op.drop_column("bookings", "affiliate_attribution_id")

    if _has_table(inspector, "affiliate_attributions"):
        op.drop_table("affiliate_attributions")

    if _has_table(inspector, "affiliate_commission_rules"):
        op.drop_table("affiliate_commission_rules")

    for col in (
        "link_type", "tour_id", "campaign_name", "utm_source", "utm_medium",
        "utm_campaign", "utm_content", "utm_term", "custom_alias",
        "commission_type_override", "commission_percentage_override",
        "commission_fixed_override", "attribution_model", "attribution_window_days",
        "valid_from", "valid_until", "status", "created_by", "updated_by", "deleted_at",
    ):
        if _has_column(inspector, "affiliate_links", col):
            op.drop_column("affiliate_links", col)
