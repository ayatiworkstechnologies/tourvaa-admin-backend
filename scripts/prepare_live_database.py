"""Prepare an existing Tourvaa database for first production use.

The command is a dry run unless every destructive flag is provided:

    python -m scripts.prepare_live_database
    python -m scripts.prepare_live_database --execute --backup --confirm PREPARE-LIVE

It preserves schema migrations, the configured super-admin, RBAC, geographic
reference data, core settings, email templates, and tour category masters.
Transactional, portal-user, catalogue, communication, audit, and session data
is removed. A full SQL backup is mandatory before execution.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text
from sqlalchemy.engine import make_url

import app.main  # noqa: F401 - register all models
from app.config import settings
from app.database import SessionLocal, engine
from app.seed import seed_default_roles_and_permissions


BACKEND_ROOT = Path(__file__).resolve().parents[1]
CONFIRMATION = "PREPARE-LIVE"
SYSTEM_DATABASES = {"information_schema", "mysql", "performance_schema", "sys"}

# These tables are configuration/reference data and remain unchanged.
PRESERVE_FULL_TABLES = {
    "alembic_version",
    "roles",
    "permissions",
    "role_permissions",
    "admin_modules",
    "countries",
    "states",
    "cities",
    "app_settings",
    "payment_settings",
    "api_settings",
    "email_templates",
    "tour_categories",
    "tour_subcategories",
}

# Only the configured super-admin and its role assignment remain in these.
PRESERVE_FILTERED_TABLES = {"users", "user_roles"}


def _quote(name: str) -> str:
    return engine.dialect.identifier_preparer.quote(name)


def _table_counts(connection, tables: list[str]) -> dict[str, int]:
    return {
        table: int(connection.execute(text(f"SELECT COUNT(*) FROM {_quote(table)}")).scalar_one())
        for table in tables
    }


def _alembic_head() -> str:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    heads = ScriptDirectory.from_config(config).get_heads()
    if len(heads) != 1:
        raise RuntimeError(f"Expected one Alembic head, found {heads}")
    return heads[0]


def _validate_database(connection, tables: list[str]) -> tuple[int, str]:
    url = make_url(settings.DATABASE_URL)
    database = url.database or ""
    if not database or database.lower() in SYSTEM_DATABASES:
        raise RuntimeError(f"Refusing to operate on unsafe database name: {database!r}")

    required = PRESERVE_FULL_TABLES | PRESERVE_FILTERED_TABLES
    missing = sorted(required - set(tables))
    if missing:
        raise RuntimeError(f"Required tables are missing: {', '.join(missing)}")

    current_revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    expected_revision = _alembic_head()
    if current_revision != expected_revision:
        raise RuntimeError(
            f"Database migration is {current_revision}; run Alembic to reach {expected_revision} first"
        )

    admin = connection.execute(
        text(
            """
            SELECT u.id, r.slug
            FROM users u
            JOIN roles r ON r.id = u.role_id
            WHERE LOWER(u.email) = LOWER(:email)
              AND r.slug = 'super-admin'
              AND u.is_active = TRUE
            """
        ),
        {"email": settings.SUPER_ADMIN_EMAIL.strip()},
    ).first()
    if not admin:
        raise RuntimeError("The configured active super-admin account was not found")
    return int(admin.id), database


def _find_mysqldump() -> Path:
    discovered = shutil.which("mysqldump")
    candidates = [
        Path(discovered) if discovered else None,
        Path(r"C:\Program Files\MySQL\MySQL Server 8.0\bin\mysqldump.exe"),
        Path(r"C:\Program Files\MySQL\MySQL Workbench 8.0\mysqldump.exe"),
    ]
    for candidate in candidates:
        if candidate and candidate.is_file():
            return candidate
    raise RuntimeError("mysqldump was not found; install MySQL client tools before cleanup")


def _backup_database(database: str) -> Path:
    url = make_url(settings.DATABASE_URL)
    dialect = engine.dialect.name

    if dialect == "sqlite":
        db_path = Path(url.database)
        if not db_path.is_file():
            raise RuntimeError(f"SQLite database file not found at {db_path}")
        backup_path = db_path.with_suffix(f".backup-{datetime.now():%Y%m%d-%H%M%S}.db")
        shutil.copy2(db_path, backup_path)
        return backup_path

    backup_dir = (BACKEND_ROOT / "backups").resolve()
    if BACKEND_ROOT.resolve() not in backup_dir.parents:
        raise RuntimeError("Backup directory resolved outside the backend workspace")
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / f"before-live-cleanup-{datetime.now():%Y%m%d-%H%M%S}.sql"

    command = [
        str(_find_mysqldump()),
        "--single-transaction",
        "--routines",
        "--triggers",
        "--events",
        "--set-gtid-purged=OFF",
        "--default-character-set=utf8mb4",
        "--host",
        url.host or "127.0.0.1",
        "--port",
        str(url.port or 3306),
        "--user",
        url.username or "",
        database,
    ]
    environment = os.environ.copy()
    if url.password:
        environment["MYSQL_PWD"] = url.password

    with backup_path.open("wb") as output:
        result = subprocess.run(
            command,
            stdout=output,
            stderr=subprocess.PIPE,
            env=environment,
            check=False,
        )
    if result.returncode != 0:
        backup_path.unlink(missing_ok=True)
        message = result.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"mysqldump failed: {message}")
    if backup_path.stat().st_size == 0:
        backup_path.unlink(missing_ok=True)
        raise RuntimeError("mysqldump produced an empty backup")
    return backup_path


def _print_plan(counts: dict[str, int], admin_id: int) -> list[str]:
    clear_tables = sorted(set(counts) - PRESERVE_FULL_TABLES - PRESERVE_FILTERED_TABLES)
    print("\nPRESERVE COMPLETELY")
    for table in sorted(PRESERVE_FULL_TABLES):
        print(f"  {table:34} {counts[table]:8}")
    print("\nPRESERVE FILTERED")
    print(f"  users                              1 of {counts['users']} (super-admin id {admin_id})")
    print(f"  user_roles                         admin assignments only ({counts['user_roles']} currently)")
    print("\nCLEAR")
    for table in clear_tables:
        if counts[table]:
            print(f"  {table:34} {counts[table]:8}")
    print(f"\nTables cleared: {len(clear_tables)}")
    print(f"Rows currently in cleared tables: {sum(counts[table] for table in clear_tables)}")
    return clear_tables


def _execute_cleanup(connection, clear_tables: list[str], admin_id: int) -> None:
    dialect = engine.dialect.name
    if dialect in {"mysql", "mariadb"}:
        connection.execute(text("SET FOREIGN_KEY_CHECKS=0"))
    elif dialect == "sqlite":
        connection.execute(text("PRAGMA foreign_keys=OFF"))

    try:
        for table in clear_tables:
            if dialect in {"mysql", "mariadb"}:
                connection.execute(text(f"TRUNCATE TABLE {_quote(table)}"))
            else:
                connection.execute(text(f"DELETE FROM {_quote(table)}"))
        connection.execute(text("DELETE FROM user_roles WHERE user_id <> :admin_id"), {"admin_id": admin_id})
        connection.execute(text("DELETE FROM users WHERE id <> :admin_id"), {"admin_id": admin_id})
        connection.execute(
            text(
                """
                UPDATE users
                SET token_version = token_version + 1,
                    reset_password_token = NULL,
                    reset_password_expires_at = NULL,
                    email_verification_token = NULL,
                    email_verification_expires_at = NULL
                WHERE id = :admin_id
                """
            ),
            {"admin_id": admin_id},
        )
    finally:
        if dialect in {"mysql", "mariadb"}:
            connection.execute(text("SET FOREIGN_KEY_CHECKS=1"))
        elif dialect == "sqlite":
            connection.execute(text("PRAGMA foreign_keys=ON"))

    connection.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="Apply the cleanup after validation")
    parser.add_argument("--backup", action="store_true", help="Create the mandatory SQL backup")
    parser.add_argument("--confirm", default="", help=f"Must be exactly {CONFIRMATION!r}")
    args = parser.parse_args()

    tables = sorted(inspect(engine).get_table_names())
    with engine.connect() as connection:
        admin_id, database = _validate_database(connection, tables)
        counts = _table_counts(connection, tables)
        clear_tables = _print_plan(counts, admin_id)

    if not args.execute:
        print("\nDRY RUN ONLY. No database rows were changed.")
        return
    if not args.backup or args.confirm != CONFIRMATION:
        raise SystemExit(
            f"Execution requires --backup --confirm {CONFIRMATION}; no database rows were changed."
        )

    backup_path = _backup_database(database)
    print(f"\nBackup created: {backup_path}")

    with engine.connect() as connection:
        _execute_cleanup(connection, clear_tables, admin_id)

    db = SessionLocal()
    try:
        seed_default_roles_and_permissions(db)
    finally:
        db.close()

    with engine.connect() as connection:
        final_counts = _table_counts(connection, tables)
        remaining_users = connection.execute(text("SELECT COUNT(*) FROM users")).scalar_one()
        remaining_admin = connection.execute(
            text("SELECT COUNT(*) FROM users WHERE id = :admin_id AND is_active = TRUE"),
            {"admin_id": admin_id},
        ).scalar_one()
    if remaining_users != 1 or remaining_admin != 1:
        raise RuntimeError("Post-cleanup super-admin verification failed")
    if any(final_counts[table] for table in clear_tables):
        raise RuntimeError("Post-cleanup verification found rows in a cleared table")

    print("\nCleanup complete. Essential reference/configuration data and one super-admin remain.")


if __name__ == "__main__":
    main()
