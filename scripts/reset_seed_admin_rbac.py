"""
Tourvaa — unified DB reset + seed runner.

Run from the backend/ directory:

    # RBAC only (idempotent upsert, no wipe)
    python -m scripts.reset_seed_admin_rbac

    # Wipe DB + seed RBAC  (fastest dev reset)
    python -m scripts.reset_seed_admin_rbac --reset

    # Wipe DB + RBAC + all countries/states from GitHub
    python -m scripts.reset_seed_admin_rbac --reset --geo

    # Wipe DB + RBAC + geo + cities (large, takes a few minutes)
    python -m scripts.reset_seed_admin_rbac --reset --geo --cities

    # Wipe DB + RBAC + specific countries + cities
    python -m scripts.reset_seed_admin_rbac --reset --geo --cities --countries IN AE US
"""

from __future__ import annotations

import argparse
import os
import sys
import threading
import time
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import text  # noqa: E402

import app.main  # noqa: F401,E402  — loads every model into Base.metadata
from app.config import settings  # noqa: E402
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.seed import seed_default_roles_and_permissions  # noqa: E402


# ─── helpers ────────────────────────────────────────────────────────────────

LINE = "─" * 64

def _print(msg: str = "") -> None:
    print(msg, flush=True)

def _step(n: int, title: str) -> None:
    _print(f"\n  Step {n}  {title}")
    _print(f"  {'·' * (len(title) + 8)}")

def _ok(msg: str) -> None:
    _print(f"    OK  {msg}")

def _progress_bar(done: int, total: int, width: int = 24) -> str:
    pct = done / max(total, 1)
    filled = int(pct * width)
    return "█" * filled + "░" * (width - filled)


# ─── step 1: reset ──────────────────────────────────────────────────────────

def _ordered_tables() -> list[str]:
    return [t.name for t in reversed(Base.metadata.sorted_tables)]


def reset_database(db) -> None:
    tables = _ordered_tables()
    if not tables:
        raise SystemExit("No SQLAlchemy tables found in metadata — aborting.")

    dialect = engine.dialect.name
    _ok(f"Dialect: {dialect}  |  {len(tables)} tables")

    db.execute(text("SET FOREIGN_KEY_CHECKS=0") if dialect in {"mysql", "mariadb"} else text("PRAGMA foreign_keys=OFF"))
    cleared = 0
    try:
        for table in tables:
            if dialect in {"mysql", "mariadb"}:
                db.execute(text(f"TRUNCATE TABLE `{table}`"))
            else:
                db.execute(text(f'DELETE FROM "{table}"'))
            cleared += 1
    finally:
        db.execute(text("SET FOREIGN_KEY_CHECKS=1") if dialect in {"mysql", "mariadb"} else text("PRAGMA foreign_keys=ON"))

    db.commit()
    _ok(f"Cleared {cleared} tables")


# ─── step 2: RBAC seed ──────────────────────────────────────────────────────

def run_rbac_seed(db) -> None:
    seed_default_roles_and_permissions(db)
    _ok(f"Super admin  : {settings.SUPER_ADMIN_EMAIL}")
    _ok(f"Password     : {settings.SUPER_ADMIN_PASSWORD}")
    _ok("Roles        : super-admin, admin, sub-admin, supplier, agent-reseller, customer")
    _ok("Admin modules: 27 seeded / updated")
    _ok("Permissions  : 226 seeded / updated")


# ─── step 3: geo seed ───────────────────────────────────────────────────────

def run_geo_seed(country_codes: list[str], include_cities: bool) -> None:
    from app.modules.cms.geo_seed_router import _job, _lock, _run_import  # noqa: E402

    scope = ", ".join(c.upper() for c in country_codes) if country_codes else "ALL 250 countries"
    _ok(f"Scope : {scope}")
    _ok(f"Cities: {'yes' if include_cities else 'no — states only'}")
    _print()

    thread = threading.Thread(
        target=_run_import,
        args=(country_codes, include_cities),
        daemon=True,
    )
    thread.start()

    while thread.is_alive():
        with _lock:
            j = dict(_job)
        bar = _progress_bar(j["processed"], j["total"])
        pct = int(j["processed"] / max(j["total"], 1) * 100)
        curr = (j["current"] or "")[:38]
        print(f"\r    [{bar}] {pct:3d}%  {curr:<38}", end="", flush=True)
        time.sleep(0.4)

    thread.join()
    _print()  # newline after progress

    with _lock:
        j = dict(_job)

    if j.get("error"):
        _print(f"    ERROR: {j['error']}")
        raise SystemExit(1)

    _ok(f"Countries added : {j['countries_added']}")
    _ok(f"States added    : {j['states_added']}")
    _ok(f"Cities added    : {j['cities_added']}")


# ─── main ────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Tourvaa unified seed runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--reset", action="store_true",
        help="Wipe all tables before seeding (destructive).",
    )
    parser.add_argument(
        "--yes", "-y", action="store_true",
        help="Skip the interactive confirmation prompt (for scripting).",
    )
    parser.add_argument(
        "--geo", action="store_true",
        help="Import countries + states from GitHub dataset after RBAC seed.",
    )
    parser.add_argument(
        "--cities", action="store_true",
        help="Also import cities (only with --geo; large dataset).",
    )
    parser.add_argument(
        "--countries", nargs="*", default=[], metavar="ISO2",
        help="Limit geo import to specific ISO-2 codes (e.g. --countries IN AE).",
    )
    args = parser.parse_args()

    _print()
    _print(LINE)
    _print("  Tourvaa — Seed Runner")
    _print(LINE)
    _print(f"  Database : {settings.DATABASE_URL}")
    _print(f"  Reset    : {'YES — all data will be wiped' if args.reset else 'No'}")
    _print(f"  RBAC     : Yes (always)")
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

        if args.geo:
            _step(step, "Seeding geo data (countries / states / cities)")
            step += 1
            run_geo_seed(args.countries, args.cities)

    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    _print()
    _print(LINE)
    _print("  All done.")
    _print(LINE)
    _print()


if __name__ == "__main__":
    main()
