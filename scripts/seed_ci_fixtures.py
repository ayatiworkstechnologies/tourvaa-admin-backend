"""Seed the minimal deterministic reference data required by API CI tests.

This command refuses to run unless both ``CI=true`` and the configured
database name contains ``ci``. It is intentionally separate from application
startup and production/demo seeds.
"""

from __future__ import annotations

import os

import app.main  # noqa: F401 - register every SQLAlchemy model

from app.config import settings
from app.database import SessionLocal, engine
from app.models.cms import City, Country, State, Tour, TourCategory
from app.models.users import User
from app.seed import seed_default_roles_and_permissions


INDIA_STATES = (
    ("Andhra Pradesh", "AP"),
    ("Assam", "AS"),
    ("Bihar", "BR"),
    ("Chhattisgarh", "CG"),
    ("Goa", "GA"),
    ("Gujarat", "GJ"),
    ("Haryana", "HR"),
    ("Himachal Pradesh", "HP"),
    ("Jharkhand", "JH"),
    ("Karnataka", "KA"),
    ("Kerala", "KL"),
    ("Madhya Pradesh", "MP"),
    ("Maharashtra", "MH"),
    ("Odisha", "OD"),
    ("Punjab", "PB"),
    ("Rajasthan", "RJ"),
    ("Tamil Nadu", "TN"),
    ("Uttar Pradesh", "UP"),
)


def _assert_ci_database() -> None:
    database_name = (engine.url.database or "").lower()
    if os.environ.get("CI", "").lower() != "true" or "ci" not in database_name:
        raise SystemExit(
            "Refusing to seed CI fixtures: CI=true and a database name containing 'ci' are required."
        )


def main() -> None:
    _assert_ci_database()
    db = SessionLocal()
    try:
        seed_default_roles_and_permissions(db)

        india = db.query(Country).filter(Country.country_code == "IN").first()
        if not india:
            india = Country(
                id=101,
                country_name="India",
                country_code="IN",
                phone_code="+91",
                currency_code="INR",
                status="active",
            )
            db.add(india)
            db.flush()

        states: dict[str, State] = {}
        for state_name, state_code in INDIA_STATES:
            state = (
                db.query(State)
                .filter(State.country_id == india.id, State.state_name == state_name)
                .first()
            )
            if not state:
                state = State(
                    country_id=india.id,
                    state_name=state_name,
                    state_code=state_code,
                    status="active",
                )
                db.add(state)
                db.flush()
            states[state_name] = state

        mumbai = (
            db.query(City)
            .filter(City.country_id == india.id, City.city_name == "Mumbai")
            .first()
        )
        if not mumbai:
            mumbai = City(
                country_id=india.id,
                state_id=states["Maharashtra"].id,
                city_name="Mumbai",
                status="active",
            )
            db.add(mumbai)
            db.flush()

        category = db.query(TourCategory).filter(TourCategory.slug == "ci-adventure").first()
        if not category:
            category = TourCategory(
                category_name="CI Adventure",
                slug="ci-adventure",
                description="Deterministic category used by the backend API suite.",
                status="active",
            )
            db.add(category)
            db.flush()

        tour = db.query(Tour).filter(Tour.slug == "ci-published-tour").first()
        if not tour:
            admin = db.query(User).filter(User.email == settings.SUPER_ADMIN_EMAIL.strip().lower()).first()
            if not admin:
                raise RuntimeError("RBAC seed did not create the configured super-admin")
            tour = Tour(
                tour_code="CI-TOUR-0001",
                title="CI Published Tour",
                slug="ci-published-tour",
                subtitle="Stable integration-test fixture",
                price_start_per_person=100,
                currency="USD",
                country_id=india.id,
                state_id=states["Maharashtra"].id,
                city_id=mumbai.id,
                category_id=category.id,
                start_location="Mumbai",
                finish_location="Mumbai",
                number_of_days=1,
                short_description="Published tour used by backend API integration tests.",
                long_description="Deterministic CI fixture; not created outside an explicitly named CI database.",
                status="published",
                created_by=admin.id,
                updated_by=admin.id,
            )
            db.add(tour)

        db.commit()
        print("CI fixtures ready: India, 18 states, Mumbai, category, and one published tour.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
