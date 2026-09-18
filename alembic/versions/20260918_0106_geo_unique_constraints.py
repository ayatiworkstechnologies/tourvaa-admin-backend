"""De-duplicate states/cities and add the unique constraints that keep them
that way.

Neither table had any unique index beyond its primary key, so nothing at the
database level stopped the same state or city being inserted twice - the geo
seeder only de-duplicated in application code (SELECT-then-INSERT), which
cannot help when rows arrive from another code path, from a concurrent run,
or from an earlier import that spelled a name differently.

This migration:
  1. Repoints every foreign key that references a duplicate row at the
     surviving (lowest-id) row, so nothing is orphaned.
  2. Deletes the now-unreferenced duplicates.
  3. Adds UNIQUE(country_id, state_name) on states and
     UNIQUE(country_id, state_id, city_name) on cities.

Caveat: MySQL treats NULLs as distinct in a unique index, so cities that
legitimately have no state (city-states such as Singapore, see
cms_geo_seed) are still only protected by the seeder's explicit IS NULL
check. They are de-duplicated by step 2 here regardless, because GROUP BY
does group NULLs together.

Revision ID: 20260918_0106
Revises: 20260918_0105
Create Date: 2026-09-18
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260918_0106"
down_revision = "20260918_0105"
branch_labels = None
depends_on = None

STATE_INDEX = "uq_states_country_name"
CITY_INDEX = "uq_cities_country_state_name"

# Every column that points at cities.id / states.id, so duplicates can be
# merged without orphaning the rows that reference them.
CITY_REFERENCES = [
    ("tours", "city_id"),
    ("customers", "city_id"),
    ("suppliers", "city_id"),
    ("cms_popular_destinations", "city_id"),
]
STATE_REFERENCES = [
    ("tours", "state_id"),
    ("cities", "state_id"),
]


def _has_table(inspector, table: str) -> bool:
    return table in inspector.get_table_names()


def _has_index(inspector, table: str, name: str) -> bool:
    return name in {i["name"] for i in inspector.get_indexes(table)}


def upgrade():
    conn = op.get_bind()
    inspector = inspect(conn)

    # ---- 1. states -------------------------------------------------------
    conn.execute(sa.text("DROP TEMPORARY TABLE IF EXISTS _state_keep"))
    conn.execute(sa.text(
        "CREATE TEMPORARY TABLE _state_keep AS "
        "SELECT country_id, state_name, MIN(id) AS keep_id "
        "FROM states GROUP BY country_id, state_name"
    ))

    for table, column in STATE_REFERENCES:
        if not _has_table(inspector, table):
            continue
        conn.execute(sa.text(
            f"UPDATE {table} t "
            f"JOIN states s ON t.{column} = s.id "
            "JOIN _state_keep k ON k.country_id = s.country_id AND k.state_name = s.state_name "
            f"SET t.{column} = k.keep_id "
            f"WHERE t.{column} <> k.keep_id"
        ))

    conn.execute(sa.text(
        "DELETE s FROM states s "
        "JOIN _state_keep k ON k.country_id = s.country_id AND k.state_name = s.state_name "
        "WHERE s.id <> k.keep_id"
    ))
    conn.execute(sa.text("DROP TEMPORARY TABLE IF EXISTS _state_keep"))

    # ---- 2. cities (after states, so state_id is already canonical) ------
    conn.execute(sa.text("DROP TEMPORARY TABLE IF EXISTS _city_keep"))
    conn.execute(sa.text(
        "CREATE TEMPORARY TABLE _city_keep AS "
        "SELECT country_id, state_id, city_name, MIN(id) AS keep_id "
        "FROM cities GROUP BY country_id, state_id, city_name"
    ))

    for table, column in CITY_REFERENCES:
        if not _has_table(inspector, table):
            continue
        # <=> is the NULL-safe equality MySQL needs here: a city with no
        # state has state_id NULL, and `NULL = NULL` would never match.
        conn.execute(sa.text(
            f"UPDATE {table} t "
            f"JOIN cities c ON t.{column} = c.id "
            "JOIN _city_keep k ON k.country_id = c.country_id "
            "AND k.state_id <=> c.state_id AND k.city_name = c.city_name "
            f"SET t.{column} = k.keep_id "
            f"WHERE t.{column} <> k.keep_id"
        ))

    conn.execute(sa.text(
        "DELETE c FROM cities c "
        "JOIN _city_keep k ON k.country_id = c.country_id "
        "AND k.state_id <=> c.state_id AND k.city_name = c.city_name "
        "WHERE c.id <> k.keep_id"
    ))
    conn.execute(sa.text("DROP TEMPORARY TABLE IF EXISTS _city_keep"))

    # ---- 3. lock it in ---------------------------------------------------
    inspector = inspect(conn)
    if not _has_index(inspector, "states", STATE_INDEX):
        op.create_index(STATE_INDEX, "states", ["country_id", "state_name"], unique=True)
    if not _has_index(inspector, "cities", CITY_INDEX):
        op.create_index(CITY_INDEX, "cities", ["country_id", "state_id", "city_name"], unique=True)


def downgrade():
    conn = op.get_bind()
    inspector = inspect(conn)
    if _has_index(inspector, "cities", CITY_INDEX):
        op.drop_index(CITY_INDEX, table_name="cities")
    if _has_index(inspector, "states", STATE_INDEX):
        op.drop_index(STATE_INDEX, table_name="states")
