from sqlalchemy.orm import Session

from app.modules.audit.service import log_audit
from app.modules.settings.models import ApiSetting, AppSetting, PaymentSetting
from app.modules.users.models import User


DEFAULT_SETTINGS = [
    {"key": "site_name", "label": "Site Name", "value": "Tourvaa", "group": "general", "is_public": True},
    {"key": "company_name", "label": "Company Name", "value": "Tourvaa", "group": "general", "is_public": True},
    {"key": "support_email", "label": "Support Email", "value": "support@tourvaa.com", "group": "general", "is_public": True},
    {"key": "support_phone", "label": "Support Phone", "value": "+910000000000", "group": "general", "is_public": True},
    {"key": "company_address", "label": "Company Address", "value": "New Zealand", "group": "general", "is_public": True},
    {"key": "default_country", "label": "Default Country", "value": "India", "group": "general", "is_public": True},
    {"key": "default_currency", "label": "Default Currency", "value": "INR", "group": "general", "is_public": True},
    {"key": "logo", "label": "Logo URL", "value": "", "group": "general", "is_public": True},
    {"key": "favicon", "label": "Favicon URL", "value": "", "group": "general", "is_public": True},
    {"key": "booking_prefix", "label": "Booking Prefix", "value": "TVA", "group": "booking", "is_public": False},
    {"key": "currency", "label": "Currency", "value": "NZD", "group": "booking", "is_public": True},
    {"key": "timezone", "label": "Timezone", "value": "Pacific/Auckland", "group": "system", "is_public": False},
    {"key": "maintenance_mode", "label": "Maintenance Mode", "value": "false", "group": "system", "is_public": False},
    {"key": "stripe_enabled", "label": "Stripe Enabled", "value": "false", "group": "payment", "is_public": False},
    {"key": "stripe_public_key", "label": "Stripe Public Key", "value": "", "group": "payment", "is_public": False},
    {"key": "stripe_secret_key", "label": "Stripe Secret Key Placeholder", "value": "", "group": "payment", "is_public": False},
    {"key": "paypal_enabled", "label": "PayPal Enabled", "value": "false", "group": "payment", "is_public": False},
    {"key": "paypal_client_id", "label": "PayPal Client ID Placeholder", "value": "", "group": "payment", "is_public": False},
    {"key": "paypal_secret", "label": "PayPal Secret Placeholder", "value": "", "group": "payment", "is_public": False},
    {"key": "payment_surcharge_percentage", "label": "Payment Surcharge Percentage", "value": "0", "group": "payment", "is_public": False},
    {"key": "default_payment_mode", "label": "Default Payment Mode", "value": "test", "group": "payment", "is_public": False},
    {"key": "google_map_api_key", "label": "Google Maps API Key Placeholder", "value": "", "group": "api", "is_public": False},
    {"key": "email_api_key", "label": "Email API Key Placeholder", "value": "", "group": "api", "is_public": False},
    {"key": "sms_api_key", "label": "SMS API Key Placeholder", "value": "", "group": "api", "is_public": False},
    {"key": "third_party_api_key", "label": "Third Party API Key Placeholder", "value": "", "group": "api", "is_public": False},
    {"key": "brightlane_external_link", "label": "Brightlane External Link Placeholder", "value": "", "group": "api", "is_public": False},
]

DEFAULT_PAYMENT_SETTINGS = [
    {"provider_name": "stripe", "is_enabled": False, "public_key": "", "secret_key": "", "surcharge_percentage": "0", "mode": "test"},
    {"provider_name": "paypal", "is_enabled": False, "public_key": "", "secret_key": "", "surcharge_percentage": "0", "mode": "test"},
]

DEFAULT_API_SETTINGS = [
    {"api_name": "google_maps", "api_key": "", "api_secret": "", "api_url": "", "is_enabled": False},
    {"api_name": "email_service", "api_key": "", "api_secret": "", "api_url": "", "is_enabled": False},
    {"api_name": "sms_service", "api_key": "", "api_secret": "", "api_url": "", "is_enabled": False},
    {"api_name": "brightlane", "api_key": "", "api_secret": "", "api_url": "", "is_enabled": False},
]


