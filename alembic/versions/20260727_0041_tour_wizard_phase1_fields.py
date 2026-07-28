"""extend tours/tour_overviews/tour_itineraries for the 10-step tour wizard

Phase 1 of the tour builder redesign consolidates the create form and the
12-tab editor into a single 10-step wizard. Most of the new step content
already had a backing table; this migration adds the remaining columns
that are additive-only (no new tables, no data movement) so existing rows
keep working unchanged. See plans/immutable-wondering-ocean.md for the
full phase breakdown - agent pricing, structured accommodation, multi-
destination locations, and the policy-text fields are deferred to Phase 2
because they need brand-new tables.

Revision ID: 20260727_0041
Revises: 20260724_0040
"""

import sqlalchemy as sa
from alembic import op

revision = "20260727_0041"
down_revision = "20260724_0040"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return column in {c["name"] for c in inspector.get_columns(table)}


TOURS_COLUMNS = [
    ("state_id", sa.Integer(), {"nullable": True}),
    ("number_of_nights", sa.Integer(), {"nullable": True}),
    ("max_group_size", sa.Integer(), {"nullable": True}),
    ("min_booking_size", sa.Integer(), {"nullable": True}),
    ("tour_language", sa.String(length=100), {"nullable": True}),
    ("suitable_age_range", sa.String(length=100), {"nullable": True}),
    ("tour_visibility", sa.String(length=20), {"nullable": False, "server_default": "public"}),
    ("featured", sa.Boolean(), {"nullable": False, "server_default": sa.false()}),
    ("pricing_type", sa.String(length=20), {"nullable": False, "server_default": "per_person"}),
    ("offer_price", sa.Float(), {"nullable": False, "server_default": "0"}),
    ("infant_price", sa.Float(), {"nullable": False, "server_default": "0"}),
    ("single_supplement", sa.Float(), {"nullable": False, "server_default": "0"}),
    ("tax_percentage", sa.Float(), {"nullable": False, "server_default": "0"}),
    ("service_fee", sa.Float(), {"nullable": False, "server_default": "0"}),
    ("booking_deposit", sa.Float(), {"nullable": False, "server_default": "0"}),
    ("balance_payment_deadline_days", sa.Integer(), {"nullable": True}),
    ("mobile_cover_image", sa.String(length=255), {"nullable": True}),
    ("tour_video_url", sa.String(length=500), {"nullable": True}),
    ("brochure_pdf", sa.String(length=255), {"nullable": True}),
    ("focus_keyword", sa.String(length=180), {"nullable": True}),
    ("canonical_url", sa.String(length=500), {"nullable": True}),
    ("open_graph_image", sa.String(length=255), {"nullable": True}),
    ("search_visibility", sa.Boolean(), {"nullable": False, "server_default": sa.true()}),
]

TOUR_OVERVIEWS_COLUMNS = [
    ("why_choose_this_tour", sa.Text(), {"nullable": True}),
    ("ideal_for", sa.Text(), {"nullable": True}),
    ("best_season", sa.String(length=150), {"nullable": True}),
    ("tour_pace", sa.String(length=50), {"nullable": True}),
    ("transportation_summary", sa.Text(), {"nullable": True}),
    ("accommodation_summary", sa.Text(), {"nullable": True}),
    ("meal_summary", sa.Text(), {"nullable": True}),
]

TOUR_ITINERARIES_COLUMNS = [
    ("start_time", sa.String(length=20), {"nullable": True}),
    ("end_time", sa.String(length=20), {"nullable": True}),
    ("travel_distance", sa.String(length=100), {"nullable": True}),
    ("travel_duration", sa.String(length=100), {"nullable": True}),
    ("transport_type", sa.String(length=100), {"nullable": True}),
    ("meals_included", sa.String(length=150), {"nullable": True}),
    ("important_notes", sa.Text(), {"nullable": True}),
]


def _add_columns(table: str, columns: list[tuple[str, sa.types.TypeEngine, dict]]):
    for name, col_type, kwargs in columns:
        if not _has_column(table, name):
            op.add_column(table, sa.Column(name, col_type, **kwargs))


def upgrade():
    _add_columns("tours", TOURS_COLUMNS)

    # FK constraint for state_id, added separately so the column-add loop above stays uniform
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_fks = {fk["name"] for fk in inspector.get_foreign_keys("tours") if fk["name"]}
    if "fk_tours_state_id_states" not in existing_fks:
        op.create_foreign_key(
            "fk_tours_state_id_states", "tours", "states", ["state_id"], ["id"]
        )

    _add_columns("tour_overviews", TOUR_OVERVIEWS_COLUMNS)
    _add_columns("tour_itineraries", TOUR_ITINERARIES_COLUMNS)


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_fks = {fk["name"] for fk in inspector.get_foreign_keys("tours") if fk["name"]}
    if "fk_tours_state_id_states" in existing_fks:
        op.drop_constraint("fk_tours_state_id_states", "tours", type_="foreignkey")

    for name, _, _ in TOUR_ITINERARIES_COLUMNS:
        if _has_column("tour_itineraries", name):
            op.drop_column("tour_itineraries", name)

    for name, _, _ in TOUR_OVERVIEWS_COLUMNS:
        if _has_column("tour_overviews", name):
            op.drop_column("tour_overviews", name)

    for name, _, _ in TOURS_COLUMNS:
        if _has_column("tours", name):
            op.drop_column("tours", name)
