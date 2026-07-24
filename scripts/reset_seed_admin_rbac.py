"""
Tourvaa unified DB reset and seed runner.

Run from the backend directory:

    # RBAC only: roles, permissions, modules, and configured super-admin
    python -m scripts.reset_seed_admin_rbac

    # First production seed after cleanup: admin/RBAC + all countries/states/cities
    python -m scripts.reset_seed_admin_rbac --production

    # Wipe DB + seed RBAC
    python -m scripts.reset_seed_admin_rbac --reset

    # Wipe DB + RBAC + all countries/states from GitHub
    python -m scripts.reset_seed_admin_rbac --reset --geo

    # Wipe DB + RBAC + all countries/states/cities
    python -m scripts.reset_seed_admin_rbac --reset --geo --cities

    # Wipe DB + RBAC + specific countries/states/cities
    python -m scripts.reset_seed_admin_rbac --reset --geo --cities --countries IN AE US
"""

from __future__ import annotations

import argparse
import sys
import threading
import time
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import text  # noqa: E402

import app.main  # noqa: F401,E402 - loads every model into Base.metadata
from app.config import settings  # noqa: E402
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.models.admin_modules import AdminModule  # noqa: E402
from app.models.cms import City, Country, State  # noqa: E402
from app.models.permissions import Permission  # noqa: E402
from app.models.roles import Role  # noqa: E402
from app.models.users import User  # noqa: E402
from app.seed import seed_default_roles_and_permissions  # noqa: E402


LINE = "-" * 64


def _print(msg: str = "") -> None:
    print(msg, flush=True)


def _step(n: int, title: str) -> None:
    _print(f"\n  Step {n}  {title}")
    _print(f"  {'.' * (len(title) + 8)}")


def _ok(msg: str) -> None:
    _print(f"    OK  {msg}")


def _progress_bar(done: int, total: int, width: int = 24) -> str:
    pct = done / max(total, 1)
    filled = int(pct * width)
    return "#" * filled + "-" * (width - filled)


def _ordered_tables() -> list[str]:
    return [table.name for table in reversed(Base.metadata.sorted_tables)]


def reset_database(db) -> None:
    tables = _ordered_tables()
    if not tables:
        raise SystemExit("No SQLAlchemy tables found in metadata - aborting.")

    dialect = engine.dialect.name
    _ok(f"Dialect: {dialect} | {len(tables)} tables")

    db.execute(
        text("SET FOREIGN_KEY_CHECKS=0")
        if dialect in {"mysql", "mariadb"}
        else text("PRAGMA foreign_keys=OFF")
    )
    cleared = 0
    try:
        for table in tables:
            if dialect in {"mysql", "mariadb"}:
                db.execute(text(f"TRUNCATE TABLE `{table}`"))
            else:
                db.execute(text(f'DELETE FROM "{table}"'))
            cleared += 1
    finally:
        db.execute(
            text("SET FOREIGN_KEY_CHECKS=1")
            if dialect in {"mysql", "mariadb"}
            else text("PRAGMA foreign_keys=ON")
        )

    db.commit()
    _ok(f"Cleared {cleared} tables")


def run_rbac_seed(db) -> None:
    seed_default_roles_and_permissions(db)
    role_slugs = [
        slug
        for (slug,) in db.query(Role.slug)
        .filter(Role.is_active == True)
        .order_by(Role.id.asc())
        .all()
    ]
    admin_email = settings.SUPER_ADMIN_EMAIL.strip().lower()
    _ok(f"Super admin  : {admin_email}")
    _ok("Password     : configured securely (value hidden)")
    _ok(f"Admin users  : {db.query(User).filter(User.email == admin_email).count()}")
    _ok(f"Roles        : {', '.join(role_slugs)}")
    _ok(f"Admin modules: {db.query(AdminModule).count()} seeded / updated")
    _ok(f"Permissions  : {db.query(Permission).count()} seeded / updated")


def run_geo_seed(country_codes: list[str], include_cities: bool) -> None:
    from app.routers.cms_geo_seed import _job, _lock, _run_import  # noqa: E402

    scope = ", ".join(code.upper() for code in country_codes) if country_codes else "ALL countries"
    _ok(f"Scope : {scope}")
    _ok(f"Cities: {'yes' if include_cities else 'no - states only'}")
    _print()

    thread = threading.Thread(
        target=_run_import,
        args=(country_codes, include_cities),
        daemon=True,
    )
    thread.start()

    while thread.is_alive():
        with _lock:
            job = dict(_job)
        bar = _progress_bar(job["processed"], job["total"])
        pct = int(job["processed"] / max(job["total"], 1) * 100)
        current = (job["current"] or "")[:38]
        print(f"\r    [{bar}] {pct:3d}%  {current:<38}", end="", flush=True)
        time.sleep(0.4)

    thread.join()
    _print()

    with _lock:
        job = dict(_job)

    if job.get("error"):
        _print(f"    ERROR: {job['error']}")
        raise SystemExit(1)

    _ok(f"Countries added : {job['countries_added']}")
    _ok(f"States added    : {job['states_added']}")
    _ok(f"Cities added    : {job['cities_added']}")
    _ok(f"Total countries : {db_count(Country)}")
    _ok(f"Total states    : {db_count(State)}")
    _ok(f"Total cities    : {db_count(City)}")


def db_count(model) -> int:
    db = SessionLocal()
    try:
        return db.query(model).count()
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Tourvaa unified seed runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Wipe all tables before seeding (destructive).",
    )
    parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="Skip the interactive confirmation prompt (for scripting).",
    )
    parser.add_argument(
        "--geo",
        action="store_true",
        help="Import countries and states from GitHub dataset after RBAC seed.",
    )
    parser.add_argument(
        "--cities",
        action="store_true",
        help="Also import cities. Use only with --geo or --production.",
    )
    parser.add_argument(
        "--countries",
        nargs="*",
        default=[],
        metavar="ISO2",
        help="Limit geo import to specific ISO-2 codes, e.g. --countries IN AE.",
    )
    parser.add_argument(
        "--production",
        action="store_true",
        help="Seed production essentials: super-admin, RBAC, all countries, states, and cities.",
    )
    args = parser.parse_args()

    if args.production:
        args.geo = True
        args.cities = True

    _print()
    _print(LINE)
    _print("  Tourvaa - Seed Runner")
    _print(LINE)
    _print(f"  Database : {settings.DATABASE_URL}")
    _print(f"  Reset    : {'YES - all data will be wiped' if args.reset else 'No'}")
    _print("  RBAC     : Yes")
    _print(f"  Geo      : {'Yes' if args.geo else 'No'}")
    if args.geo:
        scope = ", ".join(args.countries).upper() if args.countries else "ALL"
        _print(f"  Countries: {scope}")
        _print(f"  Cities   : {'Yes' if args.cities else 'No'}")
    _print(LINE)

    if args.reset and not args.yes:
        confirm = input("\n  Type YES to confirm wiping the database: ").strip()
        if confirm != "YES":
            _print("  Aborted.")
            sys.exit(0)

    db = SessionLocal()
    try:
        step = 1

        if args.reset:
            _step(step, "Wiping database")
            step += 1
            reset_database(db)

        _step(step, "Seeding RBAC (roles / permissions / super-admin)")
        step += 1
        run_rbac_seed(db)

    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    if args.geo:
        _step(step, "Seeding geo data (countries / states / cities)")
        run_geo_seed(args.countries, args.cities)

    _print()
    _print(LINE)
    _print("  All done.")
    _print(LINE)
    _print()


if __name__ == "__main__":
    main()
