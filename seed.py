"""Tourvaa's single seed entry point.

One command seeds everything needed to stand up the platform:

    python seed.py                     RBAC + all countries/states/cities
                                       + payment gateways (if configured)

    python seed.py --reset             wipe every table first (destructive)
    python seed.py --no-cities         skip the large cities download
    python seed.py --countries IN AE   limit geo to specific ISO-2 codes
    python seed.py --launch-markets    limit geo to Tourvaa's original 10
    python seed.py --skip-geo          RBAC + payment gateways only
    python seed.py --demo-tours        also seed the sample dev tours

Geo reference data comes from GeoNames (geonames.org) - free, public
domain, no API key. Payment-gateway seeding is driven entirely by
environment variables and is skipped silently when they are absent, so
the same command is safe on a machine with no gateway credentials.

Every step is idempotent: re-running adds nothing it has already seeded.

CI fixtures are deliberately NOT part of this runner - they are guarded
behind CI-only checks and stay in `python -m scripts.seed_ci_fixtures`.
"""

from __future__ import annotations

import argparse
import os
import sys

BACKEND_ROOT = os.path.dirname(os.path.abspath(__file__))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

# The geo progress output uses box-drawing characters that a default
# Windows console (cp1252) cannot encode.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

LAUNCH_MARKET_COUNTRIES = ["US", "CA", "IN", "NZ", "AE", "QA", "LK", "GB", "AU", "SG"]

LINE = "-" * 64


def _print(msg: str = "") -> None:
    print(msg, flush=True)


def seed_payment_gateways() -> None:
    """Upsert Stripe/PayPal credentials from the environment.

    Skipped per-provider when its variables are absent so a developer
    without gateway credentials can still run the full seed.
    """
    from app.database import SessionLocal
    from app.models.settings import PaymentSetting
    from app.utils.crypto import encrypt_secret

    stripe_public = os.environ.get("STRIPE_PUBLISHABLE_KEY")
    stripe_secret = os.environ.get("STRIPE_SECRET_KEY")
    paypal_id = os.environ.get("PAYPAL_CLIENT_ID")
    paypal_secret = os.environ.get("PAYPAL_CLIENT_SECRET")

    if not (stripe_public and stripe_secret) and not (paypal_id and paypal_secret):
        _print("    -- no gateway credentials in the environment, skipping")
        return

    db = SessionLocal()
    try:
        if stripe_public and stripe_secret:
            setting = db.query(PaymentSetting).filter(PaymentSetting.provider_name == "stripe").first()
            if not setting:
                setting = PaymentSetting(provider_name="stripe")
                db.add(setting)
            setting.public_key = stripe_public
            setting.secret_key = encrypt_secret(stripe_secret)
            setting.is_enabled = True
            setting.mode = "test"
            _print("    OK  Stripe keys saved (secret encrypted)")
        else:
            _print("    -- Stripe vars not set, skipping")

        if paypal_id and paypal_secret:
            mode = os.environ.get("PAYPAL_MODE", "sandbox")
            setting = db.query(PaymentSetting).filter(PaymentSetting.provider_name == "paypal").first()
            if not setting:
                setting = PaymentSetting(provider_name="paypal")
                db.add(setting)
            setting.public_key = paypal_id
            setting.secret_key = encrypt_secret(paypal_secret)
            setting.webhook_id = os.environ.get("PAYPAL_WEBHOOK_ID")
            setting.is_enabled = True
            setting.mode = "test" if mode == "sandbox" else mode
            _print("    OK  PayPal keys saved (secret encrypted)")
        else:
            _print("    -- PayPal vars not set, skipping")

        db.commit()
    finally:
        db.close()


def seed_demo_tours() -> None:
    """Sample tours for local development only - never for production."""
    import runpy

    for module in ("scripts.seed_demo_tour", "scripts.seed_milford_sound_tour"):
        _print(f"    .. {module}")
        runpy.run_module(module, run_name="__main__")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Tourvaa unified seed runner - seeds everything in one command.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--reset", action="store_true",
                        help="Wipe all tables before seeding (destructive).")
    parser.add_argument("--yes", "-y", action="store_true",
                        help="Skip the interactive confirmation for --reset.")
    parser.add_argument("--skip-geo", action="store_true",
                        help="Skip countries/states/cities entirely.")
    parser.add_argument("--no-cities", action="store_true",
                        help="Seed countries and states but skip the large cities download.")
    parser.add_argument("--countries", nargs="*", default=None, metavar="ISO2",
                        help="Limit geo to specific ISO-2 codes, e.g. --countries IN AE.")
    parser.add_argument("--launch-markets", action="store_true",
                        help="Limit geo to Tourvaa's original 10 launch markets.")
    parser.add_argument("--skip-payments", action="store_true",
                        help="Skip payment-gateway seeding.")
    parser.add_argument("--demo-tours", action="store_true",
                        help="Also seed sample dev tours (never use in production).")
    args = parser.parse_args()

    if args.countries is not None:
        countries = [c.upper() for c in args.countries]
        geo_scope = ", ".join(countries)
    elif args.launch_markets:
        countries = LAUNCH_MARKET_COUNTRIES
        geo_scope = ", ".join(countries) + "  (launch markets)"
    else:
        countries = []
        geo_scope = "ALL countries"

    from app.config import settings

    _print()
    _print(LINE)
    _print("  Tourvaa - Seed Runner")
    _print(LINE)
    _print(f"  Database : {settings.DATABASE_URL}")
    _print(f"  Reset    : {'YES - all data will be wiped' if args.reset else 'No'}")
    _print("  RBAC     : Yes")
    _print(f"  Geo      : {'No' if args.skip_geo else geo_scope}")
    if not args.skip_geo:
        _print(f"  Cities   : {'No' if args.no_cities else 'Yes'}")
    _print(f"  Payments : {'No' if args.skip_payments else 'If configured'}")
    _print(f"  Demo     : {'Yes' if args.demo_tours else 'No'}")
    _print(LINE)

    if args.reset and not args.yes:
        confirm = input("\n  Type YES to confirm wiping the database: ").strip()
        if confirm != "YES":
            _print("  Aborted.")
            sys.exit(0)

    from app.database import SessionLocal
    from scripts.reset_seed_admin_rbac import reset_database, run_geo_seed, run_rbac_seed

    step = 1
    db = SessionLocal()
    try:
        if args.reset:
            _print(f"\n  Step {step}  Wiping database")
            step += 1
            reset_database(db)

        _print(f"\n  Step {step}  Seeding RBAC (roles / permissions / super-admin)")
        step += 1
        run_rbac_seed(db)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    if not args.skip_geo:
        _print(f"\n  Step {step}  Seeding geo data (countries / states / cities)")
        step += 1
        run_geo_seed(countries, include_cities=not args.no_cities)

    if not args.skip_payments:
        _print(f"\n  Step {step}  Seeding payment gateways")
        step += 1
        seed_payment_gateways()

    if args.demo_tours:
        _print(f"\n  Step {step}  Seeding demo tours")
        step += 1
        seed_demo_tours()

    _print()
    _print(LINE)
    _print("  All done.")
    _print(LINE)
    _print()


if __name__ == "__main__":
    main()
