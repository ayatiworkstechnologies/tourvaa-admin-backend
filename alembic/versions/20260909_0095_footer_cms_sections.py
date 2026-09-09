"""Add cms_footer_sections and cms_footer_links so the website footer's
Support/Our Company/Login columns become admin-manageable (add/edit
sections and links, enable/disable either independently, reorder both),
instead of the three hardcoded link arrays in PublicFooter.tsx.

Revision ID: 20260909_0095
Revises: 20260909_0094
Create Date: 2026-09-09
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260909_0095"
down_revision = "20260909_0094"
branch_labels = None
depends_on = None


# Seeded from the exact current hardcoded content in
# tourvaa-admin-frontend/src/components/public/PublicFooter.tsx (lines
# 19-40 at the time of writing), so switching the frontend over to the DB
# doesn't blank the live footer.
_SEED_SECTIONS = [
    ("Support", [
        ("Contact", "/contact"),
        ("Legal Notice", "/terms"),
        ("Privacy Policy.", "/privacy-policy"),
        ("General Terms and Conditions", "/terms"),
        ("Plan Your Trip", "/contact"),
    ]),
    ("Our Company", [
        ("About us", "/about"),
        ("Blog", "/blogs"),
        ("Explore Tourvaa", "/destinations"),
        ("Tours", "/tours"),
        ("Traveller's Choice", "/tours?sort=rating_desc"),
    ]),
    ("Login", [
        ("Travellers Login", "/login"),
        ("Agents login", "/agent-portal/login"),
        ("Affiliate login", "/affiliate-portal/login"),
        ("Supplier login", "/supplier-portal/login"),
    ]),
]


def _has_table(inspector, table: str) -> bool:
    return table in inspector.get_table_names()


def upgrade():
    inspector = inspect(op.get_bind())
    if not _has_table(inspector, "cms_footer_sections"):
        sections_table = op.create_table(
            "cms_footer_sections",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("title", sa.String(120), nullable=False),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        links_table = op.create_table(
            "cms_footer_links",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("section_id", sa.Integer(), sa.ForeignKey("cms_footer_sections.id"), nullable=False, index=True),
            sa.Column("label", sa.String(120), nullable=False),
            sa.Column("url", sa.String(500), nullable=False),
            sa.Column("open_in_new_tab", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

        conn = op.get_bind()
        for section_sort, (title, links) in enumerate(_SEED_SECTIONS):
            result = conn.execute(
                sections_table.insert().values(title=title, sort_order=section_sort, is_active=True)
            )
            section_id = result.inserted_primary_key[0]
            op.bulk_insert(
                links_table,
                [
                    {"section_id": section_id, "label": label, "url": url, "open_in_new_tab": False, "sort_order": link_sort, "is_active": True}
                    for link_sort, (label, url) in enumerate(links)
                ],
            )


def downgrade():
    inspector = inspect(op.get_bind())
    if _has_table(inspector, "cms_footer_links"):
        op.drop_table("cms_footer_links")
    inspector = inspect(op.get_bind())
    if _has_table(inspector, "cms_footer_sections"):
        op.drop_table("cms_footer_sections")
