"""week 6 8 operations cms

Revision ID: 20260616_0008
Revises: 20260615_0007
Create Date: 2026-06-16
"""
from alembic import op
import sqlalchemy as sa

revision = "20260616_0008"
down_revision = "20260615_0007"
branch_labels = None
depends_on = None


def _has_table(inspector, table_name):
    return table_name in inspector.get_table_names()


def _timestamps():
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
    ]


def _review_columns(name_prefix):
    return [
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column(f"{name_prefix}_code", sa.String(length=30), nullable=True),
        sa.Column(f"{name_prefix}_name", sa.String(length=150), nullable=False),
        sa.Column(f"{name_prefix}_type", sa.String(length=75), nullable=False, server_default=""),
        sa.Column("country_id", sa.Integer(), nullable=True),
        sa.Column("city_id", sa.Integer(), nullable=True),
        sa.Column("years_in_operation", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="inactive"),
        sa.Column("approval_status", sa.String(length=30), nullable=False, server_default="pending"),
        sa.Column("rejection_reason", sa.String(length=255), nullable=True),
        sa.Column("admin_comments", sa.Text(), nullable=True),
        sa.Column("pending_requirements", sa.Text(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by", sa.Integer(), nullable=True),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejected_by", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["country_id"], ["countries.id"]),
        sa.ForeignKeyConstraint(["city_id"], ["cities.id"]),
        sa.ForeignKeyConstraint(["approved_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["rejected_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(f"{name_prefix}_code"),
    ]


def _contact_table(table_name, fk_name, parent_table):
    op.create_table(
        table_name,
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(fk_name, sa.Integer(), nullable=False),
        sa.Column("contact_name", sa.String(length=150), nullable=False),
        sa.Column("designation", sa.String(length=100), nullable=False, server_default=""),
        sa.Column("phone", sa.String(length=30), nullable=False, server_default=""),
        sa.Column("email", sa.String(length=150), nullable=False, server_default=""),
        sa.Column("alternate_phone", sa.String(length=30), nullable=False, server_default=""),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
        *_timestamps(),
        sa.ForeignKeyConstraint([fk_name], [f"{parent_table}.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f(f"ix_{table_name}_id"), table_name, ["id"], unique=False)
    op.create_index(op.f(f"ix_{table_name}_{fk_name}"), table_name, [fk_name], unique=False)


def _document_table(table_name, fk_name, parent_table, rejection=True):
    columns = [
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(fk_name, sa.Integer(), nullable=False),
        sa.Column("document_type", sa.String(length=100), nullable=False),
        sa.Column("document_name", sa.String(length=150), nullable=False),
        sa.Column("file_path", sa.String(length=255), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("mime_type", sa.String(length=100), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
    ]
    if rejection:
        columns.append(sa.Column("rejection_reason", sa.String(length=255), nullable=True))
    columns.extend(
        [
            sa.Column("uploaded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
            sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("reviewed_by", sa.Integer(), nullable=True),
            sa.ForeignKeyConstraint([fk_name], [f"{parent_table}.id"]),
            sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        ]
    )
    op.create_table(table_name, *columns)
    op.create_index(op.f(f"ix_{table_name}_id"), table_name, ["id"], unique=False)
    op.create_index(op.f(f"ix_{table_name}_{fk_name}"), table_name, [fk_name], unique=False)


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _has_table(inspector, "countries"):
        op.create_table(
            "countries",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("country_name", sa.String(length=120), nullable=False),
            sa.Column("country_code", sa.String(length=10), nullable=False),
            sa.Column("phone_code", sa.String(length=10), nullable=False, server_default=""),
            sa.Column("currency_code", sa.String(length=10), nullable=False, server_default=""),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
            *_timestamps(),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("country_name"),
            sa.UniqueConstraint("country_code"),
        )
        op.create_index(op.f("ix_countries_id"), "countries", ["id"], unique=False)

    if not _has_table(inspector, "cities"):
        op.create_table(
            "cities",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("country_id", sa.Integer(), nullable=False),
            sa.Column("city_name", sa.String(length=120), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
            *_timestamps(),
            sa.ForeignKeyConstraint(["country_id"], ["countries.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_cities_id"), "cities", ["id"], unique=False)
        op.create_index(op.f("ix_cities_country_id"), "cities", ["country_id"], unique=False)

    if not _has_table(inspector, "suppliers"):
        op.create_table(
            "suppliers",
            *_review_columns("supplier"),
            sa.Column("markup_type", sa.String(length=20), nullable=True),
            sa.Column("markup_value", sa.Float(), nullable=False, server_default="0"),
            *_timestamps(),
        )
        for column in ["id", "user_id", "supplier_code", "country_id", "city_id", "approval_status"]:
            op.create_index(op.f(f"ix_suppliers_{column}"), "suppliers", [column], unique=False)
        _contact_table("supplier_contacts", "supplier_id", "suppliers")
        op.create_table(
            "supplier_business_info",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("supplier_id", sa.Integer(), nullable=False),
            sa.Column("years_in_business", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("certificate_of_incorporation", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("monthly_customers_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("target_market", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("destinations_sold", sa.Text(), nullable=True),
            sa.Column("gst_tax_number", sa.String(length=100), nullable=False, server_default=""),
            sa.Column("business_registration_number", sa.String(length=100), nullable=False, server_default=""),
            sa.Column("approval_status", sa.String(length=30), nullable=False, server_default="pending"),
            *_timestamps(),
            sa.ForeignKeyConstraint(["supplier_id"], ["suppliers.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("supplier_id"),
        )
        op.create_index(op.f("ix_supplier_business_info_id"), "supplier_business_info", ["id"], unique=False)
        op.create_index(op.f("ix_supplier_business_info_supplier_id"), "supplier_business_info", ["supplier_id"], unique=False)
        op.create_table(
            "supplier_vehicles",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("supplier_id", sa.Integer(), nullable=False),
            sa.Column("make", sa.String(length=100), nullable=False, server_default=""),
            sa.Column("model", sa.String(length=100), nullable=False, server_default=""),
            sa.Column("year", sa.Integer(), nullable=True),
            sa.Column("capacity", sa.Integer(), nullable=True),
            sa.Column("fitness_certificate", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("insurance_document", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("vehicle_photos", sa.Text(), nullable=True),
            sa.Column("approval_status", sa.String(length=30), nullable=False, server_default="pending"),
            *_timestamps(),
            sa.ForeignKeyConstraint(["supplier_id"], ["suppliers.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_supplier_vehicles_id"), "supplier_vehicles", ["id"], unique=False)
        op.create_index(op.f("ix_supplier_vehicles_supplier_id"), "supplier_vehicles", ["supplier_id"], unique=False)
        _invoicing("supplier_invoicing", "supplier_id", "suppliers", full=True)
        _document_table("supplier_documents", "supplier_id", "suppliers")

    if _has_table(inspector, "suppliers"):
        if not _has_table(inspector, "supplier_contacts"):
            _contact_table("supplier_contacts", "supplier_id", "suppliers")
        if not _has_table(inspector, "supplier_business_info"):
            op.create_table(
                "supplier_business_info",
                sa.Column("id", sa.Integer(), nullable=False),
                sa.Column("supplier_id", sa.Integer(), nullable=False),
                sa.Column("years_in_business", sa.Integer(), nullable=False, server_default="0"),
                sa.Column("certificate_of_incorporation", sa.String(length=255), nullable=False, server_default=""),
                sa.Column("monthly_customers_count", sa.Integer(), nullable=False, server_default="0"),
                sa.Column("target_market", sa.String(length=255), nullable=False, server_default=""),
                sa.Column("destinations_sold", sa.Text(), nullable=True),
                sa.Column("gst_tax_number", sa.String(length=100), nullable=False, server_default=""),
                sa.Column("business_registration_number", sa.String(length=100), nullable=False, server_default=""),
                sa.Column("approval_status", sa.String(length=30), nullable=False, server_default="pending"),
                *_timestamps(),
                sa.ForeignKeyConstraint(["supplier_id"], ["suppliers.id"]),
                sa.PrimaryKeyConstraint("id"),
                sa.UniqueConstraint("supplier_id"),
            )
            op.create_index(op.f("ix_supplier_business_info_id"), "supplier_business_info", ["id"], unique=False)
            op.create_index(op.f("ix_supplier_business_info_supplier_id"), "supplier_business_info", ["supplier_id"], unique=False)
        if not _has_table(inspector, "supplier_vehicles"):
            op.create_table(
                "supplier_vehicles",
                sa.Column("id", sa.Integer(), nullable=False),
                sa.Column("supplier_id", sa.Integer(), nullable=False),
                sa.Column("make", sa.String(length=100), nullable=False, server_default=""),
                sa.Column("model", sa.String(length=100), nullable=False, server_default=""),
                sa.Column("year", sa.Integer(), nullable=True),
                sa.Column("capacity", sa.Integer(), nullable=True),
                sa.Column("fitness_certificate", sa.String(length=255), nullable=False, server_default=""),
                sa.Column("insurance_document", sa.String(length=255), nullable=False, server_default=""),
                sa.Column("vehicle_photos", sa.Text(), nullable=True),
                sa.Column("approval_status", sa.String(length=30), nullable=False, server_default="pending"),
                *_timestamps(),
                sa.ForeignKeyConstraint(["supplier_id"], ["suppliers.id"]),
                sa.PrimaryKeyConstraint("id"),
            )
            op.create_index(op.f("ix_supplier_vehicles_id"), "supplier_vehicles", ["id"], unique=False)
            op.create_index(op.f("ix_supplier_vehicles_supplier_id"), "supplier_vehicles", ["supplier_id"], unique=False)
        if not _has_table(inspector, "supplier_invoicing"):
            _invoicing("supplier_invoicing", "supplier_id", "suppliers", full=True)
        if not _has_table(inspector, "supplier_documents"):
            _document_table("supplier_documents", "supplier_id", "suppliers")

    if not _has_table(inspector, "agents"):
        op.create_table(
            "agents",
            *_review_columns("agent"),
            sa.Column("discount_type", sa.String(length=20), nullable=True),
            sa.Column("discount_value", sa.Float(), nullable=False, server_default="0"),
            *_timestamps(),
        )
        for column in ["id", "user_id", "agent_code", "country_id", "city_id", "approval_status"]:
            op.create_index(op.f(f"ix_agents_{column}"), "agents", [column], unique=False)
        _contact_table("agent_contacts", "agent_id", "agents")
        op.create_table(
            "agent_business_info",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("agent_id", sa.Integer(), nullable=False),
            sa.Column("years_in_business", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("certificate_of_incorporation", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("monthly_customers_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("target_market", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("destinations_sold", sa.Text(), nullable=True),
            sa.Column("iata_registration_number", sa.String(length=100), nullable=False, server_default=""),
            sa.Column("gst_tax_number", sa.String(length=100), nullable=False, server_default=""),
            sa.Column("approval_status", sa.String(length=30), nullable=False, server_default="pending"),
            *_timestamps(),
            sa.ForeignKeyConstraint(["agent_id"], ["agents.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("agent_id"),
        )
        op.create_index(op.f("ix_agent_business_info_id"), "agent_business_info", ["id"], unique=False)
        op.create_index(op.f("ix_agent_business_info_agent_id"), "agent_business_info", ["agent_id"], unique=False)
        _invoicing("agent_invoicing", "agent_id", "agents", full=True)
        _document_table("agent_documents", "agent_id", "agents")

    if not _has_table(inspector, "affiliates"):
        op.create_table(
            "affiliates",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("affiliate_code", sa.String(length=30), nullable=True),
            sa.Column("business_type", sa.String(length=75), nullable=False, server_default=""),
            sa.Column("name", sa.String(length=150), nullable=False),
            sa.Column("email", sa.String(length=150), nullable=False),
            sa.Column("phone", sa.String(length=30), nullable=False, server_default=""),
            sa.Column("website_url", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("country_id", sa.Integer(), nullable=True),
            sa.Column("city_id", sa.Integer(), nullable=True),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="inactive"),
            sa.Column("approval_status", sa.String(length=30), nullable=False, server_default="pending"),
            sa.Column("rejection_reason", sa.String(length=255), nullable=True),
            sa.Column("admin_comments", sa.Text(), nullable=True),
            sa.Column("api_link", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("approved_by", sa.Integer(), nullable=True),
            sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("rejected_by", sa.Integer(), nullable=True),
            *_timestamps(),
            sa.ForeignKeyConstraint(["country_id"], ["countries.id"]),
            sa.ForeignKeyConstraint(["city_id"], ["cities.id"]),
            sa.ForeignKeyConstraint(["approved_by"], ["users.id"]),
            sa.ForeignKeyConstraint(["rejected_by"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("affiliate_code"),
        )
        for column in ["id", "affiliate_code", "email", "country_id", "city_id", "approval_status"]:
            op.create_index(op.f(f"ix_affiliates_{column}"), "affiliates", [column], unique=False)
        op.create_table(
            "affiliate_marketing_info",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("affiliate_id", sa.Integer(), nullable=False),
            sa.Column("promotion_methods", sa.Text(), nullable=True),
            sa.Column("estimated_monthly_bookings", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("existing_audience_size", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("social_media_profiles", sa.Text(), nullable=True),
            sa.Column("existing_travel_platforms_used", sa.Text(), nullable=True),
            *_timestamps(),
            sa.ForeignKeyConstraint(["affiliate_id"], ["affiliates.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("affiliate_id"),
        )
        op.create_index(op.f("ix_affiliate_marketing_info_id"), "affiliate_marketing_info", ["id"], unique=False)
        op.create_index(op.f("ix_affiliate_marketing_info_affiliate_id"), "affiliate_marketing_info", ["affiliate_id"], unique=False)
        _invoicing("affiliate_invoicing", "affiliate_id", "affiliates", full=False)
        _document_table("affiliate_documents", "affiliate_id", "affiliates", rejection=False)

    if not _has_table(inspector, "tour_categories"):
        op.create_table(
            "tour_categories",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("category_name", sa.String(length=120), nullable=False),
            sa.Column("slug", sa.String(length=150), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("image", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
            *_timestamps(),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("slug"),
        )
        op.create_index(op.f("ix_tour_categories_id"), "tour_categories", ["id"], unique=False)
        op.create_index(op.f("ix_tour_categories_slug"), "tour_categories", ["slug"], unique=False)

    if not _has_table(inspector, "tour_subcategories"):
        op.create_table(
            "tour_subcategories",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("category_id", sa.Integer(), nullable=False),
            sa.Column("subcategory_name", sa.String(length=120), nullable=False),
            sa.Column("slug", sa.String(length=150), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("image", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
            *_timestamps(),
            sa.ForeignKeyConstraint(["category_id"], ["tour_categories.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("slug"),
        )
        op.create_index(op.f("ix_tour_subcategories_id"), "tour_subcategories", ["id"], unique=False)
        op.create_index(op.f("ix_tour_subcategories_category_id"), "tour_subcategories", ["category_id"], unique=False)
        op.create_index(op.f("ix_tour_subcategories_slug"), "tour_subcategories", ["slug"], unique=False)

    if not _has_table(inspector, "tours"):
        op.create_table(
            "tours",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("tour_code", sa.String(length=30), nullable=True),
            sa.Column("supplier_id", sa.Integer(), nullable=True),
            sa.Column("title", sa.String(length=180), nullable=False),
            sa.Column("slug", sa.String(length=200), nullable=False),
            sa.Column("subtitle", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("price_start_per_person", sa.Float(), nullable=False, server_default="0"),
            sa.Column("currency", sa.String(length=10), nullable=False, server_default="USD"),
            sa.Column("country_id", sa.Integer(), nullable=True),
            sa.Column("city_id", sa.Integer(), nullable=True),
            sa.Column("category_id", sa.Integer(), nullable=True),
            sa.Column("start_location", sa.String(length=150), nullable=False, server_default=""),
            sa.Column("finish_location", sa.String(length=150), nullable=False, server_default=""),
            sa.Column("number_of_days", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("number_of_hours", sa.Integer(), nullable=True),
            sa.Column("short_description", sa.Text(), nullable=True),
            sa.Column("long_description", sa.Text(), nullable=True),
            sa.Column("seo_title", sa.String(length=180), nullable=False, server_default=""),
            sa.Column("seo_description", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("seo_keywords", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("image_alt_text", sa.String(length=180), nullable=False, server_default=""),
            sa.Column("banner_image", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("map_image", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="draft"),
            sa.Column("created_by", sa.Integer(), nullable=True),
            sa.Column("updated_by", sa.Integer(), nullable=True),
            *_timestamps(),
            sa.ForeignKeyConstraint(["supplier_id"], ["suppliers.id"]),
            sa.ForeignKeyConstraint(["country_id"], ["countries.id"]),
            sa.ForeignKeyConstraint(["city_id"], ["cities.id"]),
            sa.ForeignKeyConstraint(["category_id"], ["tour_categories.id"]),
            sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
            sa.ForeignKeyConstraint(["updated_by"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("tour_code"),
            sa.UniqueConstraint("slug"),
        )
        for column in ["id", "tour_code", "supplier_id", "slug", "country_id", "city_id", "category_id", "status"]:
            op.create_index(op.f(f"ix_tours_{column}"), "tours", [column], unique=False)

    if not _has_table(inspector, "tour_subcategory_map"):
        op.create_table(
            "tour_subcategory_map",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("tour_id", sa.Integer(), nullable=False),
            sa.Column("subcategory_id", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
            sa.ForeignKeyConstraint(["tour_id"], ["tours.id"]),
            sa.ForeignKeyConstraint(["subcategory_id"], ["tour_subcategories.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_tour_subcategory_map_id"), "tour_subcategory_map", ["id"], unique=False)
        op.create_index(op.f("ix_tour_subcategory_map_tour_id"), "tour_subcategory_map", ["tour_id"], unique=False)
        op.create_index(op.f("ix_tour_subcategory_map_subcategory_id"), "tour_subcategory_map", ["subcategory_id"], unique=False)


def _invoicing(table_name, fk_name, parent_table, full=True):
    columns = [
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(fk_name, sa.Integer(), nullable=False),
        sa.Column("contact_name", sa.String(length=150), nullable=False, server_default=""),
        sa.Column("email", sa.String(length=150), nullable=False, server_default=""),
        sa.Column("phone", sa.String(length=30), nullable=False, server_default=""),
        sa.Column("account_name", sa.String(length=150), nullable=False, server_default=""),
        sa.Column("account_number", sa.String(length=100), nullable=False, server_default=""),
        sa.Column("bank_name", sa.String(length=150), nullable=False, server_default=""),
    ]
    if full:
        columns.extend(
            [
                sa.Column("bank_branch", sa.String(length=150), nullable=False, server_default=""),
                sa.Column("swift_code", sa.String(length=50), nullable=False, server_default=""),
                sa.Column("iban", sa.String(length=100), nullable=False, server_default=""),
            ]
        )
    columns.extend(
        [
            sa.Column("country_id", sa.Integer(), nullable=True),
            sa.Column("tax_number", sa.String(length=100), nullable=False, server_default=""),
            *_timestamps(),
            sa.ForeignKeyConstraint([fk_name], [f"{parent_table}.id"]),
            sa.ForeignKeyConstraint(["country_id"], ["countries.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(fk_name),
        ]
    )
    op.create_table(table_name, *columns)
    op.create_index(op.f(f"ix_{table_name}_id"), table_name, ["id"], unique=False)
    op.create_index(op.f(f"ix_{table_name}_{fk_name}"), table_name, [fk_name], unique=False)


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for table_name in [
        "tour_subcategory_map",
        "tours",
        "tour_subcategories",
        "tour_categories",
        "affiliate_documents",
        "affiliate_invoicing",
        "affiliate_marketing_info",
        "affiliates",
        "agent_documents",
        "agent_invoicing",
        "agent_business_info",
        "agent_contacts",
        "agents",
        "supplier_documents",
        "supplier_invoicing",
        "supplier_vehicles",
        "supplier_business_info",
        "supplier_contacts",
        "suppliers",
        "cities",
        "countries",
    ]:
        if _has_table(inspector, table_name):
            op.drop_table(table_name)
