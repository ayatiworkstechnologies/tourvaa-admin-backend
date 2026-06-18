"""
Reset the database to only the minimum admin/RBAC seed data.

This script deletes data from every mapped table, then runs the existing
role/permission/super-admin seed. It intentionally does not seed email
templates, tours, customers, bookings, payments, or other business data.

Usage:
    TOURVAA_CONFIRM_DB_RESET=YES python scripts/reset_seed_admin_rbac.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from sqlalchemy import text


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

# Import app.main so every model module is loaded into Base.metadata.
import app.main  # noqa: F401,E402
from app.config import settings  # noqa: E402
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.seed import seed_default_roles_and_permissions  # noqa: E402


CONFIRM_ENV = "TOURVAA_CONFIRM_DB_RESET"


def _ordered_table_names() -> list[str]:
    return [table.name for table in reversed(Base.metadata.sorted_tables)]


def _reset_mysql(db, table_names: list[str]) -> None:
    db.execute(text("SET FOREIGN_KEY_CHECKS=0"))
    try:
        for table_name in table_names:
            db.execute(text(f"TRUNCATE TABLE `{table_name}`"))
    finally:
        db.execute(text("SET FOREIGN_KEY_CHECKS=1"))


def _reset_sqlite(db, table_names: list[str]) -> None:
    db.execute(text("PRAGMA foreign_keys=OFF"))
    try:
        for table_name in table_names:
            db.execute(text(f'DELETE FROM "{table_name}"'))
        db.execute(text("DELETE FROM sqlite_sequence"))
    finally:
        db.execute(text("PRAGMA foreign_keys=ON"))


def _reset_generic(db, table_names: list[str]) -> None:
    for table_name in table_names:
        db.execute(text(f'DELETE FROM "{table_name}"'))


def reset_database() -> None:
    if os.environ.get(CONFIRM_ENV) != "YES":
        raise SystemExit(
            f"Refusing to reset database. Set {CONFIRM_ENV}=YES to confirm."
        )

    table_names = _ordered_table_names()
    if not table_names:
        raise SystemExit("No SQLAlchemy tables are registered; aborting.")

    db = SessionLocal()
    try:
        dialect = engine.dialect.name
        if dialect in {"mysql", "mariadb"}:
            _reset_mysql(db, table_names)
        elif dialect == "sqlite":
            _reset_sqlite(db, table_names)
        else:
            _reset_generic(db, table_names)

        db.commit()

        seed_default_roles_and_permissions(db)

        print("Database reset complete.")
        print(f"Database URL: {settings.DATABASE_URL}")
        print("Seeded only:")
        print("- admin_modules")
        print("- roles")
        print("- permissions")
        print("- role_permissions")
        print("- users: super admin")
        print("- user_roles: super admin role mapping")
        print(f"Admin email: {settings.SUPER_ADMIN_EMAIL}")
        print(f"Admin password: {settings.SUPER_ADMIN_PASSWORD}")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    reset_database()
