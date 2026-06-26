"""
One-time script to seed Stripe keys into the payment_settings table.
Run from the backend/ directory:  python seed_stripe.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))

from app.database import SessionLocal
from app.modules.settings.models import PaymentSetting
from app.crypto import encrypt_secret

STRIPE_PUBLIC  = os.environ["STRIPE_PUBLIC_KEY"]
STRIPE_SECRET  = os.environ["STRIPE_SECRET_KEY"]

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
