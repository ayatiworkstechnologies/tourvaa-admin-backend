"""Week 9+10 tour detail tables

Revision ID: 20260618_0011
Revises: 20260617_0010
Create Date: 2026-06-18
"""
from alembic import op
import sqlalchemy as sa

revision = "20260618_0011"
down_revision = "20260617_0010"
branch_labels = None
depends_on = None


def _has_table(inspector, name: str) -> bool:
    return name in inspector.get_table_names()


def upgrade():
    inspector = sa.inspect(op.get_bind())

    if not _has_table(inspector, "tour_overviews"):
        op.create_table(
            "tour_overviews",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("tour_id", sa.Integer, sa.ForeignKey("tours.id"), nullable=False, unique=True, index=True),
            sa.Column("duration_text", sa.String(100), nullable=False, server_default=""),
            sa.Column("start_location", sa.String(150), nullable=False, server_default=""),
            sa.Column("end_location", sa.String(150), nullable=False, server_default=""),
            sa.Column("group_size", sa.String(100), nullable=False, server_default=""),
            sa.Column("tour_type", sa.String(100), nullable=False, server_default=""),
            sa.Column("physical_rating", sa.String(20), nullable=False, server_default="easy"),
            sa.Column("overview_icon_data", sa.JSON, nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        )

    if not _has_table(inspector, "tour_itineraries"):
        op.create_table(
            "tour_itineraries",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("tour_id", sa.Integer, sa.ForeignKey("tours.id"), nullable=False, index=True),
            sa.Column("day_number", sa.Integer, nullable=False),
            sa.Column("day_title", sa.String(255), nullable=False, server_default=""),
            sa.Column("location_name", sa.String(255), nullable=False, server_default=""),
            sa.Column("short_description", sa.Text, nullable=True),
            sa.Column("long_description", sa.Text, nullable=True),
            sa.Column("activities", sa.Text, nullable=True),
            sa.Column("image", sa.String(255), nullable=False, server_default=""),
            sa.Column("image_alt_text", sa.String(180), nullable=False, server_default=""),
            sa.Column("display_order", sa.Integer, nullable=False, server_default="0"),
            sa.Column("status", sa.String(20), nullable=False, server_default="active"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        )

    if not _has_table(inspector, "tour_inclusions"):
        op.create_table(
            "tour_inclusions",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("tour_id", sa.Integer, sa.ForeignKey("tours.id"), nullable=False, index=True),
            sa.Column("icon", sa.String(255), nullable=False, server_default=""),
            sa.Column("title", sa.String(255), nullable=False),
            sa.Column("description", sa.Text, nullable=True),
            sa.Column("display_order", sa.Integer, nullable=False, server_default="0"),
            sa.Column("status", sa.String(20), nullable=False, server_default="active"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        )

    if not _has_table(inspector, "tour_exclusions"):
        op.create_table(
            "tour_exclusions",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("tour_id", sa.Integer, sa.ForeignKey("tours.id"), nullable=False, index=True),
            sa.Column("icon", sa.String(255), nullable=False, server_default=""),
            sa.Column("title", sa.String(255), nullable=False),
            sa.Column("description", sa.Text, nullable=True),
            sa.Column("display_order", sa.Integer, nullable=False, server_default="0"),
            sa.Column("status", sa.String(20), nullable=False, server_default="active"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        )

    if not _has_table(inspector, "tour_highlights"):
        op.create_table(
            "tour_highlights",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("tour_id", sa.Integer, sa.ForeignKey("tours.id"), nullable=False, index=True),
            sa.Column("image", sa.String(255), nullable=False, server_default=""),
            sa.Column("title", sa.String(255), nullable=False),
            sa.Column("short_description", sa.Text, nullable=True),
            sa.Column("display_order", sa.Integer, nullable=False, server_default="0"),
            sa.Column("status", sa.String(20), nullable=False, server_default="active"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        )

    if not _has_table(inspector, "tour_similar_tours"):
        op.create_table(
            "tour_similar_tours",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("tour_id", sa.Integer, sa.ForeignKey("tours.id"), nullable=False, index=True),
            sa.Column("similar_tour_id", sa.Integer, sa.ForeignKey("tours.id"), nullable=False, index=True),
            sa.Column("display_order", sa.Integer, nullable=False, server_default="0"),
            sa.Column("status", sa.String(20), nullable=False, server_default="active"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.UniqueConstraint("tour_id", "similar_tour_id", name="uq_tour_similar"),
        )

    if not _has_table(inspector, "tour_extensions"):
        op.create_table(
            "tour_extensions",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("tour_id", sa.Integer, sa.ForeignKey("tours.id"), nullable=False, index=True),
            sa.Column("extension_tour_id", sa.Integer, sa.ForeignKey("tours.id"), nullable=False, index=True),
            sa.Column("extension_title", sa.String(255), nullable=False, server_default=""),
            sa.Column("extension_note", sa.Text, nullable=True),
            sa.Column("extra_price", sa.Float, nullable=False, server_default="0"),
            sa.Column("display_order", sa.Integer, nullable=False, server_default="0"),
            sa.Column("status", sa.String(20), nullable=False, server_default="active"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        )

    if not _has_table(inspector, "tour_gallery_images"):
        op.create_table(
            "tour_gallery_images",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("tour_id", sa.Integer, sa.ForeignKey("tours.id"), nullable=False, index=True),
            sa.Column("image_path", sa.String(255), nullable=False),
            sa.Column("image_title", sa.String(255), nullable=False, server_default=""),
            sa.Column("image_alt_text", sa.String(180), nullable=False, server_default=""),
            sa.Column("image_caption", sa.Text, nullable=True),
            sa.Column("image_type", sa.String(30), nullable=False, server_default="gallery"),
            sa.Column("display_order", sa.Integer, nullable=False, server_default="0"),
            sa.Column("status", sa.String(20), nullable=False, server_default="active"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        )

    # Week 10 tables
    if not _has_table(inspector, "tour_pricing"):
        op.create_table(
            "tour_pricing",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("tour_id", sa.Integer, sa.ForeignKey("tours.id"), nullable=False, index=True),
            sa.Column("passenger_from", sa.Integer, nullable=False),
            sa.Column("passenger_to", sa.Integer, nullable=False),
            sa.Column("adult_price", sa.Float, nullable=False),
            sa.Column("child_price", sa.Float, nullable=False, server_default="0"),
            sa.Column("supplier_price", sa.Float, nullable=False, server_default="0"),
            sa.Column("markup_type", sa.String(20), nullable=False, server_default="percentage"),
            sa.Column("markup_value", sa.Float, nullable=False, server_default="0"),
            sa.Column("final_price", sa.Float, nullable=False),
            sa.Column("currency", sa.String(10), nullable=False, server_default="USD"),
            sa.Column("status", sa.String(20), nullable=False, server_default="active"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        )

    if not _has_table(inspector, "tour_optional_activities"):
        op.create_table(
            "tour_optional_activities",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("tour_id", sa.Integer, sa.ForeignKey("tours.id"), nullable=False, index=True),
            sa.Column("activity_name", sa.String(255), nullable=False),
            sa.Column("description", sa.Text, nullable=True),
            sa.Column("price_per_person", sa.Float, nullable=False, server_default="0"),
            sa.Column("image", sa.String(255), nullable=False, server_default=""),
            sa.Column("status", sa.String(20), nullable=False, server_default="active"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        )

    if not _has_table(inspector, "tour_accommodation_extras"):
        op.create_table(
            "tour_accommodation_extras",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("tour_id", sa.Integer, sa.ForeignKey("tours.id"), nullable=False, index=True),
            sa.Column("accommodation_name", sa.String(255), nullable=False),
            sa.Column("description", sa.Text, nullable=True),
            sa.Column("extra_price", sa.Float, nullable=False, server_default="0"),
            sa.Column("price_type", sa.String(20), nullable=False, server_default="per_person"),
            sa.Column("is_default", sa.Integer, nullable=False, server_default="0"),
            sa.Column("status", sa.String(20), nullable=False, server_default="active"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        )

    if not _has_table(inspector, "tour_calendar"):
        op.create_table(
            "tour_calendar",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("tour_id", sa.Integer, sa.ForeignKey("tours.id"), nullable=False, index=True),
            sa.Column("tour_date", sa.DateTime(timezone=True), nullable=False, index=True),
            sa.Column("start_date", sa.DateTime(timezone=True), nullable=True),
            sa.Column("end_date", sa.DateTime(timezone=True), nullable=True),
            sa.Column("available_seats", sa.Integer, nullable=False, server_default="0"),
            sa.Column("booked_seats", sa.Integer, nullable=False, server_default="0"),
            sa.Column("status", sa.String(20), nullable=False, server_default="available"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        )

    if not _has_table(inspector, "tour_unavailable_dates"):
        op.create_table(
            "tour_unavailable_dates",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("tour_id", sa.Integer, sa.ForeignKey("tours.id"), nullable=False, index=True),
            sa.Column("unavailable_date", sa.DateTime(timezone=True), nullable=False, index=True),
            sa.Column("reason", sa.Text, nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        )

    if not _has_table(inspector, "tour_discounts"):
        op.create_table(
            "tour_discounts",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("tour_id", sa.Integer, sa.ForeignKey("tours.id"), nullable=True, index=True),
            sa.Column("category_id", sa.Integer, sa.ForeignKey("tour_categories.id"), nullable=True, index=True),
            sa.Column("country_id", sa.Integer, sa.ForeignKey("countries.id"), nullable=True, index=True),
            sa.Column("discount_name", sa.String(255), nullable=False),
            sa.Column("discount_code", sa.String(50), nullable=True, unique=True, index=True),
            sa.Column("discount_type", sa.String(20), nullable=False),
            sa.Column("discount_value", sa.Float, nullable=False),
            sa.Column("discount_scope", sa.String(20), nullable=False, server_default="tour"),
            sa.Column("start_date", sa.DateTime(timezone=True), nullable=True),
            sa.Column("end_date", sa.DateTime(timezone=True), nullable=True),
            sa.Column("usage_limit", sa.Integer, nullable=True),
            sa.Column("used_count", sa.Integer, nullable=False, server_default="0"),
            sa.Column("minimum_booking_amount", sa.Float, nullable=False, server_default="0"),
            sa.Column("status", sa.String(20), nullable=False, server_default="active"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        )


def downgrade():
    for table in [
        "tour_discounts", "tour_unavailable_dates", "tour_calendar",
        "tour_accommodation_extras", "tour_optional_activities", "tour_pricing",
        "tour_gallery_images", "tour_extensions", "tour_similar_tours",
        "tour_highlights", "tour_exclusions", "tour_inclusions",
        "tour_itineraries", "tour_overviews",
    ]:
        try:
            op.drop_table(table)
        except Exception:
            pass
