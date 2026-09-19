"""Create one idempotent customer for booking-flow testing.

Run from the backend directory with ``python scripts/seed_dummy_customer.py``.
The record is deliberately marked as a demo account and is never linked to a
login user, so it cannot impersonate a real customer.
"""

from app.database import SessionLocal
from app.models.customers import Customer


DEMO_EMAIL = "demo.customer@tourvaa.test"


def main() -> None:
    db = SessionLocal()
    try:
        customer = db.query(Customer).filter(Customer.email == DEMO_EMAIL).first()
        if customer is None:
            customer = Customer(
                first_name="Demo",
                last_name="Customer",
                full_name="Demo Customer",
                email=DEMO_EMAIL,
                phone_country_code="+91",
                phone="+919876543210",
                country="India",
                city="New Delhi",
                status="active",
                email_verified=False,
                phone_verified=False,
            )
            db.add(customer)
            db.flush()
            customer.customer_code = f"{customer.id:05d}"
            db.commit()
            print(f"Created demo customer {customer.id} ({DEMO_EMAIL})")
        else:
            print(f"Demo customer already exists: {customer.id} ({DEMO_EMAIL})")
    finally:
        db.close()


if __name__ == "__main__":
    main()
