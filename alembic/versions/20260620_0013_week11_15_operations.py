"""Week 11-15 operations modules

Revision ID: 20260620_0013
Revises: 20260618_0012
Create Date: 2026-06-20
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "20260620_0013"
down_revision = "20260618_0012"
branch_labels = None
depends_on = None


def _has_table(inspector, table):
    return table in inspector.get_table_names()


def _cols(inspector, table):
    if not _has_table(inspector, table):
        return set()
    return {c["name"] for c in inspector.get_columns(table)}


def _add(table, col, existing):
    if col.name not in existing:
        op.add_column(table, col)
        existing.add(col.name)


def _idx(name, table, cols, unique=False):
    bind = op.get_bind()
    inspector = inspect(bind)
    names = {i["name"] for i in inspector.get_indexes(table)}
    if name not in names:
        op.create_index(name, table, cols, unique=unique)


def upgrade():
    inspector = inspect(op.get_bind())

    booking_cols = _cols(inspector, "bookings")
    for col in [
        sa.Column("tour_calendar_id", sa.Integer(), nullable=True),
        sa.Column("booked_by_user_id", sa.Integer(), nullable=True),
        sa.Column("booking_source", sa.String(30), nullable=False, server_default="admin"),
        sa.Column("country_id", sa.Integer(), nullable=True),
        sa.Column("city_id", sa.Integer(), nullable=True),
        sa.Column("tour_start_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tour_end_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("adults_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("children_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_travellers", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("currency", sa.String(10), nullable=False, server_default="USD"),
        sa.Column("base_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("optional_activity_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("accommodation_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("extension_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("discount_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("promo_code", sa.String(100), nullable=True),
        sa.Column("tax_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("surcharge_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("final_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("supplier_acceptance_status", sa.String(30), nullable=False, server_default="not_assigned"),
        sa.Column("payment_type", sa.String(30), nullable=False, server_default="full"),
        sa.Column("customer_notes", sa.Text(), nullable=True),
        sa.Column("admin_notes", sa.Text(), nullable=True),
    ]:
        _add("bookings", col, booking_cols)

    payment_cols = _cols(inspector, "payments")
    for col in [
        sa.Column("gateway", sa.String(50), nullable=False, server_default="manual"),
        sa.Column("gateway_payment_id", sa.String(150), nullable=True),
        sa.Column("gateway_order_id", sa.String(150), nullable=True),
        sa.Column("idempotency_key", sa.String(150), nullable=True),
        sa.Column("authorized_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("captured_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("surcharge_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
    ]:
        _add("payments", col, payment_cols)

    if not _has_table(inspector, "booking_travellers"):
        op.create_table("booking_travellers", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("booking_id", sa.Integer(), sa.ForeignKey("bookings.id"), nullable=False), sa.Column("traveller_type", sa.String(20), nullable=False), sa.Column("first_name", sa.String(100), nullable=False, server_default=""), sa.Column("last_name", sa.String(100), nullable=False, server_default=""), sa.Column("full_name", sa.String(220), nullable=False, server_default=""), sa.Column("date_of_birth", sa.DateTime(timezone=True), nullable=True), sa.Column("age", sa.Integer(), nullable=True), sa.Column("gender", sa.String(30), nullable=True), sa.Column("nationality", sa.String(100), nullable=True), sa.Column("passport_number", sa.String(100), nullable=True), sa.Column("passport_expiry_date", sa.DateTime(timezone=True), nullable=True), sa.Column("email", sa.String(150), nullable=True), sa.Column("phone", sa.String(50), nullable=True), sa.Column("is_primary_contact", sa.Integer(), nullable=False, server_default="0"), sa.Column("special_requirements", sa.Text(), nullable=True), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()))
        op.create_index("ix_booking_travellers_booking_id", "booking_travellers", ["booking_id"])

    if not _has_table(inspector, "booking_optional_activities"):
        op.create_table("booking_optional_activities", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("booking_id", sa.Integer(), sa.ForeignKey("bookings.id"), nullable=False), sa.Column("tour_optional_activity_id", sa.Integer(), sa.ForeignKey("tour_optional_activities.id"), nullable=True), sa.Column("activity_name_snapshot", sa.String(255), nullable=False), sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"), sa.Column("unit_price", sa.Numeric(12, 2), nullable=False, server_default="0"), sa.Column("total_price", sa.Numeric(12, 2), nullable=False, server_default="0"), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()))
        op.create_index("ix_booking_optional_activities_booking_id", "booking_optional_activities", ["booking_id"])

    if not _has_table(inspector, "booking_accommodations"):
        op.create_table("booking_accommodations", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("booking_id", sa.Integer(), sa.ForeignKey("bookings.id"), nullable=False), sa.Column("tour_accommodation_extra_id", sa.Integer(), sa.ForeignKey("tour_accommodation_extras.id"), nullable=True), sa.Column("accommodation_name_snapshot", sa.String(255), nullable=False), sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"), sa.Column("price_type", sa.String(30), nullable=False, server_default="per_person"), sa.Column("unit_price", sa.Numeric(12, 2), nullable=False, server_default="0"), sa.Column("total_price", sa.Numeric(12, 2), nullable=False, server_default="0"), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()))
        op.create_index("ix_booking_accommodations_booking_id", "booking_accommodations", ["booking_id"])

    if not _has_table(inspector, "booking_extensions"):
        op.create_table("booking_extensions", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("booking_id", sa.Integer(), sa.ForeignKey("bookings.id"), nullable=False), sa.Column("tour_extension_id", sa.Integer(), sa.ForeignKey("tour_extensions.id"), nullable=True), sa.Column("extension_tour_id", sa.Integer(), sa.ForeignKey("tours.id"), nullable=True), sa.Column("extension_name_snapshot", sa.String(255), nullable=False), sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"), sa.Column("unit_price", sa.Numeric(12, 2), nullable=False, server_default="0"), sa.Column("total_price", sa.Numeric(12, 2), nullable=False, server_default="0"), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()))
        op.create_index("ix_booking_extensions_booking_id", "booking_extensions", ["booking_id"])

    if not _has_table(inspector, "booking_status_history"):
        op.create_table("booking_status_history", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("booking_id", sa.Integer(), sa.ForeignKey("bookings.id"), nullable=False), sa.Column("old_status", sa.String(30), nullable=True), sa.Column("new_status", sa.String(30), nullable=False), sa.Column("changed_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True), sa.Column("change_source", sa.String(30), nullable=False, server_default="admin"), sa.Column("reason", sa.Text(), nullable=True), sa.Column("metadata_json", sa.JSON(), nullable=True), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()))
        op.create_index("ix_booking_status_history_booking_id", "booking_status_history", ["booking_id"])

    if not _has_table(inspector, "booking_communications"):
        op.create_table("booking_communications", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("booking_id", sa.Integer(), sa.ForeignKey("bookings.id"), nullable=False), sa.Column("sender_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True), sa.Column("sender_type", sa.String(30), nullable=False, server_default="admin"), sa.Column("message_type", sa.String(30), nullable=False, server_default="admin_message"), sa.Column("subject", sa.String(255), nullable=False, server_default=""), sa.Column("message", sa.Text(), nullable=False), sa.Column("visibility", sa.String(30), nullable=False, server_default="internal"), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()))
        op.create_index("ix_booking_communications_booking_id", "booking_communications", ["booking_id"])

    if not _has_table(inspector, "payment_transactions"):
        op.create_table("payment_transactions", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("payment_id", sa.Integer(), sa.ForeignKey("payments.id"), nullable=False), sa.Column("booking_id", sa.Integer(), sa.ForeignKey("bookings.id"), nullable=False), sa.Column("transaction_type", sa.String(30), nullable=False), sa.Column("amount", sa.Numeric(12, 2), nullable=False, server_default="0"), sa.Column("status", sa.String(30), nullable=False, server_default="success"), sa.Column("gateway_reference", sa.String(150), nullable=True), sa.Column("metadata_json", sa.JSON(), nullable=True), sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()))
        op.create_index("ix_payment_transactions_payment_id", "payment_transactions", ["payment_id"])

    if not _has_table(inspector, "payment_holds"):
        op.create_table("payment_holds", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("payment_id", sa.Integer(), sa.ForeignKey("payments.id"), nullable=False), sa.Column("booking_id", sa.Integer(), sa.ForeignKey("bookings.id"), nullable=False), sa.Column("hold_amount", sa.Numeric(12, 2), nullable=False, server_default="0"), sa.Column("captured_amount", sa.Numeric(12, 2), nullable=False, server_default="0"), sa.Column("released_amount", sa.Numeric(12, 2), nullable=False, server_default="0"), sa.Column("status", sa.String(30), nullable=False, server_default="active"), sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()))
        op.create_index("ix_payment_holds_payment_id", "payment_holds", ["payment_id"])

    if not _has_table(inspector, "invoices"):
        op.create_table("invoices", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("invoice_number", sa.String(40), nullable=False, unique=True), sa.Column("booking_id", sa.Integer(), sa.ForeignKey("bookings.id"), nullable=False), sa.Column("payment_id", sa.Integer(), sa.ForeignKey("payments.id"), nullable=True), sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=False), sa.Column("invoice_type", sa.String(30), nullable=False, server_default="tax_invoice"), sa.Column("status", sa.String(30), nullable=False, server_default="generated"), sa.Column("currency", sa.String(10), nullable=False, server_default="USD"), sa.Column("subtotal_amount", sa.Numeric(12, 2), nullable=False, server_default="0"), sa.Column("gst_amount", sa.Numeric(12, 2), nullable=False, server_default="0"), sa.Column("total_amount", sa.Numeric(12, 2), nullable=False, server_default="0"), sa.Column("amount_paid", sa.Numeric(12, 2), nullable=False, server_default="0"), sa.Column("amount_due", sa.Numeric(12, 2), nullable=False, server_default="0"), sa.Column("pdf_path", sa.String(255), nullable=True), sa.Column("emailed_at", sa.DateTime(timezone=True), nullable=True), sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()))
        op.create_index("ix_invoices_booking_id", "invoices", ["booking_id"])

    if not _has_table(inspector, "invoice_items"):
        op.create_table("invoice_items", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("invoice_id", sa.Integer(), sa.ForeignKey("invoices.id"), nullable=False), sa.Column("item_type", sa.String(40), nullable=False, server_default="booking"), sa.Column("description", sa.String(255), nullable=False), sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"), sa.Column("unit_price", sa.Numeric(12, 2), nullable=False, server_default="0"), sa.Column("tax_amount", sa.Numeric(12, 2), nullable=False, server_default="0"), sa.Column("total_price", sa.Numeric(12, 2), nullable=False, server_default="0"), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()))
        op.create_index("ix_invoice_items_invoice_id", "invoice_items", ["invoice_id"])

    if not _has_table(inspector, "notifications"):
        op.create_table("notifications", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True), sa.Column("notification_type", sa.String(60), nullable=False), sa.Column("title", sa.String(180), nullable=False), sa.Column("message", sa.Text(), nullable=False), sa.Column("channel", sa.String(30), nullable=False, server_default="in_app"), sa.Column("status", sa.String(30), nullable=False, server_default="pending"), sa.Column("is_read", sa.Integer(), nullable=False, server_default="0"), sa.Column("entity_type", sa.String(60), nullable=True), sa.Column("entity_id", sa.Integer(), nullable=True), sa.Column("notification_id", sa.String(100), nullable=True), sa.Column("metadata_json", sa.JSON(), nullable=True), sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True), sa.Column("read_at", sa.DateTime(timezone=True), nullable=True), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()))
        op.create_index("ix_notifications_user_id", "notifications", ["user_id"])

    if not _has_table(inspector, "user_sessions"):
        op.create_table("user_sessions", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False), sa.Column("session_id", sa.String(120), nullable=False, unique=True), sa.Column("ip_address", sa.String(100), nullable=True), sa.Column("user_agent", sa.String(255), nullable=True), sa.Column("status", sa.String(30), nullable=False, server_default="active"), sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True), sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now()), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()))
        op.create_index("ix_user_sessions_user_id", "user_sessions", ["user_id"])


def downgrade():
    for table in ["user_sessions", "notifications", "invoice_items", "invoices", "payment_holds", "payment_transactions", "booking_communications", "booking_status_history", "booking_extensions", "booking_accommodations", "booking_optional_activities", "booking_travellers"]:
        try:
            op.drop_table(table)
        except Exception:
            pass
