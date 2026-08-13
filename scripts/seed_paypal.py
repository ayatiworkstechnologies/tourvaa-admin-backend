"""
One-time script to seed PayPal keys into the payment_settings table.
Run from the backend/ directory:  python scripts/seed_paypal.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models.settings import PaymentSetting
from app.utils.crypto import encrypt_secret

PAYPAL_CLIENT_ID = os.environ.get("PAYPAL_CLIENT_ID")
PAYPAL_CLIENT_SECRET = os.environ.get("PAYPAL_CLIENT_SECRET")
PAYPAL_MODE = os.environ.get("PAYPAL_MODE", "sandbox")
PAYPAL_WEBHOOK_ID = os.environ.get("PAYPAL_WEBHOOK_ID")
if not PAYPAL_CLIENT_ID or not PAYPAL_CLIENT_SECRET:
    print("Error: set PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET environment variables before running this script.")
    sys.exit(1)

db = SessionLocal()
try:
    setting = db.query(PaymentSetting).filter(PaymentSetting.provider_name == "paypal").first()
    if not setting:
        setting = PaymentSetting(provider_name="paypal")
        db.add(setting)

    setting.public_key = PAYPAL_CLIENT_ID
    setting.secret_key = encrypt_secret(PAYPAL_CLIENT_SECRET)
    setting.webhook_id = PAYPAL_WEBHOOK_ID
    setting.is_enabled = True
    setting.mode = "test" if PAYPAL_MODE == "sandbox" else PAYPAL_MODE
    db.commit()
    print("PayPal keys saved (secret key encrypted).")
finally:
    db.close()
