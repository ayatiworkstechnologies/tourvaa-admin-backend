"""Add Phase 1-3 new module tables

Revision ID: 20260623_0019
Revises: 20260622_0018
Create Date: 2026-06-23
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "20260623_0019"
down_revision = "20260622_0018"
branch_labels = None
depends_on = None


def _has_table(table: str) -> bool:
    return inspect(op.get_bind()).has_table(table)


def upgrade():
    # -----------------------------------------------------------------------
    # 1. Tour Versions
    # -----------------------------------------------------------------------
    if not _has_table("tour_versions"):
        op.create_table(
            "tour_versions",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("tour_id", sa.Integer, sa.ForeignKey("tours.id"), nullable=False, index=True),
            sa.Column("version_number", sa.Integer, nullable=False, default=1),
            sa.Column("snapshot", sa.JSON, nullable=False),
            sa.Column("status", sa.String(30), nullable=False, default="pending_approval"),
            sa.Column("submitted_by", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
            sa.Column("reviewed_by", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
            sa.Column("rejection_reason", sa.Text, nullable=True),
            sa.Column("submitted_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    # -----------------------------------------------------------------------
    # 2. Supplier Ledger
    # -----------------------------------------------------------------------
    if not _has_table("supplier_ledgers"):
        op.create_table(
            "supplier_ledgers",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("supplier_id", sa.Integer, sa.ForeignKey("suppliers.id"), nullable=False, index=True),
            sa.Column("booking_id", sa.Integer, sa.ForeignKey("bookings.id"), nullable=False, index=True),
            sa.Column("gross_amount", sa.Numeric(12, 2), nullable=False, default=0),
            sa.Column("commission_amount", sa.Numeric(12, 2), nullable=False, default=0),
            sa.Column("commission_percentage", sa.Numeric(5, 2), nullable=False, default=0),
            sa.Column("net_payable", sa.Numeric(12, 2), nullable=False, default=0),
            sa.Column("amount_paid", sa.Numeric(12, 2), nullable=False, default=0),
            sa.Column("amount_pending", sa.Numeric(12, 2), nullable=False, default=0),
            sa.Column("currency", sa.String(10), nullable=False, default="USD"),
            sa.Column("status", sa.String(30), nullable=False, default="pending"),
            sa.Column("notes", sa.Text, nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        )

    if not _has_table("supplier_payouts"):
        op.create_table(
            "supplier_payouts",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("payout_code", sa.String(30), unique=True, nullable=True),
            sa.Column("supplier_id", sa.Integer, sa.ForeignKey("suppliers.id"), nullable=False, index=True),
            sa.Column("total_amount", sa.Numeric(12, 2), nullable=False, default=0),
            sa.Column("currency", sa.String(10), nullable=False, default="USD"),
            sa.Column("payment_method", sa.String(50), nullable=False, default="bank_transfer"),
            sa.Column("reference_number", sa.String(150), nullable=True),
            sa.Column("status", sa.String(30), nullable=False, default="pending"),
            sa.Column("notes", sa.Text, nullable=True),
            sa.Column("initiated_by", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
            sa.Column("approved_by", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
            sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        )

    if not _has_table("supplier_payout_items"):
        op.create_table(
            "supplier_payout_items",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("payout_id", sa.Integer, sa.ForeignKey("supplier_payouts.id"), nullable=False, index=True),
            sa.Column("ledger_id", sa.Integer, sa.ForeignKey("supplier_ledgers.id"), nullable=False, index=True),
            sa.Column("amount", sa.Numeric(12, 2), nullable=False, default=0),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    # -----------------------------------------------------------------------
    # 3. Checkout Sessions
    # -----------------------------------------------------------------------
    if not _has_table("checkout_sessions"):
        op.create_table(
            "checkout_sessions",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("session_key", sa.String(64), unique=True, nullable=False),
            sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
            sa.Column("customer_id", sa.Integer, sa.ForeignKey("customers.id"), nullable=True),
            sa.Column("tour_id", sa.Integer, sa.ForeignKey("tours.id"), nullable=True),
            sa.Column("tour_calendar_id", sa.Integer, sa.ForeignKey("tour_calendar.id"), nullable=True),
            sa.Column("step", sa.String(50), nullable=False, default="tour_selection"),
            sa.Column("status", sa.String(30), nullable=False, default="active"),
            sa.Column("data", sa.JSON, nullable=True),
            sa.Column("booking_id", sa.Integer, sa.ForeignKey("bookings.id"), nullable=True),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        )

    # -----------------------------------------------------------------------
    # 4. Website CMS
    # -----------------------------------------------------------------------
    if not _has_table("cms_homepage_banners"):
        op.create_table(
            "cms_homepage_banners",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("title", sa.String(200), nullable=False),
            sa.Column("subtitle", sa.String(400), nullable=True),
            sa.Column("image", sa.String(255), nullable=False),
            sa.Column("cta_text", sa.String(100), nullable=True),
            sa.Column("cta_url", sa.String(500), nullable=True),
            sa.Column("sort_order", sa.Integer, nullable=False, default=0),
            sa.Column("is_active", sa.Boolean, nullable=False, default=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        )

    if not _has_table("cms_popular_destinations"):
        op.create_table(
            "cms_popular_destinations",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("country_id", sa.Integer, sa.ForeignKey("countries.id"), nullable=True),
            sa.Column("city_id", sa.Integer, sa.ForeignKey("cities.id"), nullable=True),
            sa.Column("title", sa.String(200), nullable=False),
            sa.Column("image", sa.String(255), nullable=True),
            sa.Column("description", sa.Text, nullable=True),
            sa.Column("sort_order", sa.Integer, nullable=False, default=0),
            sa.Column("is_active", sa.Boolean, nullable=False, default=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        )

    if not _has_table("cms_popular_tours"):
        op.create_table(
            "cms_popular_tours",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("tour_id", sa.Integer, sa.ForeignKey("tours.id"), nullable=False),
            sa.Column("sort_order", sa.Integer, nullable=False, default=0),
            sa.Column("is_active", sa.Boolean, nullable=False, default=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    if not _has_table("cms_tours_on_deals"):
        op.create_table(
            "cms_tours_on_deals",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("tour_id", sa.Integer, sa.ForeignKey("tours.id"), nullable=False),
            sa.Column("deal_label", sa.String(100), nullable=True),
            sa.Column("discount_percentage", sa.Integer, nullable=False, default=0),
            sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
            sa.Column("sort_order", sa.Integer, nullable=False, default=0),
            sa.Column("is_active", sa.Boolean, nullable=False, default=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        )

    if not _has_table("cms_blogs"):
        op.create_table(
            "cms_blogs",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("title", sa.String(200), nullable=False),
            sa.Column("slug", sa.String(220), unique=True, nullable=False),
            sa.Column("excerpt", sa.Text, nullable=True),
            sa.Column("content", sa.Text, nullable=True),
            sa.Column("featured_image", sa.String(255), nullable=True),
            sa.Column("author", sa.String(120), nullable=True),
            sa.Column("tags", sa.JSON, nullable=True),
            sa.Column("seo_title", sa.String(200), nullable=True),
            sa.Column("seo_description", sa.String(400), nullable=True),
            sa.Column("status", sa.String(20), nullable=False, default="draft"),
            sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_by", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        )

    if not _has_table("cms_customer_reviews"):
        op.create_table(
            "cms_customer_reviews",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("reviewer_name", sa.String(120), nullable=False),
            sa.Column("reviewer_image", sa.String(255), nullable=True),
            sa.Column("rating", sa.Integer, nullable=False, default=5),
            sa.Column("review_text", sa.Text, nullable=False),
            sa.Column("tour_name", sa.String(200), nullable=True),
            sa.Column("country", sa.String(100), nullable=True),
            sa.Column("sort_order", sa.Integer, nullable=False, default=0),
            sa.Column("is_active", sa.Boolean, nullable=False, default=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        )

    if not _has_table("cms_help_centre"):
        op.create_table(
            "cms_help_centre",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("category", sa.String(100), nullable=False),
            sa.Column("question", sa.Text, nullable=False),
            sa.Column("answer", sa.Text, nullable=False),
            sa.Column("sort_order", sa.Integer, nullable=False, default=0),
            sa.Column("is_active", sa.Boolean, nullable=False, default=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        )

    if not _has_table("cms_policies"):
        op.create_table(
            "cms_policies",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("slug", sa.String(80), unique=True, nullable=False),
            sa.Column("title", sa.String(200), nullable=False),
            sa.Column("content", sa.Text, nullable=False),
            sa.Column("last_updated", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        )

    if not _has_table("cms_promotional_popups"):
        op.create_table(
            "cms_promotional_popups",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("title", sa.String(200), nullable=False),
            sa.Column("content", sa.Text, nullable=True),
            sa.Column("image", sa.String(255), nullable=True),
            sa.Column("cta_text", sa.String(100), nullable=True),
            sa.Column("cta_url", sa.String(500), nullable=True),
            sa.Column("display_after_seconds", sa.Integer, nullable=False, default=3),
            sa.Column("display_frequency", sa.String(20), nullable=False, default="once"),
            sa.Column("is_active", sa.Boolean, nullable=False, default=False),
            sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True),
            sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        )

    if not _has_table("cms_external_links"):
        op.create_table(
            "cms_external_links",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("label", sa.String(120), nullable=False),
            sa.Column("url", sa.String(500), nullable=False),
            sa.Column("open_in_new_tab", sa.Boolean, nullable=False, default=True),
            sa.Column("location", sa.String(50), nullable=False, default="footer"),
            sa.Column("sort_order", sa.Integer, nullable=False, default=0),
            sa.Column("is_active", sa.Boolean, nullable=False, default=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        )

    if not _has_table("cms_sitemap_entries"):
        op.create_table(
            "cms_sitemap_entries",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("url", sa.String(500), nullable=False),
            sa.Column("change_frequency", sa.String(20), nullable=False, default="weekly"),
            sa.Column("priority", sa.String(5), nullable=False, default="0.5"),
            sa.Column("last_modified", sa.DateTime(timezone=True), nullable=True),
            sa.Column("is_active", sa.Boolean, nullable=False, default=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        )

    # -----------------------------------------------------------------------
    # 5. Cancellation requests & refund rules
    # -----------------------------------------------------------------------
    if not _has_table("refund_rules"):
        op.create_table(
            "refund_rules",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("tour_id", sa.Integer, sa.ForeignKey("tours.id"), nullable=True),
            sa.Column("days_before_tour_min", sa.Integer, nullable=False),
            sa.Column("days_before_tour_max", sa.Integer, nullable=True),
            sa.Column("refund_percentage", sa.Numeric(5, 2), nullable=False, default=0),
            sa.Column("description", sa.String(255), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        )

    if not _has_table("cancellation_requests"):
        op.create_table(
            "cancellation_requests",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("booking_id", sa.Integer, sa.ForeignKey("bookings.id"), nullable=False),
            sa.Column("customer_id", sa.Integer, sa.ForeignKey("customers.id"), nullable=False),
            sa.Column("reason", sa.Text, nullable=False),
            sa.Column("status", sa.String(30), nullable=False, default="pending"),
            sa.Column("refund_percentage", sa.Numeric(5, 2), nullable=False, default=0),
            sa.Column("refund_amount", sa.Numeric(12, 2), nullable=False, default=0),
            sa.Column("currency", sa.String(10), nullable=False, default="USD"),
            sa.Column("admin_notes", sa.Text, nullable=True),
            sa.Column("reviewed_by", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
            sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("gateway_refund_id", sa.String(150), nullable=True),
            sa.Column("refund_processed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        )

    # -----------------------------------------------------------------------
    # 6. Booking Calendar Events
    # -----------------------------------------------------------------------
    if not _has_table("booking_calendar_events"):
        op.create_table(
            "booking_calendar_events",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("booking_id", sa.Integer, sa.ForeignKey("bookings.id"), nullable=False, unique=True),
            sa.Column("provider", sa.String(30), nullable=False, default="internal"),
            sa.Column("external_event_id", sa.String(255), nullable=True),
            sa.Column("event_url", sa.String(500), nullable=True),
            sa.Column("ical_uid", sa.String(100), nullable=True),
            sa.Column("ics_file_path", sa.String(255), nullable=True),
            sa.Column("sync_status", sa.String(30), nullable=False, default="synced"),
            sa.Column("sync_error", sa.Text, nullable=True),
            sa.Column("retry_count", sa.Integer, nullable=False, default=0),
            sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        )

    # -----------------------------------------------------------------------
    # 7. Affiliate Tracking
    # -----------------------------------------------------------------------
    if not _has_table("affiliate_links"):
        op.create_table(
            "affiliate_links",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("affiliate_id", sa.Integer, sa.ForeignKey("affiliates.id"), nullable=False),
            sa.Column("ref_code", sa.String(60), unique=True, nullable=False),
            sa.Column("destination_url", sa.String(500), nullable=True),
            sa.Column("label", sa.String(120), nullable=True),
            sa.Column("is_active", sa.Boolean, nullable=False, default=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        )

    if not _has_table("affiliate_clicks"):
        op.create_table(
            "affiliate_clicks",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("link_id", sa.Integer, sa.ForeignKey("affiliate_links.id"), nullable=False),
            sa.Column("affiliate_id", sa.Integer, sa.ForeignKey("affiliates.id"), nullable=False),
            sa.Column("ip_address", sa.String(50), nullable=True),
            sa.Column("user_agent", sa.String(500), nullable=True),
            sa.Column("referrer", sa.String(500), nullable=True),
            sa.Column("clicked_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    if not _has_table("affiliate_conversions"):
        op.create_table(
            "affiliate_conversions",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("link_id", sa.Integer, sa.ForeignKey("affiliate_links.id"), nullable=False),
            sa.Column("affiliate_id", sa.Integer, sa.ForeignKey("affiliates.id"), nullable=False),
            sa.Column("booking_id", sa.Integer, sa.ForeignKey("bookings.id"), nullable=False, unique=True),
            sa.Column("booking_amount", sa.Numeric(12, 2), nullable=False, default=0),
            sa.Column("commission_percentage", sa.Numeric(5, 2), nullable=False, default=0),
            sa.Column("commission_amount", sa.Numeric(12, 2), nullable=False, default=0),
            sa.Column("currency", sa.String(10), nullable=False, default="USD"),
            sa.Column("status", sa.String(30), nullable=False, default="pending"),
            sa.Column("converted_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    if not _has_table("affiliate_payouts"):
        op.create_table(
            "affiliate_payouts",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("payout_code", sa.String(30), unique=True, nullable=True),
            sa.Column("affiliate_id", sa.Integer, sa.ForeignKey("affiliates.id"), nullable=False),
            sa.Column("total_amount", sa.Numeric(12, 2), nullable=False, default=0),
            sa.Column("currency", sa.String(10), nullable=False, default="USD"),
            sa.Column("payment_method", sa.String(50), nullable=False, default="bank_transfer"),
            sa.Column("reference_number", sa.String(150), nullable=True),
            sa.Column("status", sa.String(30), nullable=False, default="pending"),
            sa.Column("notes", sa.Text, nullable=True),
            sa.Column("initiated_by", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
            sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        )


def downgrade():
    for table in [
        "affiliate_payouts", "affiliate_conversions", "affiliate_clicks", "affiliate_links",
        "booking_calendar_events",
        "cancellation_requests", "refund_rules",
        "cms_sitemap_entries", "cms_external_links", "cms_promotional_popups", "cms_policies",
        "cms_help_centre", "cms_customer_reviews", "cms_blogs", "cms_tours_on_deals",
        "cms_popular_tours", "cms_popular_destinations", "cms_homepage_banners",
        "checkout_sessions",
        "supplier_payout_items", "supplier_payouts", "supplier_ledgers",
        "tour_versions",
    ]:
        if _has_table(table):
            op.drop_table(table)