def seed_settings(db: Session):
    for item in DEFAULT_SETTINGS:
        setting = db.query(AppSetting).filter(AppSetting.key == item["key"]).first()

        if not setting:
            db.add(AppSetting(**item))

    db.commit()


def seed_payment_settings(db: Session):
    for item in DEFAULT_PAYMENT_SETTINGS:
        setting = (
            db.query(PaymentSetting)
            .filter(PaymentSetting.provider_name == item["provider_name"])
            .first()
        )

        if not setting:
            db.add(PaymentSetting(**item))

    db.commit()


def seed_api_settings(db: Session):
    for item in DEFAULT_API_SETTINGS:
        setting = db.query(ApiSetting).filter(ApiSetting.api_name == item["api_name"]).first()

        if not setting:
            db.add(ApiSetting(**item))

    db.commit()


def get_settings(db: Session):
    seed_settings(db)
    return db.query(AppSetting).order_by(AppSetting.group.asc(), AppSetting.id.asc()).all()


def get_payment_settings(db: Session):
    seed_payment_settings(db)
    return db.query(PaymentSetting).order_by(PaymentSetting.provider_name.asc()).all()


def get_api_settings(db: Session):
    seed_api_settings(db)
    return db.query(ApiSetting).order_by(ApiSetting.api_name.asc()).all()


def update_payment_setting(
    db: Session,
    provider_name: str,
    values: dict,
    actor: User | None = None,
    request=None,
):
    seed_payment_settings(db)
    setting = (
        db.query(PaymentSetting)
        .filter(PaymentSetting.provider_name == provider_name.strip().lower())
        .first()
    )

    if not setting:
        return None

    old_values = {
        "is_enabled": setting.is_enabled,
        "public_key": setting.public_key,
        "secret_key": setting.secret_key,
        "surcharge_percentage": setting.surcharge_percentage,
        "mode": setting.mode,
    }

    for key, value in values.items():
        if value is not None and hasattr(setting, key):
            setattr(setting, key, value.strip() if isinstance(value, str) else value)

    log_audit(
        db,
        actor=actor,
        action="update_payment_setting",
        entity_type="payment_setting",
        entity_id=setting.id,
        old_values=old_values,
        new_values=values,
        request=request,
    )
    db.commit()
    db.refresh(setting)
    return setting


def update_api_setting(
    db: Session,
    api_name: str,
    values: dict,
    actor: User | None = None,
    request=None,
):
    seed_api_settings(db)
    setting = db.query(ApiSetting).filter(ApiSetting.api_name == api_name.strip().lower()).first()

    if not setting:
        return None

    old_values = {
        "api_key": setting.api_key,
        "api_secret": setting.api_secret,
        "api_url": setting.api_url,
        "is_enabled": setting.is_enabled,
    }

    for key, value in values.items():
        if value is not None and hasattr(setting, key):
            setattr(setting, key, value.strip() if isinstance(value, str) else value)

    log_audit(
        db,
        actor=actor,
        action="update_api_setting",
        entity_type="api_setting",
        entity_id=setting.id,
        old_values=old_values,
        new_values=values,
        request=request,
    )
    db.commit()
    db.refresh(setting)
    return setting


def update_settings(
    db: Session,
    values: dict[str, str | None],
    actor: User | None = None,
    request=None,
):
    seed_settings(db)
    old_values = {
        setting.key: setting.value
        for setting in db.query(AppSetting).filter(AppSetting.key.in_(values.keys())).all()
    }

    for key, value in values.items():
        setting = db.query(AppSetting).filter(AppSetting.key == key).first()

        if setting:
            setting.value = value

    log_audit(
        db,
        actor=actor,
        action="update_settings",
        entity_type="settings",
        old_values=old_values,
        new_values=values,
        request=request,
    )
    db.commit()
    return get_settings(db)
