"""
One-time script to seed Stripe keys into the payment_settings table.
Run from the backend/ directory:  python seed_stripe.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))

from app.database import SessionLocal
from app.models.settings import PaymentSetting
from app.utils.crypto import encrypt_secret

STRIPE_PUBLIC = os.environ.get("STRIPE_PUBLISHABLE_KEY")
STRIPE_SECRET = os.environ.get("STRIPE_SECRET_KEY")
if not STRIPE_PUBLIC or not STRIPE_SECRET:
    print("Error: set STRIPE_PUBLISHABLE_KEY and STRIPE_SECRET_KEY environment variables before running this script.")
    sys.exit(1)

db = SessionLocal()
try:
    setting = db.query(PaymentSetting).filter(PaymentSetting.provider_name == "stripe").first()
    if not setting:
        setting = PaymentSetting(provider_name="stripe")
        db.add(setting)

    setting.public_key  = STRIPE_PUBLIC
    setting.secret_key  = encrypt_secret(STRIPE_SECRET)
    setting.is_enabled  = True
    setting.mode        = "test"
    db.commit()
    print("Stripe keys saved (secret key encrypted).")
finally:
    db.close()
