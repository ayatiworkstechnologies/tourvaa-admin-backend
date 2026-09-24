"""External affiliate inventory (Viator "Day Tours & Experiences").

New tables only - nothing existing is altered except one additive column:
- external_providers: non-secret provider settings/status (credentials stay
  encrypted in api_settings / .env)
- external_destination_mappings: synced provider destinations + optional
  link to Tourvaa country/state/city
- external_affiliate_clicks: outbound affiliate click analytics (not bookings)
- tour_itineraries.day_type: "standard" (default for every existing row) or
  "free_day", an explicit admin flag for free/leisure days

Revision ID: 20260923_0003
Revises: 20260923_0002
Create Date: 2026-09-23
"""
from alembic import op
import sqlalchemy as sa

revision = "20260923_0003"
down_revision = "20260923_0002"
branch_labels = None
depends_on = None


def _tables(bind) -> set[str]:
    return set(sa.inspect(bind).get_table_names())


def upgrade():
    bind = op.get_bind()
    tables = _tables(bind)

    if "external_providers" not in tables:
        op.create_table(
            "external_providers",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("code", sa.String(40), nullable=False),
            sa.Column("name", sa.String(100), nullable=False),
            sa.Column("public_category", sa.String(120), nullable=False, server_default="Day Tours & Experiences"),
            sa.Column("show_on_homepage", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("show_on_destination_pages", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("show_on_itinerary", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("show_in_search", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("last_connection_status", sa.String(20), nullable=True),
            sa.Column("last_connection_message", sa.String(255), nullable=True),
            sa.Column("last_connection_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_destination_sync_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_destination_sync_status", sa.String(20), nullable=True),
            sa.Column("last_destination_sync_count", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index("ix_external_providers_code", "external_providers", ["code"], unique=True)

    if "external_destination_mappings" not in tables:
        op.create_table(
            "external_destination_mappings",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("provider", sa.String(40), nullable=False),
            sa.Column("provider_destination_id", sa.String(40), nullable=False),
            sa.Column("provider_destination_name", sa.String(255), nullable=False),
            sa.Column("provider_destination_type", sa.String(40), nullable=True),
            sa.Column("provider_parent_destination_id", sa.String(40), nullable=True),
            sa.Column("provider_default_currency", sa.String(3), nullable=True),
            sa.Column("slug", sa.String(191), nullable=False),
            sa.Column("tourvaa_country_id", sa.Integer(), sa.ForeignKey("countries.id", ondelete="SET NULL"), nullable=True),
            sa.Column("tourvaa_state_id", sa.Integer(), sa.ForeignKey("states.id", ondelete="SET NULL"), nullable=True),
            sa.Column("tourvaa_city_id", sa.Integer(), sa.ForeignKey("cities.id", ondelete="SET NULL"), nullable=True),
            sa.Column("mapping_source", sa.String(10), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.UniqueConstraint("provider", "provider_destination_id", name="uq_ext_dest_provider_id"),
            sa.UniqueConstraint("provider", "slug", name="uq_ext_dest_provider_slug"),
        )
        for col in ("provider", "provider_parent_destination_id", "tourvaa_country_id", "tourvaa_state_id", "tourvaa_city_id"):
            op.create_index(f"ix_external_destination_mappings_{col}", "external_destination_mappings", [col])

    if "external_affiliate_clicks" not in tables:
        op.create_table(
            "external_affiliate_clicks",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("provider", sa.String(40), nullable=False),
            sa.Column("product_code", sa.String(80), nullable=False),
            sa.Column("product_title", sa.String(255), nullable=True),
            sa.Column("provider_destination_id", sa.String(40), nullable=True),
            sa.Column("tourvaa_country_id", sa.Integer(), sa.ForeignKey("countries.id", ondelete="SET NULL"), nullable=True),
            sa.Column("tourvaa_city_id", sa.Integer(), sa.ForeignKey("cities.id", ondelete="SET NULL"), nullable=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("agent_id", sa.Integer(), sa.ForeignKey("agents.id", ondelete="SET NULL"), nullable=True),
            sa.Column("session_id", sa.String(64), nullable=True),
            sa.Column("campaign", sa.String(80), nullable=True),
            sa.Column("source_page", sa.String(40), nullable=True),
            sa.Column("page_path", sa.String(255), nullable=True),
            sa.Column("external_url", sa.Text(), nullable=True),
            sa.Column("external_url_hash", sa.String(64), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        for col in ("provider", "product_code", "provider_destination_id", "user_id", "agent_id", "session_id", "campaign", "source_page", "created_at"):
            op.create_index(f"ix_external_affiliate_clicks_{col}", "external_affiliate_clicks", [col])

    cols = {c["name"] for c in sa.inspect(bind).get_columns("tour_itineraries")}
    if "day_type" not in cols:
        op.add_column(
            "tour_itineraries",
            sa.Column("day_type", sa.String(20), nullable=False, server_default="standard"),
        )


def downgrade():
    bind = op.get_bind()
    cols = {c["name"] for c in sa.inspect(bind).get_columns("tour_itineraries")}
    if "day_type" in cols:
        op.drop_column("tour_itineraries", "day_type")
    tables = _tables(bind)
    for table in ("external_affiliate_clicks", "external_destination_mappings", "external_providers"):
        if table in tables:
            op.drop_table(table)
